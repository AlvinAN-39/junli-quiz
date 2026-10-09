/* ==========================================================================
 * 军理刷题 · Service Worker（纯原生，无依赖）
 *
 * 目标：Cache API 预缓存关键资源，首屏零网络请求，断网可用；
 *       并且**版本更新后断网看到的一定是新版**（这是 2026-10-09 修的核心问题）。
 *
 * 为什么改成现在这样 —— 旧实现的三个真实缺陷（外部审查报告 + 代码复核）：
 *   ① 缓存键不一致：联网时 cachePut(req, …) 用的是**导航请求的 URL**（如 `/`），
 *      断网回退却查 `./index.html`。Cache Storage 以 URL 为键，两者不是同一条目，
 *      于是「联网看到新版、断网回到旧版」。现在两端统一用固定的 HTML_KEY。
 *   ② 写入不纳入事件生命周期：`cachePut(...); return res;` 之后立即返回，
 *      浏览器可能在缓存落盘前就结束事件 → 竞态。现在把写入 Promise **串进
 *      respondWith 的链**（事件会等这条链 settle 才结束），效果等同 waitUntil 且不会
 *      因在回调里调用 waitUntil 而抛 InvalidStateError。
 *   ③ 缓存名固定不随内容变化：`jlx-cache-v2` 长期不变，Worker 字节没变 → 浏览器
 *      不认为 SW 更新，旧的 HTML 永远留在缓存里。现在缓存名含构建注入的内容哈希。
 *
 * 另外两项改进：
 *   ④ 精简预缓存：PWA 版的 index.html 已把 CSS / JS / 题库**全部内联**，
 *      再单独预缓存 app.css / app.js / data/questions.json 纯属重复占用。
 *      关键资源（CRITICAL）必须成功，否则**安装失败**——保留旧 Worker 继续可用，
 *      不会出现「新 Worker 装好了但没有 HTML」的半残状态。
 *   ⑤ 提供缓存状态查询（message 接口），供 App 的「设置 → 离线版本」显示是否就绪。
 *
 * 注意：SW 只能拦截 scope 内的请求（app/ 目录，构建后是 dist/web/）。
 *      单文件版（dist/军理刷题.html）已内嵌题库、且 file:// 不支持 SW，不依赖本文件。
 * ========================================================================== */

/* 构建标识：由 tools/bundle.py 在打包时替换为内容哈希（源码里保留占位符）。
 * 内容一变哈希就变 → 缓存名变 → Worker 字节变 → 浏览器触发更新、旧缓存被清理。 */
var BUILD_ID = '__BUILD_ID__';
var CACHE_NAME = 'jlx-cache-' + BUILD_ID;
/* 本应用的缓存名前缀：activate 只清理**自己的**旧缓存。
 * Cache Storage 按 origin 共享、不按 SW scope 隔离，若删掉所有 k !== CACHE_NAME 的
 * 缓存，会把同源下其它应用（同一 GitHub Pages 用户站里的别的项目）的离线缓存一起清空。 */
var CACHE_PREFIX = 'jlx-cache-';

/* 统一的 HTML 缓存键：联网写入与断网读取**必须是同一个键**（缺陷①的修法）。 */
var HTML_KEY = './index.html';

/* 关键资源：任一失败都会让新 Worker 安装失败（旧 Worker 保留，避免半残状态）。 */
var CRITICAL = [
  './index.html'
];

/* 可选资源：失败只忽略，不影响安装（图标缺失不该让整个 App 无法离线使用）。 */
var OPTIONAL = [
  './manifest.webmanifest',
  './icons/icon.svg'
];

/**
 * 把响应写入缓存。
 * 失败一律吞掉并返回 null —— 缓存写入失败不该让页面报错；
 * 调用方（导航分支）会把返回的 Promise 串进事件生命周期，确保落盘。
 */
function cachePut(key, response) {
  if (!response || !response.ok) return Promise.resolve(null);
  return caches.open(CACHE_NAME).then(function (cache) {
    return cache.put(key, response)['catch'](function () { return null; });
  })['catch'](function () { return null; });
}

