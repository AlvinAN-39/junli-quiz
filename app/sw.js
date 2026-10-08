/* ==========================================================================
 * 军理刷题 · Service Worker（纯原生，无依赖）
 * 目标：Cache API 预缓存全部资源，首屏零网络请求，断网可用。
 *
 * 说明：
 *  - 预缓存使用「逐个 add + 失败忽略」，任一资源缺失都不会让 SW 安装失败。
 *  - 运行时对同源 GET 采用 cache-first，并把成功响应写入缓存，做到「联网过
 *    一次，之后永久离线」。
 *  - 导航请求使用 network-first，失败时回退到缓存的 index.html。
 *  - 注意：SW 只能拦截 scope（app/ 目录）内的请求。若题库位于 scope 之外，
 *    请把 index.html 与 data/ 放在同一层目录后再注册；单文件版（dist/军理刷题.html）
 *    已内嵌题库，不依赖本文件。
 * ========================================================================== */
var CACHE_NAME = 'jlx-cache-v2';

var PRECACHE = [
  './',
  './index.html',
  './app.css',
  './app.js',
  './manifest.webmanifest',
  './icons/icon.svg',
  './data/questions.json',
  './sw.js'
];

function cachePut(request, response) {
  if (!response || !response.ok) return Promise.resolve(null);
  return caches.open(CACHE_NAME).then(function (cache) {
    return cache.put(request, response)['catch'](function () { return null; });
  })['catch'](function () { return null; });
}

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return Promise.all(PRECACHE.map(function (url) {
        var req = new Request(url, { cache: 'reload' });
        return cache.add(req)['catch'](function () { return null; });
      }));
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== CACHE_NAME) return caches['delete'](k);
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

  // Service Worker 脚本自身：网络优先、失败回退缓存。
  // 若不处理，断网刷新时浏览器重新校验 sw.js 会失败 → 整个 SW 失效。
  if (url.pathname === self.location.pathname) {
    event.respondWith(
      fetch(req).then(function (res) {
        cachePut(req, res.clone());
        return res;
      })['catch'](function () {
        return caches.match(req).then(function (hit) {
          return hit || new Response('', { status: 504, statusText: 'offline' });
        });
      })
    );
    return;
  }

  // 页面导航：优先网络（拿更新），断网回退缓存
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(function (res) {
        cachePut(req, res.clone());
        return res;
      })['catch'](function () {
        return caches.match('./index.html').then(function (hit) {
          return hit || caches.match('./');
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
        if (res && res.ok && res.type === 'basic') cachePut(req, res.clone());
        return res;
      });
    })
  );
});