/** 读取缓存的 HTML（断网回退用）。 */
function matchHtml() {
  return caches.match(HTML_KEY);
}

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      // 关键资源用 addAll：失败会 reject → install 失败 → 浏览器保留旧 Worker。
      return cache.addAll(CRITICAL.map(function (u) {
        return new Request(u, { cache: 'reload' });
      }));
    }).then(function () {
      return Promise.all(OPTIONAL.map(function (u) {
        return caches.open(CACHE_NAME).then(function (cache) {
          return cache.add(new Request(u, { cache: 'reload' }))['catch'](function () { return null; });
        });
      }));
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  // 只有 install 成功才会走到这里，所以「删旧缓存」天然发生在「新缓存就绪之后」。
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k.indexOf(CACHE_PREFIX) === 0 && k !== CACHE_NAME) return caches['delete'](k);
        return null;
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;

  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;   // 本 App 不发跨域请求，直接放行

  // SW 脚本自身：网络优先、失败回退缓存。
  // 若不处理，断网刷新时浏览器重新校验 sw.js 会失败 → 整个 SW 失效。
  if (url.pathname === self.location.pathname) {
    event.respondWith(
      fetch(req).then(function (res) {
        return cachePut(req, res.clone()).then(function () { return res; });
      })['catch'](function () {
        return caches.match(req).then(function (hit) {
          return hit || new Response('', { status: 504, statusText: 'offline' });
        });
      })
    );
    return;
  }

  // 页面导航：网络优先（拿更新），断网回退到**同一个键**。
  // 关键在于写入用 HTML_KEY 而不是 req —— 否则 `/` 与 `./index.html` 会各存一份，
  // 断网时拿到的是另一份（很可能是旧的），这正是用户遇到的「离线仍是旧版」。
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(function (res) {
        // 把写缓存串进这条链：事件会等它完成，避免「页面显示了新内容但没落盘」
        return cachePut(HTML_KEY, res.clone()).then(function () { return res; });
      })['catch'](function () {
        return matchHtml().then(function (hit) {
          if (hit) return hit;
          return new Response(
            '<!doctype html><meta charset="utf-8"><title>离线</title>' +
            '<p style="font:16px/1.6 system-ui;padding:24px">当前处于离线状态，且本机还没有可用的离线副本。' +
            '请联网打开一次本应用以完成缓存。</p>',
            { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        });
      })
    );
    return;
  }

  // 复习提纲数据：网络优先。
  // 它是唯一一个「支持不重新打包、直接把新文件放进部署目录」的资源
  // （docs/04-outline-data.md 的「方式二」）。若也走缓存优先，换掉文件后用户
  // 会永远看到旧提纲 —— SW 字节没变，浏览器不会触发更新。
  if (url.pathname.indexOf('/data/outline-2026.json') >= 0) {
    event.respondWith(
      fetch(req).then(function (res) {
        return cachePut(req, res.clone()).then(function () { return res; });
      })['catch'](function () {
        return caches.match(req).then(function (hit) {
          return hit || new Response('', { status: 504, statusText: 'offline' });
        });
      })
    );
    return;
  }

  // 静态资源：缓存优先，未命中再走网络并回写缓存
  event.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && res.ok && res.type === 'basic') {
          return cachePut(req, res.clone()).then(function () { return res; });
        }
        return res;
      });
    })
  );
});

/**
 * 缓存状态查询（供 App「设置 → 离线版本」显示）。
 * App 发 {type:'cache-status'}，SW 回 {type:'cache-status', cacheName, buildId, hasHtml, updatedAt}。
 * 「就绪」= 当前版本名的缓存里确实有 HTML —— 这才是「离线已更新」的可验证证据，
 * 而不是只看页面显示了新内容（页面新 ≠ 缓存已落盘）。
 */
self.addEventListener('message', function (event) {
  var data = event.data || {};
  if (data.type !== 'cache-status') return;
  var reply = function (port, payload) {
    try { port.postMessage(payload); } catch (e) { /* 端口已失效，忽略 */ }
  };
  var port = event.ports && event.ports[0];
  if (!port) return;
  caches.open(CACHE_NAME).then(function (cache) {
    return cache.match(HTML_KEY).then(function (hit) {
      return {
        type: 'cache-status',
        cacheName: CACHE_NAME,
        buildId: BUILD_ID,
        hasHtml: !!hit,
        updatedAt: hit ? (hit.headers.get('date') || '') : ''
      };
    });
  })['catch'](function () {
    return { type: 'cache-status', cacheName: CACHE_NAME, buildId: BUILD_ID, hasHtml: false, updatedAt: '' };
  }).then(function (payload) {
    reply(port, payload);
  });
});
