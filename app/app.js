/* ==========================================================================
 * 军理刷题 · app.js
 * 纯原生 JS（无模块、无依赖、无构建）—— 必须写成普通脚本 + IIFE，
 * 以便打包时把本文件内容直接内联进 script 标签（切勿使用 ESM）。
 * 数据契约：docs/02-data-contract.md（冻结）
 * ========================================================================== */
(function () {
  'use strict';

  /* ======================================================================
   * 0. 常量
   * ==================================================================== */
  var KEY_PROGRESS = 'jlx.progress.v1';
  var KEY_SETTINGS = 'jlx.settings.v1';
  var KEY_EXAMS    = 'jlx.exams.v1';
  var KEY_META     = 'jlx.meta.v1';
  // 练习与背题各用独立存档，互不覆盖。
  var KEY_SESSION  = 'jlx.session.v1';
  var KEY_RECITE   = 'jlx.recite.v1'; // 背题独立存档，不覆盖练习进度
  var KEY_EXAM_SESSION = 'jlx.exam-session.v1'; // 未完成考试独立保存，恢复后等待主动继续
  var SESSION_VER  = 1;

  var APP_NAME = '军理刷题';
  var EXPORT_VER = 1;

  var TYPE_LABEL = { single: '单选题', multi: '多选题', judge: '判断题', fill: '填空题', short: '简答题' };
  var TYPE_SHORT = { single: '单选', multi: '多选', judge: '判断', fill: '填空', short: '简答' };
  var TYPE_ORDER = ['single', 'multi', 'judge', 'fill', 'short'];
  var LETTERS = 'ABCDEFGHIJ';

  var DEFAULT_SETTINGS = {
    theme: 'auto',        // auto | light | dark
    fontSize: 'm',        // s | m | l | xl
    order: 'seq',         // seq | rand
    shuffleOptions: false,
    autoNext: true,
    examCount: 20,
    examMinutes: 30,
    explainOpen: null,    // null=跟随上下文默认 | true=展开 | false=折叠（仅题目卡片路径记忆）
    sound: true,          // 音效开关（默认开）
    haptic: true,         // 震动开关（默认开；iPhone 上静默无效）
    volume: 2             // 音效音量档位：1=小(2×) 2=中(3×) 3=大(4×)，见 SoundVolume
  };

  var NAV_TITLE = {
    home: '首页', practice: '练习', exam: '模拟考试', recite: '背题模式',
    outline: '复习提纲', wrong: '错题本', fav: '收藏夹', search: '搜索', stats: '学习统计', sync: '导入 / 导出', settings: '设置'
  };

  var $  = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ======================================================================
   * 1. 存储层（localStorage 全部包 try/catch：Safari 隐私模式会抛异常）
   * ==================================================================== */
  var memStore = {};
  var LS_OK = (function () {
    try {
      var k = '__jlx_probe__';
      window.localStorage.setItem(k, '1');
      window.localStorage.removeItem(k);
      return true;
    } catch (e) { return false; }
  })();

  var storageFailed = !LS_OK;

  function rawGet(key) {
    // 当前页写入可能因额度不足失败，最新内存镜像必须优先于旧磁盘值。
    if (Object.prototype.hasOwnProperty.call(memStore, key)) return memStore[key];
    if (LS_OK) {
      try {
        var v = window.localStorage.getItem(key);
        if (v !== null) return v;
      } catch (e) { /* 忽略，走内存镜像 */ }
    }
    return null;
  }
  function rawSet(key, val) {
    memStore[key] = val;              // 内存镜像：写失败也不丢当前会话数据
    if (!LS_OK) return false;
    try { window.localStorage.setItem(key, val); return true; }
    catch (e) { storageFailed = true; return false; }
  }
  function rawDel(key) {
    // 删除标记保留在内存；磁盘删除失败时也不能把旧存档重新读回来。
    memStore[key] = null;
    if (!LS_OK) return;
    try { window.localStorage.removeItem(key); } catch (e) { storageFailed = true; }
  }
  function loadJSON(key, fallback) {
    var raw = rawGet(key);
    if (!raw) return fallback;
    try {
      var v = JSON.parse(raw);
      return (v && typeof v === 'object') ? v : fallback;
    } catch (e) { return fallback; }
  }
  function saveJSON(key, val) { return rawSet(key, JSON.stringify(val)); }
  /** 外部对象与数组分开校验；数组不能作为题目进度或结果字典。 */
  function isRecord(v) { return !!v && typeof v === 'object' && !Array.isArray(v); }

  /* ======================================================================
   * 2. 工具函数
   * ==================================================================== */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function escRe(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function fmtClock(sec) {
    sec = Math.max(0, Math.round(sec));
    var m = Math.floor(sec / 60), s = sec % 60;
    if (m >= 60) return Math.floor(m / 60) + ':' + pad2(m % 60) + ':' + pad2(s);
    return pad2(m) + ':' + pad2(s);
  }
  function fmtDur(ms) {
    var sec = Math.round(ms / 1000);
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + '分' + pad2(s) + '秒';
  }
  function dayKey(ts) {
    var d = new Date(ts);
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }
  function fmtDate(ts) {
    if (!ts) return '—';
    var d = new Date(ts);
    return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }
  function pct(a, b) { return b > 0 ? Math.round(a / b * 100) : 0; }

  /** 洗牌内核：Fisher-Yates，随机源由调用方提供（便于用种子复现同一顺序）。 */
  function shuffleCore(arr, rand) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rand() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }
  function shuffle(arr) { return shuffleCore(arr, Math.random); }

  /**
   * 带种子的洗牌（练习会话恢复用）。
   * 为什么不能只存「顺序 = rand」：退出或刷新后要恢复**完全相同的随机顺序**，
   * 只记「随机」二字无法复现；记完整题号序列又要占约 10 KB localStorage。
   * 方案是记一个 32 位种子 + 同一套算法重排，顺序可 100% 复现。
   * ⚠ 本算法一旦改动，历史会话恢复出的顺序会变 → 必须同时升 `SESSION_VER`。
   */
  function newSeed() { return Math.floor(Math.random() * 0x7fffffff) + 1; }
  function mulberry32(seed) {
    var t = seed >>> 0;
    return function () {
      t = (t + 0x6D2B79F5) >>> 0;
      var r = Math.imul(t ^ (t >>> 15), 1 | t);
      r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  }
  function shuffleSeeded(arr, seed) { return shuffleCore(arr, mulberry32(seed)); }
  function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }
  function debounce(fn, ms) {
    var t = 0;
    return function () {
      var args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }
  function hl(text, kw) {
    var safe = esc(text);
    if (!kw) return safe;
    try {
      return safe.replace(new RegExp('(' + escRe(esc(kw)) + ')', 'gi'), '<span class="search-hit">$1</span>');
    } catch (e) { return safe; }
  }
  /** 宽松文本比较：全角转半角、去空白与常见标点、忽略大小写 */
  function normText(s) {
    return String(s == null ? '' : s)
      .replace(/[\uFF01-\uFF5E]/g, function (ch) { return String.fromCharCode(ch.charCodeAt(0) - 0xFEE0); })
      .replace(/\u3000/g, ' ')
      .replace(/[\s,，.。;；:：、!！?？"'“”‘’()（）\[\]【】<>《》\-—_/\\|]/g, '')
      .toLowerCase();
  }
  function hashStr(s) {
    var h = 5381, i = s.length;
    while (i) h = (h * 33) ^ s.charCodeAt(--i);
    return (h >>> 0).toString(36);
  }
  function toInt(v, dflt) {
    var n = parseInt(v, 10);
    return isNaN(n) ? dflt : n;
  }

  /* ======================================================================
   * 3. 答案归一化（严格实现契约第 2 节）
   * ==================================================================== */
  function normalizeAnswer(q) {
    if (q.type === 'single') return String(q.answer).trim().toUpperCase();
    if (q.type === 'multi')  return (Array.isArray(q.answer) ? q.answer : String(q.answer).split(''))
                               .map(function (s) { return String(s).trim().toUpperCase(); })
                               .filter(Boolean).sort();
    if (q.type === 'judge')  return q.answer === true || q.answer === 'true' || q.answer === '对' || q.answer === '正确';
    if (q.type === 'fill')   return (Array.isArray(q.answer) ? q.answer : [q.answer]).map(String);
    return String(q.answer ?? '');
  }

  function answerText(q) {
    var a = q.qa;
    if (q.type === 'single') return String(a || '—');
    if (q.type === 'multi') return (a && a.length) ? a.join('') : '—';
    if (q.type === 'judge') return a ? '正确（√）' : '错误（×）';
    if (q.type === 'fill') return (a || []).map(function (t, i) { return '第' + (i + 1) + '空：' + t; }).join('\n');
    return String(a || '（略）');
  }

  /* ======================================================================
   * 4. 内置 mock 题库（≥12 题，覆盖 5 种题型；断网 / file:// 兜底）
   * ==================================================================== */
  var MOCK_BANK = {
    schema: 1,
    generatedAt: '2026-09-30T00:00:00+08:00',
    counts: { single: 5, multi: 3, judge: 4, fill: 2, short: 2, total: 16 },
    sources: ['模拟题', '提纲'],
    questions: [
      { id: 'q-9001', type: 'single', stem: '中国人民解放军诞生于哪一年？', options: ['1921年', '1927年', '1937年', '1949年'], answer: 'B', explanation: '1927年8月1日南昌起义，标志着中国共产党独立领导武装斗争和创建人民军队的开始。', source: '模拟题', chapter: '中国国防', section: '一、单选题' },
      { id: 'q-9002', type: 'single', stem: '我国现行兵役制度是（）。', options: ['义务兵役制', '志愿兵役制', '义务兵与志愿兵相结合、民兵与预备役相结合的兵役制度', '雇佣兵役制'], answer: 'C', explanation: '《中华人民共和国兵役法》规定，我国实行义务兵与志愿兵相结合、民兵与预备役相结合的兵役制度。', source: '模拟题', chapter: '中国国防', section: '一、单选题' },
      { id: 'q-9003', type: 'single', stem: '我国全民国防教育日是哪一天？', options: ['9月3日', '9月18日', '每年9月的第三个星期六', '10月1日'], answer: 'C', explanation: '《国防教育法》规定，每年9月的第三个星期六为全民国防教育日。', source: '模拟题', chapter: '中国国防', section: '一、单选题' },
      { id: 'q-9004', type: 'single', stem: '我国国防的基本类型属于（）。', options: ['扩张型', '自卫型', '联盟型', '中立型'], answer: 'B', explanation: '我国是社会主义国家，国防政策是防御性的，国防属于自卫型。', source: '提纲', chapter: '中国国防', section: '一、单选题' },
      { id: 'q-9005', type: 'single', stem: '新时期军事战略方针把军事斗争准备的基点放在（）。', options: ['打赢信息化局部战争上', '打赢大规模地面战争上', '应对核战争上', '维持边境巡逻上'], answer: 'A', explanation: '新时期军事战略方针明确把军事斗争准备基点放在打赢信息化条件下局部战争上。', source: '模拟题', chapter: '战略环境', section: '一、单选题' },
      { id: 'q-9006', type: 'multi', stem: '我国武装力量由以下哪些部分组成？', options: ['中国人民解放军现役部队', '中国人民武装警察部队', '民兵', '外国驻军'], answer: ['A', 'B', 'C'], explanation: '我国武装力量由中国人民解放军、中国人民武装警察部队和民兵组成。', source: '提纲', chapter: '中国国防', section: '二、多选题' },
      { id: 'q-9007', type: 'multi', stem: '信息化战争的主要特征包括（）。', options: ['战场空间多维化', '武器装备智能化', '指挥控制自动化', '作战样式单一化'], answer: ['A', 'B', 'C'], explanation: '信息化战争具有战场空间多维、武器装备智能、指挥控制自动化、作战样式多样化等特征。', source: '模拟题', chapter: '信息化战争', section: '二、多选题' },
      { id: 'q-9008', type: 'multi', stem: '下列属于军事高技术主要领域的有（）。', options: ['侦察监视技术', '精确制导技术', '伪装与隐身技术', '传统步兵方阵战术'], answer: ['A', 'B', 'C'], explanation: '军事高技术主要包括侦察监视、精确制导、伪装隐身、航天、电子对抗、指挥自动化等技术群。', source: '模拟题', chapter: '军事高技术', section: '二、多选题' },
      { id: 'q-9009', type: 'judge', stem: '中国人民解放军是中国共产党绝对领导下的人民军队。', options: [], answer: true, explanation: '党对军队的绝对领导是我军的根本原则和永远不变的军魂。', source: '提纲', chapter: '军事思想', section: '三、判断题' },
      { id: 'q-9010', type: 'judge', stem: '我国的国防政策是防御性的。', options: [], answer: true, explanation: '中国始终奉行防御性的国防政策，不称霸、不扩张、不谋求势力范围。', source: '提纲', chapter: '中国国防', section: '三、判断题' },
      { id: 'q-9011', type: 'judge', stem: '三湾改编确立了「支部建在连上」的原则，从组织上保证了党对军队的领导。', options: [], answer: true, explanation: '1927年三湾改编，把党的支部建在连上，实行官兵平等，确立了党对军队的绝对领导。', source: '模拟题', chapter: '军事思想', section: '三、判断题' },
      { id: 'q-9012', type: 'judge', stem: '在信息化战争中，人的因素已不再是决定战争胜负的重要因素。', options: [], answer: false, explanation: '武器装备越发展，人的因素越重要。人是战争胜负的决定性因素这一基本原理没有改变。', source: '模拟题', chapter: '信息化战争', section: '三、判断题' },
      { id: 'q-9013', type: 'fill', stem: '1927年8月1日，________起义打响了武装反抗国民党反动派的第一枪。', options: [], answer: ['南昌'], explanation: '南昌起义是中国共产党独立领导武装斗争、创建人民军队的开始。', source: '模拟题', chapter: '中国国防', section: '四、填空题' },
      { id: 'q-9014', type: 'fill', stem: '《中华人民共和国国防教育法》于________年颁布施行（填 4 位数字）。', options: [], answer: ['2001'], explanation: '《国防教育法》于2001年4月28日通过并施行。', source: '提纲', chapter: '中国国防', section: '四、填空题' },
      { id: 'q-9015', type: 'short', stem: '简述我国国防政策的基本内容。', options: [], answer: '①维护国家安全统一，保障国家发展利益；②实现国防和军队现代化；③坚持积极防御的军事战略方针；④坚持走和平发展道路，反对霸权主义和强权政治；⑤维护世界和平，反对侵略扩张。', explanation: '答题要点：防御性、维护统一、现代化、积极防御、和平发展。', source: '提纲', chapter: '中国国防', section: '五、简答题' },
      { id: 'q-9016', type: 'short', stem: '简述信息化战争的基本特征。', options: [], answer: '①战场空间由陆海空天电多维构成；②武器装备信息化、智能化；③指挥控制自动化、网络化；④作战样式多样化、非线式、非接触；⑤战争消耗大、节奏快，对信息与人才依赖度高。', explanation: '答题要点：多维战场、智能武器、自动化指挥、多样化样式、信息主导。', source: '模拟题', chapter: '信息化战争', section: '五、简答题' }
    ]
  };

  /* ======================================================================
   * 5. 题库加载：window.__QUESTION_BANK__ → fetch → mock（绝不白屏）
   * ==================================================================== */
  function isBank(b) {
    return !!b && typeof b === 'object' && Array.isArray(b.questions) && b.questions.length > 0;
  }

  function fetchJson(url) {
    return new Promise(function (resolve, reject) {
      if (typeof window.fetch !== 'function') { reject(new Error('no fetch')); return; }
      var done = false;
      var timer = setTimeout(function () { if (!done) { done = true; reject(new Error('timeout')); } }, 5000);
      window.fetch(url, { cache: 'no-store' }).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(function (j) {
        if (done) return; done = true; clearTimeout(timer); resolve(j);
      })['catch'](function (e) {
        if (done) return; done = true; clearTimeout(timer); reject(e);
      });
    });
  }

  function loadBank() {
    // ① 单文件版注入（最高优先级，且完全不发网络请求）
    try {
      if (isBank(window.__QUESTION_BANK__)) {
        return Promise.resolve({ bank: window.__QUESTION_BANK__, from: '注入题库' });
      }
    } catch (e) { /* noop */ }

    // ② 开发版 fetch（file:// 下 Safari/Chrome 会拦截，直接跳过避免控制台报错）
    var proto = (window.location && window.location.protocol) || '';
    if (proto === 'http:' || proto === 'https:') {
      return fetchJson('../data/questions.json')
        .then(function (j) {
          if (isBank(j)) return { bank: j, from: 'data/questions.json' };
          throw new Error('bad bank');
        })
        ['catch'](function () {
          return fetchJson('data/questions.json')
            .then(function (j) {
              if (isBank(j)) return { bank: j, from: 'data/questions.json' };
              throw new Error('bad bank');
            });
        })
        ['catch'](function () { return { bank: MOCK_BANK, from: '内置示例题库（mock）' }; });
    }

    // ③ 兜底 mock
    return Promise.resolve({ bank: MOCK_BANK, from: '内置示例题库（mock）' });
  }

  /**结构化解析字段的防御性归一化（非对象/数组 → {}，各字段 String 化） */
  function normalizeParts(raw) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
    return {
      answer: String(raw.answer == null ? '' : raw.answer),
      reason: String(raw.reason == null ? '' : raw.reason),
      note: String(raw.note == null ? '' : raw.note),
      ref: String(raw.ref == null ? '' : raw.ref)
    };
  }

  /** 把原始题目转成内部结构：补默认值 + 归一化答案 */
  function hydrate(raw, idx) {
    if (!raw || typeof raw !== 'object') return null;
    var type = String(raw.type || '').trim();
    if (TYPE_ORDER.indexOf(type) < 0) return null;
    var stem = String(raw.stem == null ? '' : raw.stem).trim();
    if (!stem) return null;
    var options = Array.isArray(raw.options) ? raw.options.map(function (o) { return String(o); }) : [];
    if ((type === 'single' || type === 'multi') && options.length < 2) return null;
    var q = {
      id: String(raw.id || ('q-auto-' + (idx + 1))),
      type: type,
      stem: stem,
      options: options,
      explanation: String(raw.explanation == null ? '' : raw.explanation),
      explanationParts: normalizeParts(raw.explanationParts),
      explanationSrc: String(raw.explanationSrc || ''),
      explanationRef: String(raw.explanationRef || ''),
      keyConcept: String(raw.keyConcept || ''),
      keywords: Array.isArray(raw.keywords) ? raw.keywords.slice(0, 8).map(String) : [],
      distractorWhy: (raw.distractorWhy && typeof raw.distractorWhy === 'object') ? raw.distractorWhy : {},
      source: String(raw.source || '未标注'),
      chapter: String(raw.chapter || '未分类'),
      section: String(raw.section || ''),
      // 难题标记（本轮新增）：第二版 source 的 isHard + 既有题的复核判定，缺字段一律按「非难题」
      isHard: raw.isHard === true,
      answerUncertain: raw.answerUncertain === true,
      answerRaw: raw.answer
    };
    q.qa = normalizeAnswer(raw);
    return q;
  }

  function buildBank(rawBank) {
    var list = [], seenIds = {};
    var arr = (rawBank && Array.isArray(rawBank.questions)) ? rawBank.questions : [];
    for (var i = 0; i < arr.length; i++) {
      var q = hydrate(arr[i], i);
      if (!q) continue;
      if (seenIds[q.id]) q.id = q.id + '-' + i;
      seenIds[q.id] = 1;
      list.push(q);
    }
    return list;
  }

  /* ======================================================================
   * 6. 全局状态
   * ==================================================================== */
  var State = {
    bank: null,
    questions: [],
    byId: {},
    chapters: [],
    progress: {},
    /**
     * 按日期的作答记录：{ 'YYYY-MM-DD': { n: 作答次数, ok: 答对次数 } }
     *
     * 为什么需要它（用户报告的问题 4）：
     *   `progress` 每题只存一个 `lastTs`（最后一次作答时间），导出到 JSON 的
     *   时间信息就只有它。换设备导入后，「近 7 天作答量」只能靠这些 lastTs 反推，
     *   同一题在不同日期的多次作答会丢失，于是统计看起来「对不上」。
     *   这里单独按天累计，导出/导入随之带上，时间维度就不再失真。
     */
    dailyStats: {},
    settings: null,
    exams: [],
    meta: {},
    from: '',
    route: 'home',
    sess: null,       // 当前练习或背题会话
    exam: null,       // 正在进行的考试
    lastSess: null,   // 最近一次练习会话（内存内「继续上次练习」）
    lastOrder: 'seq', // 上次实际使用的出题顺序（seq|rand），供刷新后「继续上次练习」还原
    reciteQ: '',     // 背题搜索词，与全局搜索页面隔离
    reciteSearchOpen: false,
    p: {},            // 各页面临时参数
    examTimer: 0
  };

  function initState() {
    State.progress = sanitizeProgress(loadJSON(KEY_PROGRESS, {}));
    State.settings = Object.assign({}, DEFAULT_SETTINGS, loadJSON(KEY_SETTINGS, {}));
    State.exams = sanitizeExams(loadJSON(KEY_EXAMS, []));
    State.meta = loadJSON(KEY_META, {});
    if (!State.meta || typeof State.meta !== 'object') State.meta = {};
    syncSettings();
    State.lastOrder = (State.settings.order === 'rand') ? 'rand' : 'seq';
  }

  /* ======================================================================
   * 练习会话持久化（用户报告：随机练习退出/刷新后点「继续上次练习」要接着练）
   * ----------------------------------------------------------------------
   * 设计要点（用户裁定）：
   *   · 练习与背题分别保存到各自的键，考试不写这两个键。
   *   · 恢复「退出时的原顺序 + 原位置」：顺序靠 seed 重排复现，位置靠 i，
   *     当前题的作答状态靠 res（这样退出前看到的判定与解析能原样回来）。
   *   · 退出练习**不清**这个键：下次点「继续上次练习」才有东西可恢复。
   *   · 刷新与退出走同一套：都从磁盘读，内存里的 State.lastSess 只是快路径。
   *   · 题号若已不在题库（导入/换库）→ 整个会话作废，退回新练习，不半途错位。
   * ⚠ 改 `shuffleSeeded` 的算法或这里存的东西时，必须同时升 `SESSION_VER`。
   * -------------------------------------------------------------------- */
  var sessSaveTimer = 0;
  function saveSessionSoon() {
    if (sessSaveTimer) return;                       // 60ms 合并，避免每次答题都写盘
    sessSaveTimer = setTimeout(function () { sessSaveTimer = 0; saveSession(); }, 60);
  }
  function sessionPayload(s) {
    var res = {};
    Object.keys(s.res || {}).forEach(function (k) {
      var v = s.res[k];
      res[k] = { picked: v.picked, ok: !!v.ok, ts: v.ts || 0, self: !!v.self };
    });
    var payload = {
      ver: SESSION_VER, ts: Date.now(), title: s.title || '',
      seed: toInt(s.seed, 0), order: s.order || 'seq', i: toInt(s.i, 0),
      ids: s.ids.slice(), res: res, draft: s.draft || {}, perm: s.perm || {},
      wrongMode: !!s.wrongMode, revealedRef: s.revealedRef || {}
    };
    if (s.mode === 'recite') {
      payload.mode = 'recite';
      payload.query = State.reciteQ;
      payload.searchOpen = State.reciteSearchOpen;
      payload.scrollY = Math.max(0, toInt(s.scrollY, 0));
      payload.perm = s.perm || {};
    }
    return payload;
  }
  function saveSession() {
    var s = State.sess;
    if (!s || ['practice', 'recite'].indexOf(s.mode) < 0 || !s.ids || !s.ids.length) return;
    // ⚠ 这里存的是**当前会话已排好的题目顺序**（`s.ids`），不是原始题库顺序。
    //    恢复时必须**原样使用**这份顺序（见 resumeSession），绝不能再洗一次 ——
    //    否则「洗过的顺序再洗一遍」会得到第三个顺序，永远对不上原顺序。
    saveJSON(s.mode === 'recite' ? KEY_RECITE : KEY_SESSION, sessionPayload(s));
  }
  /** 磁盘里的会话是否可用（用于首页/设置页决定是否显示「继续」入口） */
  function hasResumable() {
    // 内存快照也要确认题目仍在题库里：否则「换库后旧会话」会让入口误显示、点进去落空
    if (State.lastSess && State.lastSess.mode === 'practice' && State.lastSess.ids.length
        && State.lastSess.ids.every(function (id) { return !!State.byId[id]; })) return true;
    return !!loadSession();
  }
  function loadSession(key) {
    var d = loadJSON(key || KEY_SESSION, null);
    if (!d || typeof d !== 'object') return null;
    if (d.ver !== SESSION_VER) return null;
    if (!Array.isArray(d.ids) || !d.ids.length) return null;
    if (['seq', 'rand'].indexOf(d.order) < 0) return null;
    for (var k = 0; k < d.ids.length; k++) {
      if (typeof d.ids[k] !== 'string' || !Object.prototype.hasOwnProperty.call(State.byId, d.ids[k])) return null;
    }
    return d;
  }
  /** 草稿与排列按题型校验；旧存档缺少新增字段时自然兼容为空。 */
  function restoreSessionMap(data, ids, kind) {
    var out = {};
    if (!data || typeof data !== 'object' || Array.isArray(data)) return out;
    ids.forEach(function (id) {
      if (!Object.prototype.hasOwnProperty.call(data, id)) return;
      var q = qById(id), v = data[id];
      if (!q) return;
      var letters = q.options.map(function (_, i) { return LETTERS[i]; });
      if (kind === 'perm') {
        if (Array.isArray(v) && v.length === letters.length && v.every(function (l, i) {
          return typeof l === 'string' && letters.indexOf(l) >= 0 && v.indexOf(l) === i;
        })) out[id] = v.slice();
      } else if (kind === 'flag') {
        if (typeof v === 'boolean') out[id] = v;
      } else if (q.type === 'single') {
        if (typeof v === 'string' && letters.indexOf(v) >= 0) out[id] = v;
      } else if (q.type === 'multi') {
        if (Array.isArray(v) && v.every(function (l, i) { return letters.indexOf(l) >= 0 && v.indexOf(l) === i; })) out[id] = v.slice();
      } else if (q.type === 'judge') {
        if (typeof v === 'boolean') out[id] = v;
      } else if (q.type === 'fill') {
        if (Array.isArray(v) && v.every(function (x) { return typeof x === 'string'; })) out[id] = v.slice();
      } else if (typeof v === 'string') out[id] = v;
    });
    return out;
  }
  /** 已提交结果复用草稿的题型校验，忽略坏条目而保留其它有效作答。 */
  function restoreSessionResults(data, ids) {
    var out = {};
    if (!isRecord(data)) return out;
    ids.forEach(function (id) {
      var r = data[id], q = qById(id);
      if (!isRecord(r) || typeof r.ok !== 'boolean' || !q) return;
      var candidate = {}; candidate[id] = r.picked;
      var picks = restoreSessionMap(candidate, [id], 'draft');
      var picked = picks[id];
      if (q.type === 'short' && r.self === true && r.picked === undefined) picked = '';
      else if (!Object.prototype.hasOwnProperty.call(picks, id) || !hasAnswer(q, picked)) return;
      out[id] = { picked: picked, ok: r.ok, self: !!r.self, ts: Math.max(0, toInt(r.ts, 0)) };
    });
    return out;
  }
  /**
   * 恢复会话（首页「继续上次练习」与设置页「从下一题继续」共用这一套）。
   * 顺序**按存储原样恢复**：`d.ids` 就是退出时屏幕上那一份排好的顺序，
   * 直接拿来用即可复现「原顺序 + 原位置」，不需要（也不能）用种子重排。
   */
  function resumeSession() {
    var d = loadSession();
    if (!d) return false;
    var ids = d.ids.slice();
    var s = {
      ids: ids, i: clamp(toInt(d.i, 0), 0, ids.length - 1),
      title: d.title || '继续练习', order: d.order, mode: 'practice',
      res: restoreSessionResults(d.res, ids),
      draft: restoreSessionMap(d.draft, ids, 'draft'), perm: restoreSessionMap(d.perm, ids, 'perm'),
      wrongMode: !!d.wrongMode, revealedRef: restoreSessionMap(d.revealedRef, ids, 'flag'), startedAt: Date.now(),
      gridOpen: false, gridPage: 1, seed: toInt(d.seed, 0)
    };
    State.sess = s; State.lastSess = s; State.lastOrder = d.order;
    go('practice');
    return true;
  }

  function syncSettings() {
    var s = State.settings;
    if (['auto', 'light', 'dark'].indexOf(s.theme) < 0) s.theme = 'auto';
    if (['s', 'm', 'l', 'xl'].indexOf(s.fontSize) < 0) s.fontSize = 'm';
    if (['seq', 'rand'].indexOf(s.order) < 0) s.order = 'seq';
    s.examCount = clamp(toInt(s.examCount, 20), 1, 200);
    s.examMinutes = clamp(toInt(s.examMinutes, 30), 1, 300);
    s.shuffleOptions = !!s.shuffleOptions;
    s.autoNext = !!s.autoNext;
    if (s.explainOpen !== true && s.explainOpen !== false) s.explainOpen = null;
    if (s.sound !== true && s.sound !== false) s.sound = true;      // 脏数据回落默认开
    if (s.haptic !== true && s.haptic !== false) s.haptic = true;
    // 音量档位：非法值（含旧版本没有该字段）统一回落到「中」
    s.volume = clamp(toInt(s.volume, 2), 1, 3);
  }

  function saveSettings() { saveJSON(KEY_SETTINGS, State.settings); }
  function saveProgress() { saveJSON(KEY_PROGRESS, State.progress); }

  /* ---- 按日期的作答记录（放在 progress 的保留键下，不新增 localStorage 键）----
   * 用户报告的问题 4：每题只有一个 lastTs，导出到 JSON 的时间信息就只有它，
   * 换设备导入后「近 7 天作答量」只能靠 lastTs 反推，会失真。
   */
  var KEY_DAILY = '__daily';

  function dailyMap() {
    var d = State.progress[KEY_DAILY];
    if (!d || typeof d !== 'object') { d = {}; State.progress[KEY_DAILY] = d; }
    return d;
  }
  /** 题目记录（排除保留键）：一切「遍历 progress」的场景都必须用它 */
  function progressIds() {
    return Object.keys(State.progress).filter(function (k) { return k !== KEY_DAILY; });
  }
  /** 记一次作答到当天（ok 表示答对） */
  function bumpDaily(ok) {
    var k = dayKey(Date.now());
    var d = dailyMap();
    if (!d[k] || typeof d[k] !== 'object') d[k] = { n: 0, ok: 0 };
    d[k].n += 1;
    if (ok) d[k].ok += 1;
  }
  /** 合并两份按日期记录（按天求和；用于「合并导入」） */
  function mergeDaily(a, b) {
    var srcs = [sanitizeDaily(a), sanitizeDaily(b)];
    var out = {};
    if (!srcs.length) return out;
    srcs.forEach(function (src) {
      Object.keys(src).forEach(function (k) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(k)) return;          // 只接受日期键，防脏数据
        var x = src[k];
        if (!x || typeof x !== 'object') return;
        if (!out[k]) out[k] = { n: 0, ok: 0 };
        out[k].n += toInt(x.n, 0);
        out[k].ok += toInt(x.ok, 0);
      });
    });
    return out;
  }
  /** 清洗导入来的按日期记录 */
  function sanitizeDaily(src) {
    var out = {};
    if (!isRecord(src)) return out;
    Object.keys(src).forEach(function (k) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(k) || dayKey(new Date(k + 'T12:00:00').getTime()) !== k) return;
      var x = src[k];
      if (!isRecord(x)) return;
      var n = Math.max(0, toInt(x.n, 0));
      out[k] = { n: n, ok: clamp(toInt(x.ok, 0), 0, n) };
    });
    return out;
  }
  function saveExams() { saveJSON(KEY_EXAMS, State.exams.slice(0, 50)); }
  function saveMeta() { saveJSON(KEY_META, State.meta); }

  /* ======================================================================
   * 更新公告（开屏弹窗 + 可随时复看）
   * ----------------------------------------------------------------------
   * 规则（用户确认）：
   *   · 每个版本**只自动弹一次**，关闭后不再打扰；想看随时可从首页/导入导出页打开；
   *   · 弹窗出现在首屏（题库加载完成后），带「修复 / 新增 / 更正」三组条目。
   * 判重依据取 `window.__BUILD__.v`（打包时注入的版本号，形如 2026.10.08-2140）；
   * 取不到版本号时**不弹**，避免在没有版本概念的环境里反复弹。
   * -------------------------------------------------------------------- */
  /**
   * 本次更新公告 —— **只描述当前版本**。
   * 用户 2026-10-09 要求：每次版本更新时清除上一版的公告内容、补充当版内容，
   * 并在公告左上角标注版本号；因此这里不再累积历史版本（此前累积了 8 组，越看越乱）。
   * 发新版时：把 groups 换成该版的改动即可，noticeHtml() 会自动带上版本号。
   */
  var NOTICE = {
    "title": "本次更新",
    "intro": "完成1531题逐题检查，修订114题；参考答案调整12题。",
    "groups": [
      {
        "name": "修复",
        "items": [
          "补回多选漏项，修正军事思想层次、战斧制导和简答答案缺项。",
          "清除错题解析和错误错因，修复单选重复正确项，补充法规版本与历史时间范围。",
          "修复存疑提示被打包丢弃、网页依据不显示的问题。"
        ]
      },
      {
        "name": "说明",
        "items": [
          "六道题仍需进一步核查，解析已说明疑点，多选恢复存疑提示。",
          "题目总数1531、难题536，原有作答、收藏和错题记录保留。",
          "逐题阅读完成；证据不足的题已另列清单，不将自洽检查当成知识全部正确的证明。"
        ]
      }
    ]
  };

  function buildTagTextSafe() {
    try {
      var b = window.__BUILD__;
      return (b && b.v) ? String(b.v) : '';
    } catch (e) { return ''; }
  }

  function noticeHtml() {
    var v = buildTagTextSafe();
    // 左上角版本标识（用户要求：公告左上角标注版本号）
    var h = '<div class="notice-ver">本次更新' + (v ? ' · ' + esc(v) : '') + '</div>';
    h += '<div class="notice-intro">' + esc(NOTICE.intro) + '</div>';
    NOTICE.groups.forEach(function (g) {
      h += '<div class="notice-group"><div class="notice-gt">' + esc(g.name) + '</div><ul class="notice-ul">';
      g.items.forEach(function (t) { h += '<li>' + esc(t) + '</li>'; });
      h += '</ul></div>';
    });
    return h;
  }

  /** 手动打开公告（首页/导入导出页入口） */
  function showNotice() {
    openModal({
      title: NOTICE.title,
      html: noticeHtml(),
      buttons: [{ label: '知道了', cls: 'primary' }]
    });
  }

  /** 开屏自动弹一次（仅当本版本未弹过） */
  function maybeShowNotice() {
    var v = buildTagTextSafe();
    if (!v) return;                                  // 没有版本号就不弹
    if (State.meta.noticeSeen === v) return;
    State.meta.noticeSeen = v;
    saveMeta();
    setTimeout(showNotice, 260);                     // 等首屏渲染完再弹，避免与渲染抢帧
  }


  /* ---- 进度条目 ---- */
  function entry(id) { return State.progress[id] || null; }
  function ensureEntry(id) {
    var p = State.progress[id];
    if (!p || typeof p !== 'object') {
      p = { seen: 0, correct: 0, wrong: 0, lastTs: 0, box: 0, fav: false, wrongFlag: false };
      State.progress[id] = p;
    }
    if (typeof p.seen !== 'number') p.seen = 0;
    if (typeof p.correct !== 'number') p.correct = 0;
    if (typeof p.wrong !== 'number') p.wrong = 0;
    if (typeof p.lastTs !== 'number') p.lastTs = 0;
    if (typeof p.box !== 'number') p.box = 0;
    p.fav = !!p.fav;
    p.wrongFlag = !!p.wrongFlag;
    return p;
  }

  /** 记录一次作答（每答一题即写 localStorage） */
  function record(qid, ok, opt) {
    opt = opt || {};
    var p = ensureEntry(qid);
    p.seen += 1;
    p.lastTs = Date.now();
    bumpDaily(!!ok);      // 同步记入「按日期作答记录」：导出/导入后统计不再失真
    if (ok) {
      p.correct += 1;
      p.box = clamp((p.box || 0) + 1, 0, 5);
      if (opt.inWrongMode) p.wrongFlag = false;
    } else {
      p.wrong += 1;
      p.box = 1;
      if (opt.markWrong !== false) p.wrongFlag = true;   // 错题自动进错题本
    }
    saveProgress();
    // 徽章与统计改为「失效 + 空闲重算」，避免每次作答都同步遍历全库 1171 题
    invalidateStats();
    return p;
  }

  function toggleFav(qid) {
    var p = ensureEntry(qid);
    p.fav = !p.fav;
    if (!p.lastTs) p.lastTs = 0;
    saveProgress();
    invalidateStats();
    return p.fav;
  }

  /* ---- 派生统计 ---- */
  /* 性能开关（默认全开）。
   * 用途：让 `tools/build_perf_baseline.py` 能产出「只关这三处优化」的对照产物，
   * 用同一份题库、同一套样式量化这几处的收益；生产环境恒为 true，
   * 关闭后行为与历史实现一致（多遍历全库、每次作答重建整卡）。
   */
  var PERF_CACHE_DERIVE = true;   // 统计结果缓存
  var PERF_LEAN_BADGES = true;    // 徽章与统计合并为一次遍历
  var PERF_DIFF_MULTI = true;     // 多选题勾选差量更新（不重建整卡）

  var statsCache = null;

  /** 进度、收藏或题库发生任何变化后调用；下一次 derive() 会重算并刷新界面数字 */
  function invalidateStats() {
    statsCache = null;
    if (statsDirty) return;
    statsDirty = true;
    var run = function () {
      statsDirty = false;
      if (statsCache) return;             // 已有人算过就不重复
      updateBadges();                     // 刷新侧栏与徽章上的派生数字
    };
    // 优先空闲回调，退化到 60ms 定时器；都不影响首屏（首屏同步算一次）
    try {
      if (window.requestIdleCallback) { window.requestIdleCallback(run, { timeout: 500 }); return; }
    } catch (e) { /* noop */ }
    setTimeout(run, 60);
  }
  var statsDirty = false;

  function derive() {
    if (PERF_CACHE_DERIVE && statsCache) return statsCache;
    statsCache = deriveUncached();
    return statsCache;
  }

  /**
   * 统计分桶（按题型 / 按章节）的空对象 —— **字段必须与顶层 `d` 一致**。
   * 2026-10-09 踩过的真实坑：分桶对象漏了 `uniqueCorrect`，而累加处写 `t.uniqueCorrect += 1`，
   * `undefined + 1` 得到 NaN，于是统计页「按题型正确率」「按章节掌握情况」整列显示 `NaN%`／`NaN/x 题`
   * （顶层总正确率却正常，因为顶层字段初始化过）。
   * 抽成这一处工厂，避免下次再加字段时又漏掉某个分桶（铁律 40：逻辑只留一处）。
   */
  function emptyBucket() {
    return { total: 0, attempts: 0, correct: 0, done: 0, rate: 0, uniqueCorrect: 0, uniqueRate: 0 };
  }

  function deriveUncached() {
    var d = {
      total: State.questions.length, done: 0, attempts: 0, correct: 0,
      // 去重口径（按题目算）：做对过的题数 / 正确率。用户 2026-10-09 要求统计百分比按此口径
      uniqueCorrect: 0, uniqueRate: 0,
      rate: 0, wrong: 0, fav: 0, mastered: 0, review: 0, untouched: 0,
      byType: {}, byChapter: {}, days: []
    };
    TYPE_ORDER.forEach(function (t) { d.byType[t] = emptyBucket(); });
    State.questions.forEach(function (q) {
      var t = d.byType[q.type] || (d.byType[q.type] = emptyBucket());
      t.total += 1;
      if (!d.byChapter[q.chapter]) d.byChapter[q.chapter] = emptyBucket();
      var c = d.byChapter[q.chapter];
      c.total += 1;
      var p = State.progress[q.id];
      // 收藏与错题标记不依赖作答次数，背题时仅收藏也必须计入徽章。
      if (p && p.fav) d.fav += 1;
      if (p && p.wrongFlag) d.wrong += 1;
      if (!p || !p.seen) { d.untouched += 1; return; }
      d.done += 1; d.attempts += p.seen; d.correct += p.correct;
      if (p.correct > 0) d.uniqueCorrect += 1;
      t.done += 1; t.attempts += p.seen; t.correct += p.correct;
      if (p.correct > 0) t.uniqueCorrect += 1;
      c.done += 1; c.attempts += p.seen; c.correct += p.correct;
      if (p.correct > 0) c.uniqueCorrect += 1;
      if (p.box >= 3 && p.correct > 0) d.mastered += 1; else d.review += 1;
    });
    d.rate = pct(d.correct, d.attempts);
    d.uniqueRate = pct(d.uniqueCorrect, d.done);
    TYPE_ORDER.forEach(function (t) {
      d.byType[t].rate = pct(d.byType[t].correct, d.byType[t].attempts);
      d.byType[t].uniqueRate = pct(d.byType[t].uniqueCorrect, d.byType[t].done);
    });
    Object.keys(d.byChapter).forEach(function (k) {
      d.byChapter[k].rate = pct(d.byChapter[k].correct, d.byChapter[k].attempts);
      d.byChapter[k].uniqueRate = pct(d.byChapter[k].uniqueCorrect, d.byChapter[k].done);
    });

    // 最近 7 天做题量
    //   优先用「按日期作答记录」（_daily）：同一题在不同日期多次作答都能计上，
    //   这正是用户报告「导出/导入后统计失真」时缺的那部分信息；
    //   旧数据没有该记录时，回退到原来的「按每题最后一次作答日」口径。
    var today = new Date(); today.setHours(0, 0, 0, 0);
    for (var i = 6; i >= 0; i--) {
      var day = new Date(today.getTime() - i * 86400000);
      d.days.push({ key: dayKey(day.getTime()), label: (day.getMonth() + 1) + '/' + day.getDate(), n: 0, ok: 0 });
    }
    var idx = {};
    d.days.forEach(function (x, i) { idx[x.key] = i; });
    var daily = State.progress[KEY_DAILY];
    var hasDaily = false;
    if (daily && typeof daily === 'object') {
      Object.keys(daily).forEach(function (k) {
        if (idx[k] === undefined) return;
        var rec = daily[k] || {};
        if (toInt(rec.n, 0) > 0) hasDaily = true;
        d.days[idx[k]].n += toInt(rec.n, 0);
        d.days[idx[k]].ok += toInt(rec.ok, 0);
      });
    }
    if (!hasDaily) {
      State.questions.forEach(function (q) {
        var p = State.progress[q.id];
        if (!p || !p.lastTs) return;
        var k = dayKey(p.lastTs);
        if (idx[k] !== undefined) { d.days[idx[k]].n += 1; if (p.correct > 0) d.days[idx[k]].ok += 1; }
      });
    }
    d.hasDaily = hasDaily;
    return d;
  }

  function wrongIds() {
    return State.questions.filter(function (q) { var p = entry(q.id); return p && p.wrongFlag; })
      .map(function (q) { return q.id; });
  }
  function favIds() {
    return State.questions.filter(function (q) { var p = entry(q.id); return p && p.fav; })
      .map(function (q) { return q.id; });
  }
  /**
   * 难题专项题号（本轮新增）。
   * 依据 Q.isHard（第二版 source 的原标记 + 对既有题的复核判定），
   * 一处定义、三处引用（首页入口卡 / 练习设置页按钮 / 「难题挑战」动作）。
   */
  function hardIds() {
    return State.questions.filter(function (q) { return q.isHard; }).map(function (q) { return q.id; });
  }
  function qById(id) { return State.byId[id] || null; }

  /* ======================================================================
   * 7. UI 基础：toast / modal / 主题
   * ==================================================================== */
  function toast(msg, kind, ms) {
    var wrap = $('#toast-wrap');
    if (!wrap) return;
    var el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.textContent = String(msg);
    wrap.appendChild(el);
    setTimeout(function () {
      el.style.transition = 'opacity .2s';
      el.style.opacity = '0';
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
    }, ms || 2000);
  }

  var modalCloseCb = null;
  function openModal(opts) {
    opts = opts || {};
    var back = $('#modal-backdrop');
    if (!back) return;
    $('#modal-title').textContent = opts.title || '提示';
    var body = $('#modal-body');
    if (opts.html) body.innerHTML = opts.html; else body.textContent = opts.text || '';
    var foot = $('#modal-foot');
    foot.innerHTML = '';
    var btns = opts.buttons || [{ label: '知道了', cls: 'primary' }];
    btns.forEach(function (b) {
      var el = document.createElement('button');
      el.type = 'button';
      el.className = 'btn ' + (b.cls || 'ghost');
      el.textContent = b.label;
      el.addEventListener('click', function () {
        Feedback.fire(b.cls === 'ghost' ? 'modal:cancel' : 'modal:ok');
        closeModal();
        if (typeof b.onClick === 'function') b.onClick();
      });
      foot.appendChild(el);
    });
    back.hidden = false;
    modalCloseCb = opts.onClose || null;
    var first = foot.querySelector('.btn');
    if (first) { try { first.focus(); } catch (e) { /* noop */ } }
  }
  function closeModal() {
    var back = $('#modal-backdrop');
    if (back) back.hidden = true;
    var cb = modalCloseCb; modalCloseCb = null;
    if (typeof cb === 'function') cb();
  }
  function confirmBox(title, text, okLabel, onOk) {
    openModal({
      title: title, html: '<p>' + esc(text) + '</p>',
      buttons: [
        { label: '取消', cls: 'ghost' },
        { label: okLabel || '确定', cls: 'danger', onClick: onOk }
      ]
    });
  }

  var THEME_ICON = {
    auto: '<path d="M12 3a9 9 0 1 0 0 18z" fill="currentColor"/><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/>',
    light: '<circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22M5 5l1.7 1.7M17.3 17.3L19 19M19 5l-1.7 1.7M6.7 17.3L5 19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    dark: '<path d="M21 13a8.5 8.5 0 1 1-10-10 7 7 0 0 0 10 10z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>'
  };
  var THEME_NAME = { auto: '跟随系统', light: '浅色', dark: '深色' };
  var VOLUME_NAME = { 1: '小', 2: '中', 3: '大' };

  function applyTheme() {
    var s = State.settings;
    document.documentElement.setAttribute('data-theme', s.theme);
    document.documentElement.setAttribute('data-fs', s.fontSize);
    var ico = $('#theme-icon');
    if (ico) ico.innerHTML = THEME_ICON[s.theme] || THEME_ICON.auto;
    var btn = $('#btn-theme');
    if (btn) {
      btn.setAttribute('title', '主题：' + THEME_NAME[s.theme]);
      btn.setAttribute('aria-label', '主题：' + THEME_NAME[s.theme]);
      btn.classList.toggle('on', s.theme !== 'auto');
    }
  }
  function cycleTheme() {
    var order = ['auto', 'light', 'dark'];
    var i = order.indexOf(State.settings.theme);
    State.settings.theme = order[(i + 1) % order.length];
    saveSettings(); applyTheme();
    toast('主题：' + THEME_NAME[State.settings.theme], '', 1200);
  }
  function cycleFont() {
    var order = ['s', 'm', 'l', 'xl'], name = { s: '小', m: '标准', l: '大', xl: '特大' };
    var i = order.indexOf(State.settings.fontSize);
    State.settings.fontSize = order[(i + 1) % order.length];
    saveSettings(); applyTheme();
    toast('字号：' + name[State.settings.fontSize], '', 1200);
  }

  /* ======================================================================
   * 8. 路由
   * ==================================================================== */
  var ACT = {};
  var VIEWS = {};
  function reg(name, fn) { ACT[name] = fn; }

  function go(route, params) {
    if (!VIEWS[route]) route = 'home';
    if (route !== 'exam' && State.route === 'exam' && State.exam && State.exam.phase === 'run' && !State.exam.paused) {
      confirmBox('暂停考试并离开？', '已作答内容和剩余时间会保存，回来后可继续考试。', '暂停并离开', function () {
        pauseExam();
        go(route, params);
      });
      return;
    }
    cancelWrongSearch();
    wrongSearchComposing = false;
    flushSession(); // 切换页面前同步保存，避免延迟写盘错过最后一次翻页
    State.route = route;
    if (params) State.p = params;
    var hash = '#/' + route;
    if (window.location.hash !== hash) {
      suppressHash = true;
      window.location.hash = hash;
    }
    render(true);
  }
  var suppressHash = false;

  function currentRouteFromHash() {
    var h = (window.location.hash || '').replace(/^#\/?/, '');
    return VIEWS[h] ? h : 'home';
  }

  function updateBadges() {
    var d = derive();
    // 徽章数字直接来自同一次统计结果，省掉 wrongIds()/favIds() 两遍全库遍历
    var bw = d.wrong, bf = d.fav;
    if (!PERF_LEAN_BADGES) { bw = wrongIds().length; bf = favIds().length; }
    [['#badge-wrong', bw], ['#badge-wrong-t', bw], ['#badge-fav', bf], ['#badge-fav-t', bf]].forEach(function (pair) {
      var el = $(pair[0]);
      if (!el) return;
      el.textContent = String(pair[1]);
      el.classList.toggle('zero', pair[1] === 0);
    });
    var side = $('#side-stat');
    if (side) {
      side.innerHTML = '题库 <b>' + d.total + '</b> 题 · 已做 <b>' + d.done + '</b><br>' +
        '作答正确率 <b>' + d.rate + '%</b> · 错题 <b>' + d.wrong + '</b><br>' +
        '来源：' + esc(State.from || '—');
    }
    var sub = $('#brand-sub');
    if (sub) sub.textContent = State.from || '离线题库';
  }

  /* ----导航选中态（底部 tabbar + 桌面侧栏）------------------------
   * 视觉差异由 CSS 负责（颜色 / 图标描边加粗+药丸底 / 文字加粗），这里只负责打标记：
   *   class="active" + aria-current="page" + data-active="true|false"
   * 路由映射：答题页(practice)、背题(recite)、考试(exam) 都归属「练习」tab；
   *          搜索、导入导出是首页入口下的工具页，归属「首页」——保证任何页面都有且只有一个高亮项。
   * 侧栏本身有全部 9 个条目，按路由精确匹配（背题就高亮背题，不会同时高亮练习）。
   * -------------------------------------------------------------------- */
  var ROUTE_TAB = {
    home: 'home', practice: 'practice', recite: 'practice', exam: 'practice',
    wrong: 'wrong', fav: 'fav', stats: 'stats', search: 'home', sync: 'home'
  };

  function setNavState(el, on) {
    if (on) {
      el.classList.add('active');
      el.setAttribute('aria-current', 'page');
      el.setAttribute('data-active', 'true');
    } else {
      el.classList.remove('active');
      el.removeAttribute('aria-current');
      el.setAttribute('data-active', 'false');
    }
  }

  function updateNavActive() {
    var r = State.route;
    var tabKey = ROUTE_TAB[r] || 'home';
    $$('.tab-item').forEach(function (el) {
      setNavState(el, el.getAttribute('data-nav') === tabKey);
    });
    $$('.nav-item').forEach(function (el) {
      setNavState(el, el.getAttribute('data-nav') === r);
    });
  }

  /**构建版本号（日期+时间）。由 tools/bundle.py 注入 window.__BUILD__，读不到返回空串。 */
  function buildTagText() {
    try {
      var b = window.__BUILD__;
      if (b && typeof b === 'object' && b.v) return 'v' + String(b.v);
    } catch (e) { /* noop */ }
    return '';   // 绝不显示 undefined
  }

  /* ======================================================================
   * 9. 渲染管线
   * ==================================================================== */
  function render(scroll) {
    var route = State.route;
    var viewEl = $('#view');
    if (!viewEl) return;
    var fn = VIEWS[route] || VIEWS.home;
    var html;
    try { html = fn(); }
    catch (e) {
      html = '<div class="card"><h2 class="card-title">页面渲染出错</h2>' +
        '<div class="note">' + esc(e && e.message ? e.message : String(e)) + '</div>' +
        '<div class="btn-row mt10"><button class="btn primary" type="button" data-nav="home">返回首页</button></div></div>';
    }
    if (storageFailed) html = '<div class="card note" role="alert">浏览器无法保存数据，当前操作仅暂存在本页。' +
      '关页前请导出备份。<button class="btn sm" type="button" data-nav="sync">导出备份</button></div>' + html;
    viewEl.innerHTML = html;
    updateTopbar();
    updateBadges();
    updateNavActive();
    try { afterRender(route); } catch (e2) { /* 渲染后钩子异常不影响主流程 */ }
    var s = State.sess;
    if (route === 'recite' && s && s.mode === 'recite' && s.restoreScroll) {
      s.restoreScroll = false;
      try { window.scrollTo(0, s.scrollY || 0); } catch (e3) { /* 不支持滚动时保留题目位置 */ }
    } else if (scroll) { try { window.scrollTo(0, 0); } catch (e4) { /* noop */ } }
    // 题卡渲染时才生成选项排列，渲染后保存才能恢复相同的字母与答案。
    if (s && route === s.mode) saveSession();
    if (route === 'exam') saveExamSession();
  }

  function updateTopbar() {
    var r = State.route;
    var title = NAV_TITLE[r] || APP_NAME;
    var meta = '';
    var strip = false, cur = 0, tot = 0, stripTip = '';

    if (r === 'practice' && State.sess && State.sess.mode === 'practice') {
      // 进度标度 = **已作答去重计数**（不是「走到第几题」）。
      // 原实现用 i+1 当进度，前后跳题都会让百分比虚高，用户报告「题号当进度」即此。
      title = State.sess.title;
      tot = State.sess.ids.length;
      cur = sessAnsweredCount(State.sess);
      strip = true;
      stripTip = '正确率 ' + sessRate(State.sess) + '%';
      meta = State.sess.order === 'rand' ? '随机' : '顺序';
    } else if (r === 'recite' && State.sess && State.sess.mode === 'recite') {
      // 背题模式不计对错，进度只能是「浏览到第几题」
      title = State.sess.title; cur = State.sess.i + 1; tot = State.sess.ids.length; strip = true;
      meta = '背题';
    } else if (r === 'exam') {
      if (State.exam && State.exam.phase === 'run' && !State.exam.paused) {
        title = '模拟考试'; cur = State.exam.i + 1; tot = State.exam.ids.length; strip = true;
        meta = '<span class="timer" id="exam-clock">--:--</span>';
      } else if (State.exam && State.exam.phase === 'selfcheck') {
        title = '主观题自评'; strip = false;
      }
    } else if (r === 'stats') {
      meta = '共 ' + State.questions.length + ' 题';
    }

    var t = $('#page-title');
    if (t) t.textContent = title;
    //版本号只在首页显示，位置是顶栏最左侧（首页时返回按钮是隐藏的）
    var vt = $('#ver-tag');
    if (vt) {
      var vtext = buildTagText();
      vt.textContent = vtext;
      vt.hidden = !(vtext && r === 'home');
    }
    var m = $('#topbar-meta');
    if (m) m.innerHTML = meta + (stripTip ? '<span class="strip-tip">' + stripTip + '</span>' : '');
    var back = $('#btn-back');
    // 设置 / 提纲 / 同步也显示返回按钮（设置页是 2026-10-09 新增的页面）
    if (back) back.hidden = (r === 'home');
    if (back) back.setAttribute('aria-label', '返回');
    var ps = $('#progress-strip');
    if (ps) ps.hidden = !strip;
    if (strip) {
      var bar = $('#progress-bar'), txt = $('#progress-text');
      if (bar) bar.style.width = (tot ? Math.round(cur / tot * 100) : 0) + '%';
      if (txt) txt.textContent = (r === 'practice' ? '已答 ' : '') + cur + '/' + tot;
      if (ps) ps.setAttribute('aria-label', '进度 ' + cur + ' / ' + tot + (stripTip ? '，' + stripTip : ''));
    }
    tickClock();
  }

  function afterRender(route) {
    if (route === 'recite') renderReciteSearchResults();
    if (route === 'search') {
      var inp = $('#search-input');
      if (inp) {
        inp.value = State.p.q || '';
        if (!isTouch()) { try { inp.focus(); } catch (e) { /* noop */ } }
      }
      renderSearchResults();
    }
    if (route === 'exam' && State.exam && State.exam.phase === 'run') startExamTimer();
    if (route === 'practice' && State.sess && State.sess.mode === 'practice') focusFirstInput();
    if (route === 'recite' && State.sess && State.sess.mode === 'recite') focusFirstInput();
  }

  function isTouch() {
    return ('ontouchstart' in window) || (navigator.maxTouchPoints > 0 && window.matchMedia('(max-width:899px)').matches);
  }
  function isDesktop() {
    try { return window.matchMedia('(min-width:900px)').matches; } catch (e) { return false; }
  }
  function focusFirstInput() {
    if (!isDesktop()) return;
    var el = $('#view .fill-item .input') || $('#view .textarea');
    if (el) { try { el.focus(); } catch (e) { /* noop */ } }
  }

  /* ======================================================================
   * 10. 题目卡片组件（练习 / 考试 / 背题共用）
   * ==================================================================== */
  function dispOpts(q, sess) {
    var base = q.options.map(function (txt, i) {
      return { key: LETTERS[i], text: txt, orig: LETTERS[i] };
    });
    if (!State.settings.shuffleOptions || !sess) return base;
    if (!sess.perm) sess.perm = {};
    var perm = sess.perm[q.id];
    if (!perm) {
      perm = shuffle(q.options.map(function (_, i) { return LETTERS[i]; }));
      sess.perm[q.id] = perm;
    }
    return perm.map(function (orig, i) {
      return { key: LETTERS[i], text: q.options[LETTERS.indexOf(orig)], orig: orig };
    });
  }

  function pickHas(q, picked, letter) {
    if (q.type === 'multi') return Array.isArray(picked) && picked.indexOf(letter) >= 0;
    return picked === letter;
  }

  /** 选项乱序时，把「原始答案字母」映射成当前显示顺序下的字母 */
  function dispLetterOf(q, sess, origLetter) {
    if (!State.settings.shuffleOptions || !sess || !sess.perm) return origLetter;
    var perm = sess.perm[q.id];
    if (!perm) return origLetter;
    var i = perm.indexOf(origLetter);
    return i < 0 ? origLetter : LETTERS[i];
  }
  function answerTextDisp(q, sess) {
    if (q.type === 'single') return dispLetterOf(q, sess, q.qa);
    if (q.type === 'multi') {
      var s = (q.qa || []).map(function (l) { return dispLetterOf(q, sess, l); }).sort().join('');
      return s || '—';
    }
    return answerText(q);
  }

  /* ---- 解析正文里的选项字母映射----------------------------------
   * 问题：选项乱序后的参考答案已映射显示字母，但 `explanationParts.answer`
   * 与 `reason` 正文里的字母是**生成时写死的原始字母**，乱序后就会与选项顺序、
   * 「参考答案」行的显示字母不一致 —— 同一道题出现两套字母。
   *
   * 解法：正确答案直接来自判分字段与原始选项；正文中的选项字母只映射一次。
   * 显示映射不改动判分答案和作答存档，避免排列变化影响历史作答。
   * -------------------------------------------------------------------- */

  /**
   * 把一段文本里**指代选项的字母**换成当前显示字母。
   * 只处理明确形态，避免误伤普通文字：
   *   · `A、xxx`  —— 答录式（字母后紧跟顿号/点）
   *   · `A、B、C` —— 串列式
   *   · `故A`     —— 结论式
   * 不处理孤立的单个字母（如正文中偶然出现的 A），以免改坏文字。
   */
  function dispLettersInText(text, q, sess) {
    var s = String(text || '');
    if (!s || !State.settings.shuffleOptions || ['single', 'multi'].indexOf(q.type) < 0) return s;
    var map = function (L) { return dispLetterOf(q, sess, L); };
    // 一次扫描原文；不能将映射后的字母再送进另一轮替换。
    return s.replace(/(^|[^A-Za-z0-9])([A-J](?:[、，,\/／][A-J])+|[A-J])(?=$|[、.．:：()（）正确错误项均为都应不])|(故|选|答案|选项)([A-J](?:[、，,\/／]?[A-J])*)(?![A-Za-z0-9])/g,
      function (m, pre, letters, lead, conclusion) {
        return (pre || lead || '') + (letters || conclusion).replace(/[A-J]/g, map);
      });
  }
  function answerDispInExplain(q, sess) {
    if (q.type === 'single' || q.type === 'multi') {
      // 判分答案是唯一来源，防止解析里独立保存的字母与选项文本互相矛盾。
      var letters = q.type === 'multi' ? q.qa : [q.qa];
      return letters.map(function (L) {
        return dispLetterOf(q, sess, L) + '、' + (q.options[LETTERS.indexOf(L)] || '');
      }).join('；');
    }
    return ((q && q.explanationParts) || {}).answer || answerText(q);
  }

  /* ---- 多选答案存疑标记--------------------------------------------
   * 源 PDF 把多选题答案压成连续字母串，切分存在固有歧义，题库对这批 multi
   * 题打了 answerUncertain: true。此标记只影响展示，不影响任何判分/统计逻辑。
   * 约定：仅当 q.type === 'multi' 且 q.answerUncertain === true 时显示。
   * -------------------------------------------------------------------- */
  function isUncertain(q) {
    return !!q && q.answerUncertain === true && q.type === 'multi';
  }
  /** 轻量提示条：放在题干下方 */
  function uncertNote(q) {
    if (!isUncertain(q)) return '';
    return '<div class="uncert">⚠ 本题答案由原卷答案串自动解析，多选切分存在歧义，建议对照原卷核实</div>';
  }
  /** 行内小标记（用于「参考答案」标题旁） */
  function uncertTag() {
    return '<span class="chip warn mini">⚠ 存疑</span>';
  }
  /** 纯文本后缀（用于内联在句中的「正确答案」） */
  function uncertSuffix(q) {
    return isUncertain(q) ? '（存疑）' : '';
  }

  function renderStem(q) {
    return '<div class="q-stem">' + esc(q.stem) + '</div>';
  }

  function renderOptions(q, ctx) {
    var opts = dispOpts(q, ctx.sess);
    var html = '<div class="options">';
    opts.forEach(function (o) {
      var isAns = (q.type === 'single') ? (q.qa === o.orig) : ((q.qa || []).indexOf(o.orig) >= 0);
      var isPick = pickHas(q, ctx.picked, o.orig);
      var cls = 'opt', mk = '';
      if (ctx.reveal) {
        if (isAns) { cls += ' right'; mk = '✅'; }
        else if (isPick) { cls += ' wrong'; mk = '❌'; }
        else { cls += ' faded'; }
      } else if (isPick) { cls += ' sel'; }
      html += '<button type="button" class="' + cls + '" data-act="ans:pick" data-k="' + o.orig + '"' +
        (ctx.reveal || ctx.locked ? ' disabled' : '') + '>' +
        '<span class="opt-key">' + o.key + '</span>' +
        '<span class="opt-txt">' + esc(o.text) + '</span>' +
        (mk ? '<span class="opt-mk">' + mk + '</span>' : '') +
        '</button>';
    });
    return html + '</div>';
  }

  function renderJudge(q, ctx) {
    var two = [{ v: true, t: '正确', k: '√' }, { v: false, t: '错误', k: '×' }];
    var html = '<div class="judge-row">';
    two.forEach(function (o) {
      var isAns = (q.qa === o.v);
      var isPick = (ctx.picked === o.v) && (ctx.picked !== undefined && ctx.picked !== null);
      var cls = 'judge-btn', mk = '';
      if (ctx.reveal) {
        if (isAns) { cls += ' right'; mk = '✅'; }
        else if (isPick) { cls += ' wrong'; mk = '❌'; }
      } else if (isPick) { cls += ' sel'; }
      html += '<button type="button" class="' + cls + '" data-act="ans:pick" data-k="' + o.v + '"' +
        (ctx.reveal || ctx.locked ? ' disabled' : '') + '>' +
        '<span class="jk">' + o.k + '</span><span>' + o.t + '</span>' +
        (mk ? '<span class="opt-mk">' + mk + '</span>' : '') +
        '</button>';
    });
    return html + '</div>';
  }

  function renderFill(q, ctx) {
    var n = Math.max(1, (q.qa || []).length);
    var vals = Array.isArray(ctx.picked) ? ctx.picked : [];
    var html = '<div class="fill-list">';
    for (var i = 0; i < n; i++) {
      html += '<div class="fill-item"><span class="fill-no">' + (i + 1) + '</span>' +
        '<input class="input" type="text" inputmode="text" autocomplete="off" autocorrect="off" ' +
        'autocapitalize="off" spellcheck="false" data-act="ans:fill" data-i="' + i + '" ' +
        'placeholder="第 ' + (i + 1) + ' 空" value="' + esc(vals[i] || '') + '"' +
        (ctx.reveal || ctx.locked ? ' disabled' : '') + '></div>';
    }
    return html + '</div>';
  }

  function renderShort(q, ctx) {
    var val = typeof ctx.picked === 'string' ? ctx.picked : '';
    return '<div class="field mt10"><textarea class="textarea" data-act="ans:short" ' +
      'placeholder="在此作答（可只写要点）…"' + (ctx.reveal || ctx.locked ? ' disabled' : '') + '>' +
      esc(val) + '</textarea></div>';
  }

  function renderVerdict(ctx) {
    if (!ctx.reveal) return '';
    // 背题模式恒 reveal 且从未作答，ctx.ok 恒为 false —— 若照常渲染会显示
    // 「回答错误」，与「直接看答案」的语义冲突（用户报告的「背题模式错误提示有误」）。
    if (ctx.sess && ctx.sess.mode === 'recite') return '';
    var q = ctx.q;
    var head = ctx.ok
      ? '<div class="verdict ok"><span class="v-ico">✅</span><span class="v-txt">回答正确！</span></div>'
      : '<div class="verdict bad"><span class="v-ico">❌</span><span class="v-txt">回答错误' + verdictWhy(q, ctx) + '</span></div>';
    return head;
  }
  function verdictWhy(q, ctx) {
    if (q.type === 'short') return '（自评：不会）';
    if (q.type === 'fill') {
      var a = (q.qa || []).map(function (t, i) { return '第' + (i + 1) + '空「' + t + '」'; }).join('，');
      var u = (ctx.picked || []).map(function (t) { return String(t || '（空）'); }).join('，');
      return '<br><span class="small">你的答案：' + esc(u) + '<br>正确答案：' + esc(a) + '</span>';
    }
    var mine = '';
    if (q.type === 'multi') mine = Array.isArray(ctx.picked) ? ctx.picked.map(function (L) { return dispLetterOf(q, ctx.sess, L); }).sort().join('') : '';
    else if (q.type === 'single') mine = dispLetterOf(q, ctx.sess, String(ctx.picked || ''));
    else if (q.type === 'judge') mine = ctx.picked ? '正确' : '错误';
    return '<br><span class="small">你的答案：' + esc(mine || '（未作答）') + '　正确答案：' + esc(answerTextDisp(q, ctx.sess)) + uncertSuffix(q) + '</span>';
  }

  /* ---- 解析出处标注----------------------------------------------
   * explanationSrc: textbook | web | manual | bank | template
   *   textbook → 显示教材引用位置 explanationRef
   *   manual   → 显示「已人工校订」小 chip
   *   template → 灰字「本题库未收录直接出处」
   *   web → 显示网页出处；bank → 有明确出处时标为参考出处，不冒充独立证明
   *   空 → 不显示任何出处行
   * 纯展示，不影响判分/统计/进度。
   * ------------------------------------------------------------------ */
  var ICO_BOOK = '<svg class="ex-ico" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">' +
    '<path d="M4 4h6a3 3 0 0 1 2 1 3 3 0 0 1 2-1h6v15h-6a3 3 0 0 0-2 1 3 3 0 0 0-2-1H4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';

  function explainSrcLine(q) {
    var src = q.explanationSrc || '';
    if (src === 'textbook' || src === 'web' || src === 'bank') {
      // 出处文本优先取 explanationRef；的 explanationParts.ref 是它的冗余副本，作兜底
      var parts = q.explanationParts || {};
      var ref = String(q.explanationRef || parts.ref || '').trim();
      // 原卷说明可能没有具体引用；网页和已填写的参考出处不能在交付界面静默消失。
      if (src === 'bank' && !ref) return '';
      var label = src === 'bank' ? '参考出处：' : '依据：';
      return '<div class="ex-src">' + ICO_BOOK + '<span>' + label + esc(ref || (src === 'web' ? '网页来源' : '教材')) + '</span></div>';
    }
    if (src === 'manual') {
      var manualRef = q.explanationRef || (q.explanationParts || {}).ref || '';
      return '<div class="ex-src"><span class="chip mini">已人工校订</span>' +
        (manualRef ? '<span>依据：' + esc(manualRef) + '</span>' : '') + '</div>';
    }
    if (src === 'template') {
      return '<div class="ex-src muted">本题库未收录直接出处</div>';
    }
    return '';   // 未提供来源类型时不猜测出处。
  }

  /**
   * 解析正文：优先用结构化 explanationParts 分行渲染，字段缺失就跳过该行，
   * 不会出现「为什么：」这种空标签。
   *  - answer 正确答案 / reason 为什么 / note 提示（小字灰）
   *  - ref 不单独出块，统一由 explainSrcLine() 出「依据」行，避免重复显示两遍
   *  - 四个字段全缺失时回落到纯文本 q.explanation（保持之前的行为，数据异常也不空白）
   * 说明：题库里 explanation 本身就是 parts 的拼接（如 "正确答案：A、…\n提示：…"），
   *      所以分行渲染不会丢内容。
   */
  function explainBody(q, sess) {
    var p = q.explanationParts || {};
    var rows = '';
    if (p.answer || q.type === 'single' || q.type === 'multi') {
      //选项乱序时把解析里的答案字母同步成显示字母，避免与选项/参考答案两套字母
      rows += '<div class="ex-row"><b class="ex-label">正确答案</b><span class="ex-val">' + esc(answerDispInExplain(q, sess)) + '</span></div>';
    }
    if (p.reason) {
      //正文若按字母指代选项（如「故A、B正确」），同样要跟着乱序走
      rows += '<div class="ex-row"><b class="ex-label">为什么</b><span class="ex-val">' + esc(dispLettersInText(p.reason, q, sess)) + '</span></div>';
    }
    if (p.note) {
      rows += '<div class="ex-row ex-sub"><b class="ex-label">提示</b><span class="ex-val">' + esc(dispLettersInText(p.note, q, sess)) + '</span></div>';
    }
    if (!rows) return esc(dispLettersInText(q.explanation || '（原题库未提供解析）', q, sess)) + explainSrcLine(q);
    return rows + explainSrcLine(q);
  }

  /**
   * 解析默认展开还是折叠（；本版按用户要求改为**默认展开**）。
   *  - 题目卡片路径（练习/背题/简答）：未记录偏好时**默认展开**；
   *    用户手动折叠过后就沿用他的选择（`settings.explainOpen`）。
   *  - 成绩单路径（route === 'exam'）：**一律使用各区块自己的默认值**，忽略偏好
   *    —— 否则用户展开过解析，成绩单的「全部题目回顾」也会跟着展开，
   *    把「错题回顾默认展开、全部回顾默认折叠」的设计冲掉。
   */
  function explainOpenNow(dfltOpen) {
    // 提纲页的小节默认折叠：新提纲有 200+ 个小节，全展开会拖慢首屏也难浏览
    if (State.route === 'outline') return false;
    if (State.route !== 'exam') {
      var v = State.settings.explainOpen;
      if (v === true || v === false) return v;
      return true;                     // 默认展开（用户要求：解析与依据默认显示）
    }
    return !!dfltOpen;
  }

  /**
   * 解析块（默认折叠，点标题条展开）：练习 / 背题 / 简答自评 / 考试成绩单 四处共用。
   * dfltOpen = 该上下文的默认展开态（成绩单「错题回顾」传 true，其余传 false）。
   * 显隐只用 CSS（.explain.open .ex-body）控制，解析内容始终留在 DOM 中，不删除不重插。
   */
  function explainBlock(q, dfltOpen, sess) {
    var open = explainOpenNow(dfltOpen);
    return '<div class="explain fold' + (open ? ' open' : '') + '">' +
      '<button type="button" class="ex-head" data-act="explain:toggle" aria-expanded="' + (open ? 'true' : 'false') + '">' +
      '<span class="ex-ttl">📖 解析与依据</span>' +
      '<span class="ex-arrow" aria-hidden="true">' + (open ? '▴' : '▾') + '</span>' +
      '</button>' +
      '<div class="ex-body">' + explainBody(q, sess) + '</div>' +
      '</div>';
  }

  /** 折叠 / 展开解析：原地切换，不重绘整页（保住滚动位置与选中文本） */
  reg('explain:toggle', function (el) {
    var next = el.getAttribute('aria-expanded') !== 'true';
    var box = (el.closest ? el.closest('.explain') : null) || el.parentNode;
    if (box && box.classList) box.classList.toggle('open', next);
    el.setAttribute('aria-expanded', next ? 'true' : 'false');
    var arrow = el.querySelector ? el.querySelector('.ex-arrow') : null;
    if (arrow) arrow.textContent = next ? '▴' : '▾';
    // 题目卡片路径（练习/背题/简答）记住偏好，下一题自动沿用；
    // 成绩单两张列表不写偏好，恒定保持「错题回顾默认展开、全部回顾默认折叠」。
    if (State.route !== 'exam') { State.settings.explainOpen = next; saveSettings(); }
  });

  /* ---- 关键词解析：只在「实际答错」时显示 --------------------------
   * 数据来自题库新增字段：
   *   keyConcept    考点（短名词短语）
   *   keywords      关键词数组
   *   distractorWhy { 选项字母: 该选项为什么不对 }，只含错误选项
   * 纯展示：不参与判分 / 错题本 / 进度 / 考试计分。
   * -------------------------------------------------------------------- */

  /**
   * 是否「已作答且答错」——复用现有判分结果，不重新判定：
   *   ctx.reveal !== true → 还没判分（含背题模式恒 reveal 但未作答的情况由下一行兜住）
   *   ctx.ok === true     → 答对 → 不显示
   *   hasAnswer(...)      → 未作答（背题模式 picked 为 undefined）→ 不显示
   */
  function isWrongAnswered(q, ctx) {
    if (!ctx || ctx.reveal !== true || ctx.ok) return false;
    return hasAnswer(q, ctx.picked);
  }

  /** 用户实际选中的选项字母（内部统一用原始字母，与 q.qa / distractorWhy 同一套） */
  function pickedLetters(q, picked) {
    if (q.type === 'multi') return Array.isArray(picked) ? picked : [];
    if (q.type === 'single') return (typeof picked === 'string' && picked) ? [picked] : [];
    return [];   // judge / fill / short 没有选项干扰项
  }

  /** 只列「用户选错的那几项」，不列全部错误选项 */
  function distractorLines(q, ctx) {
    var why = q.distractorWhy || {};
    var out = '';
    pickedLetters(q, ctx.picked).forEach(function (L) {
      // 多选少选会判错，但选中的正确项不属于干扰项。
      var correct = q.type === 'multi' ? q.qa : [q.qa];
      if (correct && correct.indexOf(L) >= 0) return;
      var txt = why[L];
      if (txt == null || txt === '') return;
      var idx = LETTERS.indexOf(L);
      var opt = (idx >= 0 && q.options[idx] != null) ? String(q.options[idx]) : '';
      out += '<div class="kw-why"><b>' + esc(dispLetterOf(q, ctx.sess, L)) + '.</b> ' + esc(opt) +
        '<span class="kw-why-txt"> — ' + esc(String(txt)) + '</span></div>';
    });
    return out;
  }

  /** 关键词解析块：答错时默认展开（此刻最需要），答对 / 未作答返回空串 */
  function kwBlock(q, ctx) {
    if (!isWrongAnswered(q, ctx)) return '';
    var html = '';
    var concept = String(q.keyConcept || '').trim();
    var kws = Array.isArray(q.keywords) ? q.keywords : [];
    if (concept) html += '<div class="kw-concept">考点：' + esc(concept) + '</div>';
    if (kws.length) {
      html += '<div class="chips">' + kws.map(function (k) {
        return '<span class="chip mini">' + esc(String(k)) + '</span>';
      }).join('') + '</div>';
    }
    var why = distractorLines(q, ctx);
    if (why) html += '<div class="kw-sub">你选的选项为什么不对</div>' + why;
    if (!html) return '';
    return '<div class="note kw-block"><div class="kw-title">关键词解析</div>' + html + '</div>';
  }

  function renderAnswerBox(q, ctx) {
    if (!ctx.reveal) return '';
    return '<div class="answer-box"><div class="ab-title">参考答案' + (isUncertain(q) ? ' ' + uncertTag() : '') + '</div>' + esc(answerTextDisp(q, ctx.sess)) + '</div>' + explainBlock(q, false, ctx.sess) + kwBlock(q, ctx);
  }

  function favBtn(q) {
    var p = entry(q.id);
    var on = !!(p && p.fav);
    return '<button type="button" class="fav-btn' + (on ? ' on' : '') + '" data-act="fav" data-id="' + esc(q.id) + '" ' +
      'title="收藏 / 取消收藏（快捷键 F）">' +
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 10l6.1-.9z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>' +
      '<span>' + (on ? '已收藏' : '收藏') + '</span></button>';
  }

  function submitBtn(q, ctx) {
    if (ctx.reveal || ctx.locked || ctx.showSelf || ctx.examRunning) return '';
    if (q.type === 'multi') return '<div class="btn-row mt16"><button class="btn primary block" type="button" data-act="ans:submit">提交答案</button></div>';
    if (q.type === 'fill') return '<div class="btn-row mt16"><button class="btn primary block" type="button" data-act="ans:submit">提交答案</button></div>';
    if (q.type === 'short') {
      return '<div class="btn-row mt16"><button class="btn primary block" type="button" data-act="ans:reveal">查看参考答案并自评</button></div>';
    }
    return '';
  }

  /** 简答题自评按钮 */
  function selfCheck(q, ctx) {
    if (!ctx.showSelf) return '';
    return '<div class="selfcheck">' +
      '<button class="btn primary" type="button" data-act="ans:self" data-v="1">✅ 我答对了</button>' +
      '<button class="btn danger" type="button" data-act="ans:self" data-v="0">❌ 没答对</button>' +
      '</div>';
  }

  function hintLine(q, ctx) {
    if (ctx.reveal || ctx.locked) return '';
    if (ctx.examRunning) return '<div class="note mt10">' +
      (q.type === 'short' ? '作答自动保存；交卷后对照参考答案自评。' : '作答自动保存；交卷后统一评分。') + '</div>';
    if (q.type === 'single') return '<div class="note mt10">点选即判分（快捷键 <kbd>1</kbd>–<kbd>' + Math.min(9, q.options.length) + '</kbd>）</div>';
    if (q.type === 'multi') return '<div class="note mt10">多选，选好后点「提交答案」（快捷键 <kbd>1</kbd>–<kbd>' + Math.min(9, q.options.length) + '</kbd> 选择，<kbd>Enter</kbd> 提交）</div>';
    if (q.type === 'judge') return '<div class="note mt10">判断对错（快捷键 <kbd>1</kbd> 正确 / <kbd>2</kbd> 错误）</div>';
    if (q.type === 'fill') return '<div class="note mt10">填空，注意每空单独填写</div>';
    return '';
  }

  /**
   * ctx = { q, idx, total, sess, picked, reveal, ok, locked, showSelf, extraHead, footer }
   */
  function renderCard(q, ctx) {
    var html = '<div class="card q-card">';
    html += '<div class="q-head">' +
      '<span class="q-idx">' + (ctx.total ? (ctx.idx + 1) + ' / ' + ctx.total : '') + '</span>' +
      '<span class="chip pri">' + (TYPE_LABEL[q.type] || q.type) + '</span>' +
      (q.isHard ? '<span class="chip hard" title="难题">难题</span>' : '') +
      (q.chapter && q.chapter !== '未分类' ? '<span class="chip">' + esc(q.chapter) + '</span>' : '') +
      '<span class="grow"></span>' + favBtn(q) + '</div>';
    html += renderStem(q);
    html += uncertNote(q);
    if (q.type === 'single' || q.type === 'multi') html += renderOptions(q, ctx);
    else if (q.type === 'judge') html += renderJudge(q, ctx);
    else if (q.type === 'fill') html += renderFill(q, ctx);
    else if (q.type === 'short') html += renderShort(q, ctx);
    html += renderVerdict(ctx);
    html += submitBtn(q, ctx);
    html += selfCheck(q, ctx);
    html += hintLine(q, ctx);
    html += renderAnswerBox(q, ctx);
    if (ctx.extraFoot) html += ctx.extraFoot;
    return html + '</div>';
  }

  function navBtns(ctx) {
    var last = ctx.idx >= ctx.total - 1;
    return '<div class="nav-btns">' +
      '<button class="btn" type="button" data-act="nav:prev"' + (ctx.idx <= 0 ? ' disabled' : '') + '>← 上一题</button>' +
      '<button class="btn primary" type="button" data-act="nav:next">' + (last ? '完成本轮 ✓' : '下一题 →') + '</button>' +
      '</div>';
  }

  /* ---- 答题卡：按 100 题一页分页（用户要求，避免一次铺开 1171 个格子）---------
   * 设计要点：
   *   · 只渲染当前页的格子，DOM 从 1171 个降到 ≤100 个；
   *   · 格子编号用**全局题号**（第 2 页第一格是 101），跳题直接映射到 ids 下标；
   *   · 打开答题卡时自动落到包含当前题的那一页；
   *   · 页码栏超过 12 页时首尾各留 2 个 + 省略号，中段围绕当前页 2 个，避免又铺一排按钮。
   * ------------------------------------------------------------------------- */
  var GRID_PAGE_SIZE = 100;
  var GRID_PAGE_BTNS = 12;

  function gridCard(list, ctx) {
    var total = list.length;
    var totalPages = Math.max(1, Math.ceil(total / GRID_PAGE_SIZE));
    var page = clamp(toInt(ctx.page, 1), 1, totalPages);
    var from = (page - 1) * GRID_PAGE_SIZE;
    var to = Math.min(from + GRID_PAGE_SIZE, total);
    var cells = '<div class="qgrid">';
    for (var i = from; i < to; i++) {
      var q = list[i];
      if (!q) continue;
      var cls = 'qcell';
      var r = ctx.resOf(q.id);
      if (r) cls += ctx.revealRes ? (r.ok ? ' right' : ' wrong') : ' done';
      if (i === ctx.idx) cls += ' cur';
      var p = entry(q.id);
      if (p && p.fav) cls += ' fav';
      cells += '<button type="button" class="' + cls + '" data-act="nav:jump" data-i="' + i + '">' + (i + 1) + '</button>';
    }
    cells += '</div>';
    // 页码栏：每页按钮直接写题号区间
    var nums = [];
    if (totalPages <= GRID_PAGE_BTNS) {
      for (var k = 1; k <= totalPages; k++) nums.push(k);
    } else {
      var keep = {};
      [1, 2, totalPages - 1, totalPages].forEach(function (n) { if (n >= 1 && n <= totalPages) keep[n] = 1; });
      for (var j = page - 2; j <= page + 2; j++) { if (j >= 1 && j <= totalPages) keep[j] = 1; }
      var sorted = Object.keys(keep).map(Number).sort(function (a, b) { return a - b; });
      var prev = 0;
      sorted.forEach(function (n) {
        if (prev && n - prev > 1) nums.push('…');
        nums.push(n);
        prev = n;
      });
    }
    var pages = '<div class="grid-pages">';
    nums.forEach(function (n) {
      if (n === '…') { pages += '<span class="gp-gap">…</span>'; return; }
      var a = (n - 1) * GRID_PAGE_SIZE + 1, b2 = Math.min(n * GRID_PAGE_SIZE, total);
      pages += '<button type="button" class="gp' + (n === page ? ' on' : '') + '"' +
        (n === page ? ' aria-current="page"' : '') +
        ' data-act="grid:page" data-v="' + n + '">' + a + '-' + b2 + '</button>';
    });
    pages += '</div>';
    return '<div class="card"><div class="card-title">答题卡<span class="card-sub">' +
      (from + 1) + '-' + to + ' / 共 ' + total + ' 题</span></div>' +
      cells + pages +
      '<div class="legend mt10"><span><i class="done"></i>已答</span><span><i class="todo"></i>未答</span>' +
      '<span><i class="cur"></i>当前</span>' + (ctx.revealRes ? '<span><i class="right"></i>正确</span><span><i class="wrong"></i>错误</span>' : '') +
      '<span>★ 收藏</span></div></div>';
  }

  /* ======================================================================
   * 11. 首页
   * ==================================================================== */
  function entryCard(act, icon, title, sub, extra) {
    return '<button type="button" class="entry-card" ' + (act ? 'data-act="' + act + '"' : '') + (extra || '') + '>' +
      '<span class="entry-ico">' + icon + '</span>' +
      '<span class="entry-txt"><strong>' + title + '</strong><small>' + sub + '</small></span>' +
      '<svg class="chev" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '</button>';
  }
  var ICO = {
    seq: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    exam: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="13" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 9v4l3 2M9 2h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    recite: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2.6" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
    wrong: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    fav: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 10l6.1-.9z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16.5 16.5L21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    stats: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    sync: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h13l-3-3M20 16H7l3 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    gear: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.6 1.6M16.4 16.4L18 18M18 6l-1.6 1.6M7.6 16.4L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
  };

  VIEWS.home = function () {
    var d = derive();
    var qs = State.questions;
    var html = '';

    if (!qs.length) {
      return '<div class="card"><div class="empty"><div class="empty-ico">📭</div>' +
        '<strong>题库为空</strong><p>没有成功载入任何题目，请检查 data/questions.json 或使用单文件版。</p></div></div>';
    }

    // 概览
    html += '<div class="card">' +
      '<div class="card-title">题库总览<span class="card-sub">' + esc(State.from) + '</span></div>' +
      '<div class="grid grid-4">' +
      '<div class="stat pri"><b>' + d.total + '</b><span>总题数</span></div>' +
      '<div class="stat"><b>' + d.done + '</b><span>已做</span></div>' +
      '<div class="stat ' + (d.uniqueRate >= 60 ? 'ok' : (d.done ? 'bad' : '')) + '"><b>' + d.uniqueRate + '%</b><span>总正确率</span></div>' +
      '<div class="stat"><b>' + d.wrong + '</b><span>错题</span></div>' +
      '</div>' +
      '<div class="chips mt10">' +
      TYPE_ORDER.map(function (t) {
        var n = d.byType[t] ? d.byType[t].total : 0;
        return n ? '<span class="chip">' + TYPE_SHORT[t] + ' ' + n + '</span>' : '';
      }).join('') +
      '<span class="chip pri">章节 ' + Object.keys(d.byChapter).length + '</span>' +
      '<span class="chip">收藏 ' + d.fav + '</span>' +
      '</div>' +
      '<div class="btn-row mt16">' +
      // 「继续上次练习」按可恢复会话判定：退出练习后即使本次没答过题，也应该能接着上次练
      (hasResumable() || d.attempts ? '<button class="btn primary" type="button" data-act="home:continue">继续上次练习</button>' : '') +
      '<button class="btn' + (hasResumable() || d.attempts ? '' : ' primary') + '" type="button" data-act="home:startall">从第一题开始</button>' +
      '</div>' +
      (d.attempts ? '<div class="small muted mt6">复习进度：掌握 ' + d.mastered + ' 题 · 待复习 ' + d.review + ' 题（共 ' + d.total + ' 题）</div>' : '') +
      '</div>';

    // 入口（练习的四个模式原本各占一张卡、但点击后都只是跳转到同一个练习设置页，
    //   属于重复入口，合并为一张「顺序练习」卡 —— 四种模式在设置页里选，能力一个不少）
    // 底边栏已能直达的「练习 / 错题本 / 收藏夹 / 统计」不再重复放在首页（用户 2026-10-09 要求）
    html += '<div class="entry-grid">' +
      entryCard('exam:new', ICO.exam, '模拟考试', '计时 · 答题卡 · 百分制评分') +
      entryCard('recite:start', ICO.recite, '背题模式', '直接看题干、答案与解析') +
      entryCard('', ICO.search, '题目搜索', '按题干关键词查找', ' data-nav="search"') +
      entryCard('hard:start', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.4 6.8 19.2l1-5.9L3.5 9.2l5.9-.8z"/></svg>', '难题挑战', hardIds().length ? '共 ' + hardIds().length + ' 道易错/易混题' : '题库尚未标记难题') +
      entryCard('', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16M4 12h16M4 19h10"/><circle cx="19" cy="19" r="1.6"/></svg>', '复习提纲', '最新提纲 · 章节/小节 · 可导出 Markdown', ' data-nav="outline"') +
      entryCard('', ICO.sync, '导入 / 导出', 'iPhone ↔ Windows 手动同步', ' data-nav="sync"') +
      entryCard('', ICO.gear, '设置', '文字大小 · 主题 · 声音与震动', ' data-nav="settings"') +
      '</div>';

    html += '<div class="card mt16"><div class="card-title">使用提示</div>' +
      '<div class="small dim">' +
      '· 答题进度自动保存在本机（localStorage），关闭页面不会丢失。<br>' +
      '· iPhone 上可「添加到主屏幕」，离线全屏使用。<br>' +
      '· 音效与震动可在「导入 / 导出 · 声音与震动」里开关。' +
      '</div>' +
      '<div class="btn-row mt10"><button class="btn sm" type="button" data-act="notice:show">查看本次更新公告</button></div>' +
      '</div>';
    return html;
  };

  /* ======================================================================
   * 12. 练习（顺序 / 随机 / 章节 / 题型）
   * ==================================================================== */
  function startSession(ids, title, order, mode) {
    flushSession();
    if (mode === 'recite') { State.reciteQ = ''; State.reciteSearchOpen = false; }
    var ord = order || 'seq';
    // 随机顺序用一个种子固定下来：退出/刷新后靠它重排出**同一顺序**（见 shuffleSeeded 注释）
    var seed = (ord === 'rand') ? newSeed() : 0;
    var list = (ord === 'rand') ? shuffleSeeded(ids, seed) : ids.slice();
    if (!list.length) { toast('没有可练习的题目', 'bad'); return; }
    State.sess = {
      ids: list, i: 0, title: title, order: ord, mode: mode || 'practice',
      res: {}, draft: {}, perm: {}, startedAt: Date.now(), gridOpen: false, wrongMode: false,
      gridPage: 1, seed: seed, scrollY: 0
    };
    // 只有练习模式才更新「上次练习」指针：背题/考试不该让首页误显示「继续上次练习」
    // （注意判据是 mode，不是 ord —— ord 存的是 'seq'|'rand'）
    if ((mode || 'practice') === 'practice') State.lastSess = State.sess;
    // 记住「上次实际用的出题顺序」。首页的「继续上次练习」在页面刷新后要靠它
    // 才能回到随机练习 —— 否则会硬编码落回顺序练习（用户报告的问题 3）。
    State.lastOrder = (ord === 'rand') ? 'rand' : 'seq';
    // 立刻落盘：练习写 KEY_SESSION（退出后仍可「继续上次练习」），
    // 背题写 KEY_RECITE（刷新后回到原题；退出即作废，见 sess:exit）。
    saveSession();
    go(mode === 'recite' ? 'recite' : 'practice');
  }

  function startAll(mode, order) {
    startSession(State.questions.map(function (q) { return q.id; }),
      (order === 'rand' ? '随机练习' : '顺序练习') + ' · 全部 ' + State.questions.length + ' 题',
      order || State.settings.order, mode || 'practice');
  }

  VIEWS.practice = function () {
    if (State.sess && State.sess.mode === 'practice' && State.sess.ids.length) return practiceRun();
    return practiceSetup();
  };

  function practiceSetup() {
    var d = derive();
    var html = '';
    html += '<div class="card">' +
      '<div class="card-title">练习设置</div>' +
      '<div class="field"><label>出题顺序</label>' +
      '<div class="seg">' +
      '<button type="button" class="' + (State.settings.order === 'seq' ? 'active' : '') + '" data-act="set:order" data-v="seq">顺序</button>' +
      '<button type="button" class="' + (State.settings.order === 'rand' ? 'active' : '') + '" data-act="set:order" data-v="rand">随机</button>' +
      '</div></div>' +
      '<div class="switch-row"><div class="sw-txt"><strong>选项乱序</strong><small>打乱 A/B/C/D 显示顺序，避免背位置</small></div>' +
      '<button type="button" class="switch" role="switch" aria-checked="' + (State.settings.shuffleOptions ? 'true' : 'false') + '" data-act="set:switch" data-k="shuffleOptions" aria-label="选项乱序"></button></div>' +
      '<div class="switch-row"><div class="sw-txt"><strong>答对自动下一题</strong><small>答错时停留查看解析</small></div>' +
      '<button type="button" class="switch" role="switch" aria-checked="' + (State.settings.autoNext ? 'true' : 'false') + '" data-act="set:switch" data-k="autoNext" aria-label="答对自动下一题"></button></div>' +
      '<div class="btn-row mt16">' +
      '<button class="btn primary block" type="button" data-act="prac:start" data-mode="all">开始练习（全部 ' + d.total + ' 题）</button>' +
      '</div>' +
      '<div class="small muted mt6">已做 ' + d.done + ' / ' + d.total + ' 题 · 累计作答 ' + d.attempts + ' 次 · 正确率 ' + d.rate + '%</div>' +
      '</div>';

    // 断点续练：有可恢复的练习会话（内存或磁盘）就能接着练，不必非得答过题
    var lastQ = lastAnswered();
    var resumable = hasResumable();
    if (resumable || lastQ) {
      html += '<div class="card"><div class="card-title">继续上次练习</div>' +
        '<div class="list-item"><span class="li-idx">上次</span><span class="li-body">' +
        '<strong class="clamp2">' + esc(lastQ ? lastQ.stem : '上次的练习还没做完') + '</strong>' +
        '<small>' + (lastQ
          ? TYPE_LABEL[lastQ.type] + ' · ' + esc(lastQ.chapter) + ' · ' + fmtDate(entry(lastQ.id) ? entry(lastQ.id).lastTs : 0)
          : '会从退出时的题目继续，出题顺序保持不变') +
        '</small>' +
        '</span></div>' +
        '<div class="btn-row mt10"><button class="btn primary block" type="button" data-act="prac:continue">从下一题继续</button></div></div>';
    }

    // 按章节
    var chs = Object.keys(d.byChapter).sort(function (a, b) {
      var ai = State.questions.findIndex(function (q) { return q.chapter === a; });
      var bi = State.questions.findIndex(function (q) { return q.chapter === b; });
      return ai - bi;
    });
    html += '<div class="card"><div class="card-title">按章节练习<span class="card-sub">' + chs.length + ' 章</span></div>';
    if (!chs.length) html += '<div class="empty small">暂无章节信息</div>';
    else {
      html += '<div class="grid grid-2">';
      chs.forEach(function (c) {
        var s = d.byChapter[c];
        html += '<button type="button" class="list-item" data-act="prac:chapter" data-v="' + esc(c) + '">' +
          '<span class="li-body"><strong>' + esc(c) + '</strong>' +
          '<small>' + s.done + '/' + s.total + ' 已做 · 正确率 ' + s.rate + '%</small></span></button>';
      });
      html += '</div>';
    }
    html += '</div>';

    // 按题型
    html += '<div class="card"><div class="card-title">按题型练习</div><div class="grid grid-2">';
    TYPE_ORDER.forEach(function (t) {
      var s = d.byType[t];
      if (!s || !s.total) return;
      html += '<button type="button" class="list-item" data-act="prac:type" data-v="' + t + '">' +
        '<span class="li-body"><strong>' + TYPE_LABEL[t] + '</strong>' +
        '<small>' + s.done + '/' + s.total + ' 已做 · 正确率 ' + s.rate + '%</small></span></button>';
    });
    html += '</div></div>';

    // 难题专项（本轮新增）：与首页「难题挑战」同一个动作，避免逻辑出现两处
    var hn = hardIds().length;
    html += '<div class="card"><div class="card-title">难题挑战' +
      '<span class="card-sub">' + hn + ' 题</span></div>' +
      '<div class="small dim">需要记住精确数字/年份、易混概念辨析、多选易漏选的题目。</div>' +
      '<div class="btn-row mt10"><button class="btn' + (hn ? ' primary' : '') + ' block" type="button" data-act="hard:start"' +
      (hn ? '' : ' disabled') + '>' + (hn ? '开始难题挑战（' + hn + ' 题）' : '题库尚未标记难题') + '</button></div></div>';

    // 错题 / 收藏 快捷
    var w = wrongIds().length, f = favIds().length;
    if (w || f) {
      html += '<div class="card"><div class="card-title">专项练习</div><div class="btn-row">' +
        (w ? '<button class="btn danger" type="button" data-act="wrong:redo">重做错题（' + w + '）</button>' : '') +
        (f ? '<button class="btn" type="button" data-act="fav:practice">练习收藏（' + f + '）</button>' : '') +
        '</div></div>';
    }
    return html;
  }

  function lastAnswered() {
    var best = null, ts = -1;
    State.questions.forEach(function (q) {
      var p = entry(q.id);
      if (p && p.lastTs > ts) { ts = p.lastTs; best = q; }
    });
    return best;
  }

  function sessCurrent() {
    var s = State.sess;
    if (!s || !s.ids.length) return null;
    s.i = clamp(s.i, 0, s.ids.length - 1);
    return qById(s.ids[s.i]);
  }

  function practiceRun() {
    var s = State.sess;
    var q = sessCurrent();
    if (!q) { State.sess = null; return practiceSetup(); }
    var r = s.res[q.id];
    var reveal = !!r || !!s.revealAll;
    var picked = r ? r.picked : getDraft(s, q.id);
    var locked = false;
    var ctx = {
      q: q, idx: s.i, total: s.ids.length, sess: s,
      picked: picked, reveal: reveal, ok: r ? r.ok : false, locked: locked,
      showSelf: !!(s.revealedRef && s.revealedRef[q.id] && !r)
    };
    if (q.type === 'short' && !reveal && s.revealedRef && s.revealedRef[q.id]) {
      ctx.extraFoot = '<div class="answer-box mt10"><div class="ab-title">参考答案</div>' + esc(answerTextDisp(q, s)) + '</div>' + explainBlock(q, false, s);
    }
    var html = renderCard(q, ctx);
    html += '<div class="row between mt10 small muted"><span>正确率 ' +
      sessRate(s) + '% · 已答 ' + Object.keys(s.res).length + '/' + s.ids.length + '</span>' +
      '<span class="row"><button class="btn sm ghost" type="button" data-act="grid:toggle">答题卡</button>' +
      '<button class="btn sm ghost" type="button" data-act="sess:exit">退出练习</button></span></div>';
    html += navBtns({ idx: s.i, total: s.ids.length });
    if (s.gridOpen) html += gridCard(s.ids.map(qById), { idx: s.i, page: s.gridPage,
      resOf: function (id) { return s.res[id]; }, revealRes: true });
    return html;
  }

  function sessRate(s) {
    var n = 0, ok = 0;
    Object.keys(s.res).forEach(function (k) { n++; if (s.res[k].ok) ok++; });
    return pct(ok, n);
  }

  /**
   * 已作答题数（去重）。
   * 练习进度用它当分子：同一题反复作答只计一次，前后跳题不会让进度虚高。
   * 之所以每次现算而不缓存：s.res 是「按题 id 记录本轮结果」的字典，
   * Object.keys 对一个 ≤1171 项的字典是极轻的操作，省掉一份容易失配的缓存状态。
   */
  function sessAnsweredCount(s) {
    return (s && s.res) ? Object.keys(s.res).length : 0;
  }

  function getDraft(container, qid) {
    if (container.draft && Object.prototype.hasOwnProperty.call(container.draft, qid)) return container.draft[qid];
    return undefined;
  }
  function setDraft(container, qid, v) {
    if (container === State.exam && (container.phase !== 'run' || container.paused)) return;
    if (!container.draft) container.draft = {};
    container.draft[qid] = v;
    if (container === State.sess && container.mode === 'practice') saveSession();
    else if (container === State.exam) saveExamSession();
  }

  function hasAnswer(q, v) {
    if (v === undefined || v === null) return false;
    if (q.type === 'single') return !!v;
    if (q.type === 'multi') return Array.isArray(v) && v.length > 0;
    if (q.type === 'judge') return typeof v === 'boolean';
    if (q.type === 'fill') return Array.isArray(v) && v.some(function (x) { return String(x == null ? '' : x).trim() !== ''; });
    return String(v).trim() !== '';
  }

  function arrEq(a, b) {
    a = (a || []).slice().sort(); b = (b || []).slice().sort();
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  function fillOk(picked, qa) {
    var u = (picked || []).map(function (x) { return normText(x); });
    var a = (qa || []).map(function (x) { return normText(x); });
    var ok = true, i;
    for (i = 0; i < a.length; i++) { if ((u[i] || '') !== a[i]) { ok = false; break; } }
    if (ok) return true;
    var ju = u.filter(Boolean).join(''), ja = a.filter(Boolean).join('');
    if (ju && ju === ja) return true;                       // 多空答案写进一个空
    if (a.length === 1 && u.filter(Boolean).length === 1) return u.filter(Boolean)[0] === a[0];
    return false;
  }

  function judgeAnswer(q, picked) {
    if (q.type === 'single') return String(picked || '').toUpperCase() === q.qa;
    if (q.type === 'multi') return arrEq(picked, q.qa);
    if (q.type === 'judge') return (picked === true) === (q.qa === true);
    if (q.type === 'fill') return fillOk(picked, q.qa);
    return false;
  }

  /* ---- 练习答题动作 ---- */
  function submitPractice(q, picked, ok, selfAssessed) {
    var s = State.sess;
    if (!s) return;
    s.res[q.id] = { picked: picked, ok: ok, ts: Date.now(), self: !!selfAssessed };
    if (s.revealedRef) delete s.revealedRef[q.id];
    record(q.id, ok, { inWrongMode: !!s.wrongMode });
    setDraft(s, q.id, picked);
    if (s.lastSession) State.lastSess = s;
    if (s.mode === 'practice') saveSessionSoon();          // 作答记录落盘：继续时能看到上次的判定与解析
    render(false);
    Feedback.result(ok);          // 答对/答错音由真实判分结果驱动（练习唯一判分出口）
    if (!ok) toast('答错了，已记入错题本', 'bad', 1600);
    if (ok && State.settings.autoNext && q.type !== 'short') {
      var at = s.i;
      setTimeout(function () {
        if (State.route !== 'practice' || !State.sess || State.sess !== s) return;
        if (s.i !== at || !s.res[q.id]) return;
        if (s.i < s.ids.length - 1) { s.i++; render(true); }
      }, 700);
    }
  }

  reg('ans:pick', function (el) {
    var k = el.getAttribute('data-k');
    if (State.route === 'exam') { examPick(k); return; }
    var s = State.sess;
    if (!s) return;
    var q = sessCurrent();
    if (!q || s.res[q.id]) return;
    var revealRef = q.type === 'short' && s.revealedRef && s.revealedRef[q.id];
    if (revealRef) return;
    if (q.type === 'single') { submitPractice(q, k, judgeAnswer(q, k)); return; }
    if (q.type === 'judge') { var b = (k === 'true'); submitPractice(q, b, judgeAnswer(q, b)); return; }
    if (q.type === 'multi') {
      var cur = getDraft(s, q.id);
      if (!Array.isArray(cur)) cur = [];
      var i = cur.indexOf(k);
      if (i >= 0) cur.splice(i, 1); else cur.push(k);
      cur.sort();
      setDraft(s, q.id, cur);
      // 差量更新：只切换选项按钮的选中态，不重建整张卡片。
      // 选项按钮用 data-k 携带**原始选项字母**，与 draft 内部使用的字母同一套，
      // 因此可以直接比对。原先每次勾选都 render(false) 整卡重建，
      // 在 1171 题的会话里是不必要的 DOM 与样式重算开销。
      var opts = PERF_DIFF_MULTI ? $$('#view .q-card .opt[data-k]') : [];
      if (!opts.length) { render(false); return; }
      opts.forEach(function (b) {
        b.classList.toggle('sel', pickHas(q, cur, b.getAttribute('data-k')));
      });
      updateGridCell();
    }
  });

  reg('ans:fill', function (el) {
    var i = toInt(el.getAttribute('data-i'), 0);
    var s = State.route === 'exam' ? State.exam : State.sess;
    if (!s) return;
    var q = State.route === 'exam' ? examCurrent() : sessCurrent();
    if (!q) return;
    var cur = getDraft(s, q.id);
    if (!Array.isArray(cur)) cur = [];
    cur[i] = el.value;
    setDraft(s, q.id, cur);
    updateGridCell();
  });

  reg('ans:short', function (el) {
    var s = State.route === 'exam' ? State.exam : State.sess;
    if (!s) return;
    var q = State.route === 'exam' ? examCurrent() : sessCurrent();
    if (!q) return;
    setDraft(s, q.id, el.value);
    updateGridCell();
  });

  reg('ans:submit', function () {
    if (State.route === 'exam') { examSaveDraft(); return; }
    if (State.route === 'recite') { move(1); return; }
    var s = State.sess;
    if (!s) return;
    var q = sessCurrent();
    if (!q || s.res[q.id]) return;
    var picked = getDraft(s, q.id);
    if (!hasAnswer(q, picked)) { toast('请先作答', 'bad', 1400); return; }
    if (q.type === 'multi') picked = (picked || []).slice().sort();
    submitPractice(q, picked, judgeAnswer(q, picked));
  });

  reg('ans:reveal', function () {
    var s = State.sess;
    if (!s) return;
    var q = sessCurrent();
    if (!q) return;
    if (!s.revealedRef) s.revealedRef = {};
    s.revealedRef[q.id] = true;
    render(false);
  });

  reg('ans:self', function (el) {
    if (State.route === 'exam') { examSelf(el); return; }
    var s = State.sess;
    if (!s) return;
    var q = sessCurrent();
    if (!q || s.res[q.id]) return;
    var ok = el.getAttribute('data-v') === '1';
    submitPractice(q, getDraft(s, q.id), ok, true);
  });

  reg('nav:next', function () { move(1); });
  reg('nav:prev', function () { move(-1); });
  reg('nav:jump', function (el) { jumpTo(toInt(el.getAttribute('data-i'), 0)); });
  reg('grid:toggle', function () {
    var c = State.route === 'exam' ? State.exam : State.sess;
    if (!c) return;
    c.gridOpen = !c.gridOpen;
    // 打开时自动落到「包含当前题」的那一页，否则 1000+ 题时用户还得自己翻页找
    if (c.gridOpen) c.gridPage = Math.floor(toInt(c.i, 0) / GRID_PAGE_SIZE) + 1;
    render(false);
  });

  /** 答题卡翻页（只重绘当前页格子，不改变题目顺序与作答状态） */
  reg('grid:page', function (el) {
    var c = State.route === 'exam' ? State.exam : State.sess;
    if (!c) return;
    c.gridPage = clamp(toInt(el.getAttribute('data-v'), 1), 1, 9999);
    render(true);      // 滚回页面顶部：翻页后置顶才看得见新一页
  });

  function activeContainer() {
    if (State.route === 'exam') return State.exam;
    return State.sess;
  }

  /** 仅更新当前答题卡格子的「已答」状态（不重绘，避免输入框失焦） */
  function updateGridCell() {
    var c = activeContainer();
    if (!c || !c.ids || !c.ids.length) return;
    var q = qById(c.ids[c.i]);
    if (!q) return;
    // 输入过程中只改计数文本，答题卡收起时同样更新，保留焦点与输入法状态。
    var count = State.route === 'exam' ? $('#exam-answered') : null;
    if (count) count.textContent = '已答 ' + examAnsweredCount(c) + '/' + c.ids.length + ' 题';
    // 分页只渲染100格，按全局题号找格子；练习需提交才算已答。
    var el = $('#view .qcell[data-i="' + c.i + '"]');
    if (!el) return;
    el.classList.toggle('done', State.route === 'exam' && hasAnswer(q, getDraft(c, q.id)));
  }
  function move(d) {
    var c = activeContainer();
    if (!c) return;
    if (!c.ids.length) return;
    if (State.route === 'exam') {
      if (c.phase !== 'run' || c.paused) return;
      examSaveDraft();
    }
    var ni = c.i + d;
    if (ni < 0) { toast('已经是第一题', '', 1200); return; }
    if (ni >= c.ids.length) {
      if (State.route === 'practice') {
        Feedback.play('complete');    // 一轮练习完成：四音上行琶音
        openModal({
          title: '本轮练习完成',
          html: '<p>共 ' + c.ids.length + ' 题，作答 ' + Object.keys(c.res).length + ' 题，正确率 ' + sessRate(c) + '%。</p>',
          buttons: [
            { label: '再练一轮', cls: 'ghost', onClick: function () { startSession(c.ids, c.title, c.order, c.mode); } },
            { label: '返回首页', cls: 'primary', onClick: function () { State.sess = null; go('home'); } }
          ]
        });
      } else { toast('已经是最后一题', '', 1200); }
      return;
    }
    c.i = ni;
    if (State.route === 'practice') saveSessionSoon();
    else if (State.route === 'recite') { c.scrollY = 0; saveSession(); }
    render(true);
  }
  function jumpTo(i) {
    var c = activeContainer();
    if (!c || isNaN(i)) return;
    if (State.route === 'exam') {
      if (c.phase !== 'run' || c.paused) return;
      examSaveDraft();
    }
    c.i = clamp(i, 0, c.ids.length - 1);
    if (State.route === 'practice') saveSessionSoon();
    else if (State.route === 'recite') { c.scrollY = 0; saveSession(); }
    render(true);
  }

  reg('sess:exit', function () {
    // 退出只清内存会话；磁盘里的会话保留，下次「继续上次练习」才能接着练
    var name = State.route === 'recite' ? '背题' : '练习';
    confirmBox('退出' + name, '当前' + name + '进度已自动保存，确定退出吗？', '退出', function () {
      flushSession();
      State.sess = null;
      go('home');
    });
  });

  reg('fav', function (el) {
    var id = el.getAttribute('data-id');
    var on = toggleFav(id);
    toast(on ? '已加入收藏' : '已取消收藏', '', 1200);
    var btn = el;
    btn.classList.toggle('on', on);
    var sp = btn.querySelector('span');
    if (sp) sp.textContent = on ? '已收藏' : '收藏';
    updateBadges();
    if (State.route === 'fav') render(false); // 取消收藏后立即更新行与页头数量
  });

  /* ---- 练习入口动作 ---- */
  reg('set:order', function (el) {
    State.settings.order = el.getAttribute('data-v') === 'rand' ? 'rand' : 'seq';
    saveSettings(); render(false);
  });
  reg('set:switch', function (el) {
    var k = el.getAttribute('data-k');
    State.settings[k] = !State.settings[k];
    saveSettings();
    el.setAttribute('aria-checked', State.settings[k] ? 'true' : 'false');
    if (k === 'shuffleOptions') {
      State.sess = null;
      toast(State.settings[k] ? '选项乱序已开启' : '选项乱序已关闭', '', 1400);
    }
  });
  /** 音效 / 震动开关：开启时补一次反馈，让用户立刻听到/感觉到 */
  reg('set:feedback', function (el) {
    var k = el.getAttribute('data-k');
    if (k !== 'sound' && k !== 'haptic') return;
    State.settings[k] = !State.settings[k];
    saveSettings();
    el.setAttribute('aria-checked', State.settings[k] ? 'true' : 'false');
    if (State.settings[k]) Feedback.fire('set:switch');   // 只在“打开”时给一次确认反馈
    else if (k === 'sound') Feedback.pauseSilentTrack();  // 关音效时释放常驻静音音轨，别占着系统音频会话
  });
  /**
   * 音量档位（小 / 中 / 大）。
   * 切换后立即用响度最高的 complete 音播一次，让用户当场听出差别；
   * 若音效总开关是关的，只保存不发声（不擅自替用户打开音效）。
   */
  reg('set:volume', function (el) {
    var v = clamp(toInt(el.getAttribute('data-v'), DEFAULT_VOLUME), 1, 3);
    State.settings.volume = v;
    saveSettings();
    $$('#view .seg [data-act="set:volume"]').forEach(function (b) {
      b.classList.toggle('active', toInt(b.getAttribute('data-v'), 0) === v);
    });
    if (State.settings.sound) Feedback.play('complete');
    toast('音量已设为' + VOLUME_NAME[v], '', 1200);
  });
  reg('prac:start', function () {
    startAll('practice', State.settings.order);
  });
  reg('prac:chapter', function (el) {
    var c = el.getAttribute('data-v');
    var ids = State.questions.filter(function (q) { return q.chapter === c; }).map(function (q) { return q.id; });
    startSession(ids, '章节 · ' + c, State.settings.order, 'practice');
  });
  reg('prac:type', function (el) {
    var t = el.getAttribute('data-v');
    var ids = State.questions.filter(function (q) { return q.type === t; }).map(function (q) { return q.id; });
    startSession(ids, TYPE_LABEL[t] + '专项', State.settings.order, 'practice');
  });
  /** 难题挑战（首页入口卡与练习设置页共用同一个动作，逻辑只此一处） */
  reg('hard:start', function () {
    var ids = hardIds();
    if (!ids.length) { toast('题库尚未标记难题', 'bad'); return; }
    startSession(ids, '难题挑战 · ' + ids.length + ' 题', State.settings.order, 'practice');
  });
  reg('prac:continue', function () {
    // ① 有可恢复的会话（磁盘里存了顺序 seed + 位置 + 作答记录）→ 原样接着练
    if (resumeSession()) return;
    // ② 没有会话：按「最后作答的下一题」继续（保持旧行为，也用于首次带着历史进度进入的情况）
    var lastQ = lastAnswered();
    // 用「上次实际用的出题顺序」而不是硬编码 seq：回答问题时用过随机，继续时也应是随机。
    var ord = (State.lastOrder === 'rand') ? 'rand' : State.settings.order;
    if (!lastQ) { startAll('practice', ord); return; }
    var ids = State.questions.map(function (q) { return q.id; });
    var seed = 0;
    if (ord === 'rand') { seed = newSeed(); ids = shuffleSeeded(ids, seed); }
    var idx = ids.indexOf(lastQ.id);
    var s = {
      ids: ids, i: (idx + 1) % ids.length,
      title: '继续练习（从第 ' + (((idx + 1) % ids.length) + 1) + ' 题开始）',
      order: ord, mode: 'practice', res: {}, draft: {}, perm: {},
      startedAt: Date.now(), gridOpen: false, gridPage: 1, seed: seed
    };
    State.sess = s; State.lastSess = s; State.lastOrder = ord;
    saveSession();
    go('practice');
  });
  reg('home:continue', function () {
    // 内存快照 → 磁盘会话 → 兜底：三条路径最终都落在同一个恢复语义上
    if (State.lastSess && State.lastSess.ids.length && State.lastSess.mode === 'practice') {
      State.sess = State.lastSess;
      State.lastOrder = State.lastSess.order || State.lastOrder;
      go('practice');
      return;
    }
    if (resumeSession()) return;
    ACT['prac:continue']();
  });
  reg('home:startall', function () { startAll('practice', 'seq'); });
  reg('home:mode', function () { go('practice'); });

  /* ======================================================================
   * 13. 背题模式
   * ==================================================================== */
  /** 离开、关页时同步保存阅读位置；滚动事件只合并写盘。 */
  function flushSession() {
    if (State.route === 'exam') { examSaveDraft(); saveExamSession(); }
    var s = State.sess;
    if (!s || State.route !== s.mode) return; // 主页的残留会话不属于当前阅读状态
    if (State.route === 'recite' && s && s.mode === 'recite') {
      s.scrollY = Math.max(0, toInt(window.scrollY || window.pageYOffset, 0));
    }
    saveSession();
  }

  /** 索引完成后恢复背题，缺失任一题号则整份作废，避免位置错位。 */
  function restoreReciteSession() {
    var d = loadSession(KEY_RECITE);
    if (!d || d.mode !== 'recite') return false;
    var perm = restoreSessionMap(d.perm, d.ids, 'perm');
    State.sess = {
      ids: d.ids.slice(), i: clamp(toInt(d.i, 0), 0, d.ids.length - 1),
      title: d.title || '继续背题', order: d.order, mode: 'recite',
      res: {}, draft: {}, perm: perm, startedAt: Date.now(),
      gridOpen: false, gridPage: 1, seed: toInt(d.seed, 0),
      scrollY: Math.max(0, toInt(d.scrollY, 0)), restoreScroll: true
    };
    State.reciteQ = typeof d.query === 'string' ? d.query : '';
    State.reciteSearchOpen = !!d.searchOpen;
    return true;
  }

  /** 搜索只定位当前题集，不重建或重排背题会话。 */
  function reciteScope() {
    var s = State.sess;
    return s && s.mode === 'recite' ? s.ids : State.questions.map(function (q) { return q.id; });
  }
  function reciteSearchCard() {
    return '<div class="card recite-search"><div class="field mb0">' +
      '<label for="recite-search-input">搜索背题题目<span class="card-sub">当前范围 ' + reciteScope().length + ' 题</span></label>' +
      '<input class="input" id="recite-search-input" data-act="recite:search" type="search" aria-label="搜索背题题目"' +
      ' placeholder="题干 / 选项 / 章节；多个关键词用空格分隔" autocomplete="off" value="' + esc(State.reciteQ) + '"></div>' +
      '<div class="row wrap mt10"><button class="btn sm ghost" type="button" data-act="recite:searchclear">清空搜索</button>' +
      '<button class="btn sm ghost" type="button" data-act="recite:searchshow">显示搜索结果</button></div>' +
      '<div id="recite-search-results" class="recite-search-results" aria-live="polite"></div></div>';
  }
  function renderReciteSearchResults() {
    var box = $('#recite-search-results');
    if (!box) return;
    var kws = State.reciteQ.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!kws.length || !State.reciteSearchOpen) { box.innerHTML = ''; return; }
    var hits = reciteScope().map(qById).filter(function (q) { return q && searchMatch(q, kws); });
    if (!hits.length) { box.innerHTML = '<p class="small muted mt10">没有找到相关题目，请换个关键词；当前背题位置保持不变。</p>'; return; }
    var html = '<div class="small muted mt10">找到 ' + hits.length + ' 题，点击题目继续背题。</div><div class="list">';
    hits.slice(0, 200).forEach(function (q) {
      html += '<button class="list-item" type="button" data-act="recite:searchgo" data-id="' + esc(q.id) + '">' +
        '<span class="li-idx">' + (TYPE_SHORT[q.type] || '') + '</span><span class="li-body"><strong class="clamp3">' +
        hl(q.stem, kws[0]) + '</strong><small>' + esc(q.chapter) + '</small></span></button>';
    });
    box.innerHTML = html + '</div>' + (hits.length > 200 ? '<p class="small muted">仅显示前 200 条，请增加关键词缩小范围。</p>' : '');
  }
  reg('recite:search', null); // input 只重绘结果，保留焦点与中文输入法状态
  reg('recite:searchclear', function () {
    State.reciteQ = ''; State.reciteSearchOpen = false;
    var el = $('#recite-search-input');
    if (el) { el.value = ''; el.focus(); }
    renderReciteSearchResults(); saveSession();
  });
  reg('recite:searchshow', function () { State.reciteSearchOpen = true; renderReciteSearchResults(); saveSession(); });
  reg('recite:searchgo', function (el) {
    var id = el.getAttribute('data-id'), ids = reciteScope(), idx = ids.indexOf(id);
    if (idx < 0 || !qById(id)) return;
    if (!State.sess || State.sess.mode !== 'recite') {
      var query = State.reciteQ;
      startSession(ids, '背题模式 · 全部 ' + ids.length + ' 题', 'seq', 'recite');
      State.reciteQ = query;
    }
    State.reciteSearchOpen = false;
    jumpTo(idx);
  });

  VIEWS.recite = function () {
    var s = State.sess;
    if ((!s || s.mode !== 'recite') && restoreReciteSession()) s = State.sess;
    if (!s || s.mode !== 'recite' || !s.ids.length) {
      var d = derive();
      var html = reciteSearchCard() + '<div class="card"><div class="card-title">背题模式</div>' +
        '<p class="small dim">直接显示题干、正确答案与解析，适合考前快速过一遍。' +
        '可用 <kbd>←</kbd> <kbd>→</kbd> 或下方按钮翻题。</p>' +
        '<div class="btn-row mt10"><button class="btn primary block" type="button" data-act="recite:start">开始背题（全部 ' + d.total + ' 题）</button></div></div>';
      var chs = Object.keys(d.byChapter);
      if (chs.length) {
        html += '<div class="card"><div class="card-title">按章节背题</div><div class="grid grid-2">';
        chs.forEach(function (c) {
          html += '<button type="button" class="list-item" data-act="recite:chapter" data-v="' + esc(c) + '">' +
            '<span class="li-body"><strong>' + esc(c) + '</strong><small>' + d.byChapter[c].total + ' 题</small></span></button>';
        });
        html += '</div></div>';
      }
      if (d.wrong) {
        html += '<div class="card"><div class="btn-row"><button class="btn danger" type="button" data-act="wrong:recite">背错题（' + d.wrong + '）</button></div></div>';
      }
      return html;
    }
    var q = sessCurrent();
    if (!q) { State.sess = null; rawDel(KEY_RECITE); return VIEWS.recite(); }
    var ctx = { q: q, idx: s.i, total: s.ids.length, sess: s, picked: undefined, reveal: true, ok: false, locked: true };
    var html = reciteSearchCard() + renderCard(q, ctx);
    html += '<div class="row between mt10 small muted"><span>背题模式 · 不计入正确率</span>' +
      '<div class="row wrap"><button class="btn sm ghost" type="button" data-act="recite:new">从头背全部</button>' +
      '<button class="btn sm ghost" type="button" data-act="sess:exit">退出</button></div></div>';
    html += navBtns({ idx: s.i, total: s.ids.length });
    return html;
  };

  reg('recite:start', function () {
    if (restoreReciteSession()) { go('recite'); return; }
    ACT['recite:new']();
  });
  reg('recite:new', function () {
    startSession(State.questions.map(function (q) { return q.id; }), '背题模式 · 全部 ' + State.questions.length + ' 题', 'seq', 'recite');
  });
  reg('recite:chapter', function (el) {
    var c = el.getAttribute('data-v');
    var ids = State.questions.filter(function (q) { return q.chapter === c; }).map(function (q) { return q.id; });
    startSession(ids, '背题 · ' + c, 'seq', 'recite');
  });

  /* ======================================================================
   * 19. 复习提纲（2026-10-09 起：内容来自【26最新改版】军理课提纲 PDF）
   * ----------------------------------------------------------------------
   * 为什么换掉旧实现：用户要求「把复习提纲模块的内容改为加入新的提纲 PDF」。
   *   旧实现是按题库解析反推的知识点索引；这份 PDF 是教材配套的正式提纲，
   *   带重点标注、章节完整，复习价值更高，因此**替换**而非并列。
   * 数据来源：`data/outline-2026.json`（由 tools/build_outline_data.py 从 PDF 生成），
   *   打包时内嵌为 `window.__OUTLINE__`；HTTP 下若内嵌缺失会回退 fetch 该文件。
   * 数据结构（稳定契约，外部脚本可依赖）：
   *   { source, basis, generatedAt,
   *     stats: { chapters, sections, subs, chars },
   *     chapters: [{ chapter, chars, sections: [
   *        { section, chars, text, subs: [{ title, text }] } ] }] }
   * ⚠ 兼容性说明：`window.__JLX__.outline()` 仍可调用，但返回**上面这份新结构**；
   *   旧的 `{chapter,total,sections:[{points:[…]}]}` 形态自本轮起废弃。
   * ==================================================================== */
  var OUTLINE_EMPTY = { source: '', basis: '', stats: {}, chapters: [] };
  var outlineFetchStarted = false;

  /** 取提纲数据：内嵌优先，HTTP 下回退 fetch（file:// 不能 fetch，故只走内嵌） */
  function loadOutlineData() {
    if (State.outlineData) return State.outlineData;
    var d = window.__OUTLINE__;
    if (d && d.chapters && d.chapters.length) { State.outlineData = d; return d; }
    if (outlineFetchStarted) return OUTLINE_EMPTY;
    outlineFetchStarted = true;
    if (window.location.protocol !== 'file:' && typeof window.fetch === 'function') {
      window.fetch('data/outline-2026.json', { cache: 'no-store' }).then(function (r) {
        return r.ok ? r.json() : null;
      }).then(function (j) {
        if (j && j.chapters && j.chapters.length) {
          State.outlineData = j;
          if (State.route === 'outline') render(true);   // 数据到位后刷新当前页
        }
      })['catch'](function () { /* 内嵌缺失且 fetch 失败：保留空结构，页面会给出提示 */ });
    }
    return OUTLINE_EMPTY;
  }

  /** 新提纲 → Markdown（供「复制为 Markdown / 导出 .md」） */
  function buildOutlineMarkdown(data) {
    data = data || loadOutlineData();
    var L = ['# ' + (data.source || '军事理论复习提纲'), ''];
    if (data.basis) L.push('> 依据：' + data.basis, '');
    (data.chapters || []).forEach(function (c) {
      L.push('## ' + c.chapter, '');
      (c.sections || []).forEach(function (s) {
        L.push('### ' + s.section, '');
        var units = (s.subs && s.subs.length) ? s.subs : [{ title: '', text: s.text || '' }];
        units.forEach(function (u) {
          if (u.title) L.push('**' + u.title + '**', '');
          if (u.text) L.push(u.text, '');
        });
      });
    });
    return L.join('\n');
  }


  VIEWS.outline = function () {
    var data = loadOutlineData();
    var chapters = data.chapters || [];
    if (!chapters.length) {
      return listEmpty('📑', '提纲数据未载入',
        '公开版未包含提纲数据。你可以自己准备一份 data/outline-2026.json（结构见仓库 ' +
        'docs/04-outline-data.md，仓库里也带了空壳示例），重新打包后即可使用。');
    }
    var chs = chapters.map(function (c) { return c.chapter; });
    var focus = (State.p && State.p.chapter) || '';
    if (focus && chs.indexOf(focus) < 0) focus = '';

    var st = data.stats || {};
    var head = '<div class="card"><div class="card-title">复习提纲<span class="card-sub">' +
      (st.chapters || chapters.length) + ' 章 · ' + (st.sections || '?') + ' 节 · ' +
      (st.subs || '?') + ' 小节</span></div>' +
      '<div class="small dim">内容来自「' + esc(data.source || '军理课提纲') + '」' +
      (data.basis ? '，依据 ' + esc(data.basis) : '') + '。点小节标题展开正文（默认折叠）。</div>' +
      '<div class="chips mt10">' +
      '<button type="button" class="chip' + (focus ? '' : ' pri') + '" data-act="ol:filter" data-v="">全部</button>' +
      chs.map(function (c) {
        return '<button type="button" class="chip' + (focus === c ? ' pri' : '') +
          '" data-act="ol:filter" data-v="' + esc(c) + '">' + esc(c) + '</button>';
      }).join('') + '</div>' +
      '<div class="btn-row mt10">' +
      '<button class="btn" type="button" data-act="ol:copy">复制为 Markdown</button>' +
      '<button class="btn ghost" type="button" data-act="ol:download">导出 .md 文件</button>' +
      '</div></div>';

    var cards = '';
    chapters.forEach(function (c) {
      if (focus && c.chapter !== focus) return;
      cards += '<div class="card"><div class="card-title">' + esc(c.chapter) +
        '<span class="card-sub">' + ((c.sections || []).length) + ' 节</span></div>';
      (c.sections || []).forEach(function (s, si) {
        cards += '<div class="ol-sec"><div class="ol-sec-t">' + esc(s.section) + '</div>';
        var units = (s.subs && s.subs.length) ? s.subs : [{ title: '', text: s.text || '' }];
        units.forEach(function (u, ui) {
          var uid = 'ol-' + si + '-' + ui;
          cards += '<div class="explain fold">' +
            '<button type="button" class="ex-head" data-act="ol:toggle" data-v="' + uid + '"' +
            ' aria-expanded="false" aria-controls="' + uid + '">' +
            '<span class="ex-ttl">' + esc(u.title || ('小节 ' + (ui + 1))) + '</span>' +
            '<span class="ex-arrow" aria-hidden="true">▾</span></button>' +
            '<div class="ex-body" id="' + uid + '">' + esc(u.text || '') + '</div>' +
            '</div>';
        });
        cards += '</div>';
      });
      cards += '</div>';
    });
    return head + cards;
  };


  reg('ol:filter', function (el) {
    State.p.chapter = el.getAttribute('data-v') || '';
    render(false);
  });
  /** 手动打开「本次更新公告」（首页与导入导出页入口共用） */
  reg('notice:show', function () { showNotice(); });
  reg('ol:copy', function () { copyText(buildOutlineMarkdown(), '提纲已复制到剪贴板（Markdown）'); });
  reg('ol:download', function () {
    var ok = downloadText('军事理论复习提纲.md', buildOutlineMarkdown());
    toast(ok ? '已导出 军事理论复习提纲.md' : '当前浏览器不支持直接下载，请用「复制为 Markdown」', ok ? 'ok' : 'bad', 2600);
  });
  /** 提纲小节展开/收起：只切 class，不重渲染（200+ 小节重建 DOM 会明显卡顿） */
  reg('ol:toggle', function (el) {
    var box = el.parentNode;
    if (!box) return;
    var open = box.classList.toggle('open');
    el.setAttribute('aria-expanded', open ? 'true' : 'false');
    var ar = el.querySelector('.ex-arrow');
    if (ar) ar.textContent = open ? '▴' : '▾';
  });


  /* ======================================================================
   * 14. 模拟考试
   * ==================================================================== */
  function examScopePool(scope, withShort) {
    return State.questions.filter(function (q) {
      if (!withShort && q.type === 'short') return false;
      if (scope === 'wrong') { var p = entry(q.id); return !!(p && p.wrongFlag); }
      if (scope === 'new') { var p2 = entry(q.id); return !(p2 && p2.seen > 0); }
      return true;
    });
  }

  /** 存档一律表示已暂停；刷新、关页后不会自行倒计时或交卷。 */
  function saveExamSession() {
    var e = State.exam;
    if (!e || (e.phase !== 'run' && e.phase !== 'selfcheck')) return;
    var active = e.phase === 'run' && !e.paused;
    var now = Date.now();
    saveJSON(KEY_EXAM_SESSION, {
      ver: SESSION_VER, ids: e.ids.slice(), i: e.i, phase: e.phase, paused: true,
      draft: e.draft || {}, perm: e.perm || {}, self: e.self || {},
      minutes: e.minutes, withShort: e.withShort, scope: e.scope,
      gridOpen: e.gridOpen, gridPage: e.gridPage, autoSubmit: !!e.autoSubmit,
      remainingMs: active ? Math.max(0, e.endTs - now) : e.remainingMs,
      elapsedMs: (e.elapsedMs || 0) + (active ? Math.max(0, now - e.segmentStartTs) : 0)
    });
  }

  /** 外部存档先验证题号、时间和各题答案类型，再重建判分状态。 */
  function loadExamSession() {
    var d = loadJSON(KEY_EXAM_SESSION, null);
    if (!d || d.ver !== SESSION_VER || ['run', 'selfcheck'].indexOf(d.phase) < 0 ||
        !Array.isArray(d.ids) || !d.ids.length || d.ids.length > 200 ||
        new Set(d.ids).size !== d.ids.length || !d.ids.every(function (id) {
          return typeof id === 'string' && Object.prototype.hasOwnProperty.call(State.byId, id);
        }) || typeof d.remainingMs !== 'number' || !isFinite(d.remainingMs) || d.remainingMs < 0 ||
        typeof d.elapsedMs !== 'number' || !isFinite(d.elapsedMs) || d.elapsedMs < 0) return null;
    var minutes = clamp(toInt(d.minutes, 30), 1, 300);
    var e = {
      ids: d.ids.slice(), i: clamp(toInt(d.i, 0), 0, d.ids.length - 1), phase: d.phase, paused: true,
      draft: restoreSessionMap(d.draft, d.ids, 'draft'), perm: restoreSessionMap(d.perm, d.ids, 'perm'),
      self: restoreSessionMap(d.self, d.ids, 'flag'), minutes: minutes, withShort: !!d.withShort,
      scope: ['all', 'wrong', 'new'].indexOf(d.scope) >= 0 ? d.scope : 'all',
      gridOpen: d.gridOpen !== false, gridPage: Math.max(1, toInt(d.gridPage, 1)),
      remainingMs: Math.min(d.remainingMs, minutes * 60000), elapsedMs: d.elapsedMs,
      autoSubmit: !!d.autoSubmit, res: null
    };
    if (e.phase === 'selfcheck') { e.durationMs = e.elapsedMs; buildExamResults(e); }
    return e;
  }

  /** 仅累计实际考试时间，暂停期间不扣秒，也不计入用时。 */
  function pauseExam() {
    var e = State.exam;
    if (!e || (e.phase !== 'run' && e.phase !== 'selfcheck')) return;
    examSaveDraft();
    if (e.phase === 'run' && !e.paused) {
      var now = Date.now();
      e.remainingMs = Math.max(0, e.endTs - now);
      e.elapsedMs = (e.elapsedMs || 0) + Math.max(0, now - e.segmentStartTs);
      e.paused = true;
    }
    stopExamTimer();
    saveExamSession();
  }

  function pendingExam() {
    if (State.exam && (State.exam.phase === 'run' || State.exam.phase === 'selfcheck')) return State.exam;
    return loadExamSession();
  }

  VIEWS.exam = function () {
    var e = State.exam;
    if (!e) return examSetup();
    if (e.phase === 'run') return e.paused ? examSetup() : examRun();
    if (e.phase === 'selfcheck') return examSelfCheck();
    if (e.phase === 'report') return examReport();
    return examSetup();
  };

  function examSetup() {
    var withShort = !!State.p.withShort;
    var scope = State.p.scope || 'all';
    var pool = examScopePool(scope, withShort);
    var html = '';

    var pending = pendingExam();
    if (pending) {
      html += '<div class="card"><div class="card-title">上次考试已保存</div>' +
        '<div class="note">共 ' + pending.ids.length + ' 题，' + (pending.phase === 'selfcheck' ? '等待主观题自评' :
        '剩余 ' + fmtClock(pending.remainingMs / 1000)) + '。草稿与选项顺序已保留。</div>' +
        '<div class="btn-row mt10"><button class="btn primary" type="button" data-act="exam:resume">继续上次考试</button>' +
        '<button class="btn danger" type="button" data-act="exam:discard">放弃上次考试</button></div></div>';
    }

    html += '<div class="card"><div class="card-title">考试设置</div>' +
      '<div class="field"><label>题量</label><div class="seg">' +
      [10, 20, 30, 50, 100].map(function (n) {
        return '<button type="button" class="' + (State.settings.examCount === n ? 'active' : '') + '" data-act="exam:count" data-v="' + n + '">' + n + '</button>';
      }).join('') +
      '</div>' +
      '<div class="row mt10"><span class="small muted nowrap">自定义</span>' +
      '<input class="input" type="number" min="1" max="200" inputmode="numeric" data-act="exam:count-in" value="' + State.settings.examCount + '" style="max-width:110px">' +
      '<span class="small muted">题</span></div></div>' +

      '<div class="field"><label>时长</label><div class="seg">' +
      [10, 20, 30, 60, 90].map(function (n) {
        return '<button type="button" class="' + (State.settings.examMinutes === n ? 'active' : '') + '" data-act="exam:min" data-v="' + n + '">' + n + '分</button>';
      }).join('') +
      '</div>' +
      '<div class="row mt10"><span class="small muted nowrap">自定义</span>' +
      '<input class="input" type="number" min="1" max="300" inputmode="numeric" data-act="exam:min-in" value="' + State.settings.examMinutes + '" style="max-width:110px">' +
      '<span class="small muted">分钟</span></div></div>' +

      '<div class="field"><label>出题范围</label><div class="seg">' +
      '<button type="button" class="' + (scope === 'all' ? 'active' : '') + '" data-act="exam:scope" data-v="all">全部</button>' +
      '<button type="button" class="' + (scope === 'wrong' ? 'active' : '') + '" data-act="exam:scope" data-v="wrong">仅错题</button>' +
      '<button type="button" class="' + (scope === 'new' ? 'active' : '') + '" data-act="exam:scope" data-v="new">仅未做</button>' +
      '</div></div>' +

      '<div class="switch-row"><div class="sw-txt"><strong>包含简答题</strong><small>交卷后需自评「会 / 不会」再出分</small></div>' +
      '<button type="button" class="switch" role="switch" aria-checked="' + (withShort ? 'true' : 'false') + '" data-act="exam:short" aria-label="包含简答题"></button></div>' +

      '<div class="note mt10">当前范围可用题目：<b>' + pool.length + '</b> 题，将抽取 <b>' + Math.min(State.settings.examCount, pool.length) + '</b> 题，限时 <b>' + State.settings.examMinutes + '</b> 分钟。</div>' +
      '<div class="btn-row mt16"><button class="btn primary block" type="button" data-act="exam:start"' + (pool.length ? '' : ' disabled') + '>开始考试</button></div>' +
      '</div>';

    // 历史记录
    html += '<div class="card"><div class="card-title">历史成绩<span class="card-sub">' + State.exams.length + ' 条</span></div>';
    if (!State.exams.length) {
      html += '<div class="empty"><div class="empty-ico">🗒️</div><strong>还没有考试记录</strong><p>完成一次模拟考试后，成绩会显示在这里。</p></div>';
    } else {
      html += '<div class="list">';
      State.exams.slice(0, 20).forEach(function (x, i) {
        var pass = x.score >= 60;
        html += '<div class="list-item"><span class="li-idx">' + (i + 1) + '</span>' +
          '<span class="li-body"><strong>' + x.score + ' 分 <span class="chip ' + (pass ? 'ok' : 'bad') + '">' + (pass ? '及格' : '不及格') + '</span></strong>' +
          '<small>' + fmtDate(x.ts) + ' · 共 ' + x.total + ' 题 · 答对 ' + x.correct + ' 题 · 用时 ' + fmtDur(x.durationMs || 0) + '</small></span>' +
          '<button class="btn sm ghost" type="button" data-act="exam:detail" data-i="' + i + '">详情</button></div>';
      });
      html += '</div>' +
        '<div class="btn-row mt10"><button class="btn danger sm" type="button" data-act="exam:clear">清空成绩记录</button></div>';
    }
    html += '</div>';
    return html;
  }

  function examStart(force) {
    if (!force && pendingExam()) {
      confirmBox('重新开始考试？', '上次未完成的考试将被替换，已有学习进度和成绩不受影响。', '重新开始', function () { examStart(true); });
      return;
    }
    var withShort = !!State.p.withShort;
    var scope = State.p.scope || 'all';
    var pool = examScopePool(scope, withShort);
    if (!pool.length) { toast('该范围内没有可用题目', 'bad'); return; }
    var n = clamp(State.settings.examCount, 1, pool.length);
    var ids = shuffle(pool.map(function (q) { return q.id; })).slice(0, n);
    State.exam = {
      ids: ids, i: 0, phase: 'run', draft: {}, perm: {}, answered: {},
      startTs: Date.now(), endTs: Date.now() + State.settings.examMinutes * 60000,
      minutes: State.settings.examMinutes, gridOpen: true, gridPage: 1, withShort: withShort, scope: scope,
      res: null, self: {}, autoSubmit: false, paused: false,
      remainingMs: State.settings.examMinutes * 60000, elapsedMs: 0, segmentStartTs: Date.now()
    };
    go('exam');
    startExamTimer();
    toast('考试开始，共 ' + n + ' 题 / ' + State.settings.examMinutes + ' 分钟', 'ok', 2200);
  }

  function examCurrent() {
    var e = State.exam;
    if (!e || !e.ids.length) return null;
    e.i = clamp(e.i, 0, e.ids.length - 1);
    return qById(e.ids[e.i]);
  }

  /** 计数与答题卡共用实际草稿判定，输入、清空和整卡渲染保持同一口径。 */
  function examAnsweredCount(e) {
    return e.ids.filter(function (id) { return hasAnswer(qById(id), getDraft(e, id)); }).length;
  }
  function examRun() {
    var e = State.exam;
    var q = examCurrent();
    if (!q) { State.exam = null; return examSetup(); }
    var picked = getDraft(e, q.id);
    var answered = examAnsweredCount(e);
    var ctx = { q: q, idx: e.i, total: e.ids.length, sess: e, picked: picked, reveal: false, ok: false, locked: false, examRunning: true };
    var html = renderCard(q, ctx);
    html += '<div class="row between mt10 small muted"><span id="exam-answered">已答 ' + answered + '/' + e.ids.length + ' 题</span>' +
      '<span class="row"><button class="btn sm ghost" type="button" data-act="grid:toggle">答题卡</button>' +
      '<button class="btn sm danger" type="button" data-act="exam:submit">交卷</button></span></div>';
    html += navBtns({ idx: e.i, total: e.ids.length });
    //卡片标题里的重复「收起/展开」按钮已删除（上方工具行的「答题卡」就是同一个动作）；
    //   折叠时整张卡片不再渲染，避免留下一个空卡片。
    // 答题卡与练习共用同一个分页组件（每 100 题一页），不再各写一份。
    // 考试中不显示对错，只显示「已答/未答」，故 revealRes=false。
    if (e.gridOpen) {
      html += gridCard(e.ids.map(qById), {
        idx: e.i, page: e.gridPage, revealRes: false,
        resOf: function (id) {
          var qq = qById(id);
          return hasAnswer(qq, getDraft(e, id)) ? { ok: true } : null;
        }
      });
    }
    return html;
  }

  function examPick(k) {
    var e = State.exam;
    if (!e || e.phase !== 'run' || e.paused) return;
    var q = examCurrent();
    if (!q) return;
    if (q.type === 'single') { setDraft(e, q.id, k); render(false); return; }
    if (q.type === 'judge') { setDraft(e, q.id, k === 'true'); render(false); return; }
    if (q.type === 'multi') {
      var cur = getDraft(e, q.id);
      if (!Array.isArray(cur)) cur = [];
      var i = cur.indexOf(k);
      if (i >= 0) cur.splice(i, 1); else cur.push(k);
      cur.sort();
      setDraft(e, q.id, cur);
      render(false);
    }
  }

  function examSaveDraft() {
    var e = State.exam;
    if (!e || e.phase !== 'run' || e.paused || State.route !== 'exam') return;
    var q = examCurrent();
    if (!q) return;
    if (q.type === 'fill') {
      var ins = $$('#view .fill-item .input');
      if (ins.length) {
        var arr = [];
        ins.forEach(function (el, i) { arr[i] = el.value; });
        setDraft(e, q.id, arr);
      }
    } else if (q.type === 'short') {
      var ta = $('#view .textarea');
      if (ta) setDraft(e, q.id, ta.value);
    }
  }

  function startExamTimer() {
    if (State.examTimer) clearInterval(State.examTimer);
    State.examTimer = setInterval(tickClock, 500);
    tickClock();
  }
  function stopExamTimer() {
    if (State.examTimer) { clearInterval(State.examTimer); State.examTimer = 0; }
  }
  function tickClock() {
    var el = document.getElementById('exam-clock');
    var e = State.exam;
    if (!e || e.phase !== 'run' || e.paused) { stopExamTimer(); return; }
    if (State.route !== 'exam') { pauseExam(); return; }
    var left = Math.max(0, e.endTs - Date.now());
    var sec = Math.round(left / 1000);
    if (el) {
      el.textContent = '⏱ ' + fmtClock(left / 1000);
      el.className = 'timer' + (sec < 60 ? ' danger' : (sec < 300 ? ' warn' : ''));
    }
    if (left <= 0) {
      stopExamTimer();
      e.autoSubmit = true;
      examFinish();
      if (State.route === 'exam') render(true);
      toast('考试时间到，已自动交卷', 'bad', 2600);
    }
  }

  reg('exam:new', function () {
    if (State.exam && State.exam.phase === 'report') State.exam = null;
    go('exam', { scope: 'all', withShort: false });
  });
  reg('exam:resume', function () {
    var e = pendingExam();
    if (!e) { toast('没有可恢复的考试', 'bad'); return; }
    State.exam = e;
    if (e.phase === 'run') {
      e.paused = false; e.segmentStartTs = Date.now(); e.endTs = e.segmentStartTs + e.remainingMs;
    }
    go('exam');
    if (e.phase === 'run') startExamTimer();
  });
  reg('exam:discard', function () {
    confirmBox('放弃上次考试？', '将删除这场未完成考试的草稿，已有学习进度和成绩不受影响。', '放弃考试', function () {
      stopExamTimer(); State.exam = null; rawDel(KEY_EXAM_SESSION); render(false);
    });
  });
  reg('exam:count', function (el) { State.settings.examCount = toInt(el.getAttribute('data-v'), 20); saveSettings(); render(false); });
  reg('exam:min', function (el) { State.settings.examMinutes = toInt(el.getAttribute('data-v'), 30); saveSettings(); render(false); });
  reg('exam:scope', function (el) { State.p.scope = el.getAttribute('data-v'); render(false); });
  reg('exam:short', function () { State.p.withShort = !State.p.withShort; render(false); });
  reg('exam:start', function () { examStart(); });
  reg('exam:count-in', function (el, ev) {
    if (ev && ev.type === 'input') return;
    State.settings.examCount = clamp(toInt(el.value, 20), 1, 200); saveSettings(); render(false);
  });
  reg('exam:min-in', function (el, ev) {
    if (ev && ev.type === 'input') return;
    State.settings.examMinutes = clamp(toInt(el.value, 30), 1, 300); saveSettings(); render(false);
  });

  reg('exam:submit', function () {
    var e = State.exam;
    if (!e || e.phase !== 'run' || e.paused) return;
    examSaveDraft();
    var un = e.ids.filter(function (id) { return !hasAnswer(qById(id), getDraft(e, id)); }).length;
    confirmBox('确认交卷？', un ? ('还有 ' + un + ' 题未作答，交卷后将无法修改。') : '所有题目均已作答，交卷后将无法修改。', '交卷', function () {
      examFinish();
      render(true);
    });
  });

  /** 交卷：判分（含简答自评环节） */
  function examFinish() {
    var e = State.exam;
    if (!e || e.phase !== 'run' || e.paused) return;
    pauseExam();
    e.durationMs = e.elapsedMs;
    var needSelf = buildExamResults(e);
    if (needSelf) { e.phase = 'selfcheck'; saveExamSession(); return; }
    examScore();
  }

  /** 未答计入试卷分母，但没有作答内容就不能判为正确。 */
  function buildExamResults(e) {
    e.res = {};
    var needSelf = false;
    e.ids.forEach(function (id) {
      var q = qById(id);
      var picked = getDraft(e, id);
      if (!q) return;
      if (q.type === 'short') {
        if (!hasAnswer(q, picked)) e.self[id] = false;
        else if (!Object.prototype.hasOwnProperty.call(e.self, id)) needSelf = true;
        e.res[id] = { picked: picked, ok: e.self[id] === true, self: true };
      } else {
        e.res[id] = { picked: picked, ok: hasAnswer(q, picked) && judgeAnswer(q, picked), self: false };
      }
    });
    return needSelf;
  }

  function examSelfCheck() {
    var e = State.exam;
    var ids = e.ids.filter(function (id) { var q = qById(id); return q && q.type === 'short'; });
    var html = '<div class="card"><div class="card-title">主观题自评<span class="card-sub">' + ids.length + ' 题</span></div>' +
      '<div class="small dim">对照参考答案，如实选择「会 / 不会」，系统据此计算总分。</div></div>';
    ids.forEach(function (id, i) {
      var q = qById(id);
      var mine = getDraft(e, id);
      var sel = e.self[id];
      html += '<div class="card"><div class="q-head"><span class="q-idx">简答 ' + (i + 1) + '</span>' +
        '<span class="grow"></span>' + favBtn(q) + '</div>' +
        '<div class="q-stem">' + esc(q.stem) + '</div>' +
        '<div class="explain mt10"><div class="ex-title">你的作答</div>' + (String(mine || '').trim() ? esc(mine) : '（未作答）') + '</div>' +
        '<div class="answer-box"><div class="ab-title">参考答案</div>' + esc(answerTextDisp(q, e)) + '</div>' +
        explainBlock(q, false, e) +
        '<div class="selfcheck">' +
        '<button class="btn ' + (sel === true ? 'primary' : 'ghost') + '" type="button" data-act="ans:self" data-v="1" data-id="' + esc(id) + '"' + (hasAnswer(q, mine) ? '' : ' disabled') + '>✅ 会</button>' +
        '<button class="btn ' + (sel === false ? 'danger' : 'ghost') + '" type="button" data-act="ans:self" data-v="0" data-id="' + esc(id) + '">❌ 不会</button>' +
        '</div></div>';
    });
    var undone = ids.filter(function (id) { return !Object.prototype.hasOwnProperty.call(e.self, id); }).length;
    html += '<div class="btn-row"><button class="btn primary block" type="button" data-act="exam:scoredone"' + (undone ? ' disabled' : '') + '>' +
      (undone ? '还有 ' + undone + ' 题未自评' : '完成评分') + '</button></div>';
    return html;
  }

  function examSelf(el) {
    var e = State.exam;
    if (!e || e.phase !== 'selfcheck') return;
    var id = el.getAttribute('data-id');
    if (!id) { var q = examCurrent(); if (!q) return; id = q.id; }
    var qq = qById(id);
    if (e.ids.indexOf(id) < 0 || !qq || qq.type !== 'short') return;
    e.self[id] = hasAnswer(qq, getDraft(e, id)) && el.getAttribute('data-v') === '1';
    e.res[id].ok = e.self[id];
    render(false);
  }

  function examScore() {
    var e = State.exam;
    if (!e || e.phase === 'report' || !e.res || buildExamResults(e)) return;
    var total = e.ids.length;
    var correct = 0, wrongIds2 = [];
    e.ids.forEach(function (id) {
      var r = e.res[id];
      if (r && r.ok) correct++; else wrongIds2.push(id);
    });
    e.score = pct(correct, total);
    e.phase = 'report';
    e.correct = correct;
    e.wrongList = wrongIds2;
    stopExamTimer();
    rawDel(KEY_EXAM_SESSION);
    Feedback.play('complete');    // 交卷出成绩：四音上行琶音（同一拍内的 exam:scoredone 会被 60ms 去抖吃掉）
    // 写入历史与进度
    var rec = {
      ts: Date.now(), total: total, correct: correct, score: e.score,
      durationMs: e.durationMs, detail: e.ids.map(function (id) {
        var r = e.res[id] || {};
        return { id: id, ok: !!r.ok, pick: r.picked === undefined ? null : r.picked };
      })
    };
    State.exams.unshift(rec);
    if (State.exams.length > 50) State.exams = State.exams.slice(0, 50);
    saveExams();
    e.ids.forEach(function (id) {
      var r = e.res[id];
      if (!r) return;
      var q = qById(id);
      // 学习计数、日做题量和错题本只记录实际作答，未答仅扣考试分。
      if (q && hasAnswer(q, r.picked)) record(id, !!r.ok, { inWrongMode: false, markWrong: true });
    });
  }

  reg('exam:scoredone', function () { examScore(); render(true); });

  function examReport() {
    var e = State.exam;
    var html = '';
    var pass = e.score >= 60;
    var stars = clamp(Math.round(e.score / 20), 0, 5);
    html += '<div class="card"><div class="score-hero">' +
      '<div class="score-num ' + (pass ? 'pass' : 'fail') + '">' + e.score + '</div>' +
      '<div class="score-lbl">百分制得分' + (pass ? ' · 及格' : ' · 未及格') + '</div>' +
      '<div class="stars">' + '★'.repeat(stars) + '☆'.repeat(5 - stars) + '</div>' +
      '</div>' +
      '<div class="report-row"><span>题量</span><b>' + e.ids.length + ' 题</b></div>' +
      '<div class="report-row"><span>答对</span><b>' + e.correct + ' 题</b></div>' +
      '<div class="report-row"><span>答错 / 未答</span><b>' + (e.ids.length - e.correct) + ' 题</b></div>' +
      '<div class="report-row"><span>用时</span><b>' + fmtDur(e.durationMs || 0) + '</b></div>' +
      '<div class="report-row"><span>正确率</span><b>' + pct(e.correct, e.ids.length) + '%</b></div>' +
      (e.autoSubmit ? '<div class="note mt10">本次为超时自动交卷。</div>' : '') +
      '<div class="btn-row mt16">' +
      '<button class="btn primary" type="button" data-act="exam:new">再考一次</button>' +
      '<button class="btn" type="button" data-nav="wrong">查看错题本</button>' +
      '<button class="btn ghost" type="button" data-nav="home">返回首页</button>' +
      '</div></div>';

    if (e.wrongList && e.wrongList.length) {
      html += '<div class="card"><div class="card-title">错题回顾<span class="card-sub">' + e.wrongList.length + ' 题</span></div>';
      html += '<div class="list">';
      e.wrongList.forEach(function (id) {
        var q = qById(id);
        if (!q) return;
        html += '<div class="list-item"><span class="li-idx">' + (TYPE_SHORT[q.type] || '') + '</span>' +
          '<span class="li-body"><strong class="clamp3">' + esc(q.stem) + '</strong>' +
          '<small>你的答案：' + esc(renderPick(q, e.res[id], e)) + '　|　正确答案：' + esc(answerTextDisp(q, e).replace(/\n/g, ' ')) + uncertSuffix(q) + '</small>' +
          explainBlock(q, true, e) +
          '</span></div>';
      });
      html += '</div></div>';
    }

    html += '<div class="card"><div class="card-title">全部题目回顾</div><div class="list">';
    e.ids.forEach(function (id, i) {
      var q = qById(id);
      var r = e.res[id] || {};
      if (!q) return;
      html += '<div class="list-item"><span class="li-idx">' + (i + 1) + '</span>' +
        '<span class="li-body"><strong class="clamp2">' + (r.ok ? '✅ ' : '❌ ') + esc(q.stem) + '</strong>' +
        '<small>' + (TYPE_SHORT[q.type] || '') + ' · ' + esc(q.chapter) + '　正确答案：' + esc(answerTextDisp(q, e).replace(/\n/g, ' ')) + uncertSuffix(q) + '</small>' +
        explainBlock(q, false, e) +
        '</span></div>';
    });
    html += '</div></div>';
    return html;
  }

  function renderPick(q, r, sess) {
    if (!r || r.picked === undefined || r.picked === null) return '（未作答）';
    if (q.type === 'multi') return (r.picked || []).map(function (L) { return dispLetterOf(q, sess, L); }).sort().join('') || '（未作答）';
    if (q.type === 'single') return dispLetterOf(q, sess, r.picked);
    if (q.type === 'judge') return r.picked ? '正确' : '错误';
    if (q.type === 'fill') return (r.picked || []).map(function (t) { return String(t || '（空）'); }).join(' / ');
    return String(r.picked).slice(0, 60);
  }

  reg('exam:detail', function (el) {
    var i = toInt(el.getAttribute('data-i'), 0);
    var x = State.exams[i];
    if (!x) return;
    var html = '<div class="report-row"><span>时间</span><b>' + fmtDate(x.ts) + '</b></div>' +
      '<div class="report-row"><span>得分</span><b>' + x.score + ' 分</b></div>' +
      '<div class="report-row"><span>题量 / 答对</span><b>' + x.total + ' / ' + x.correct + '</b></div>' +
      '<div class="report-row"><span>用时</span><b>' + fmtDur(x.durationMs || 0) + '</b></div>';
    if (Array.isArray(x.detail) && x.detail.length) {
      html += '<div class="divider"></div><div class="small muted mb10">逐题结果：</div><div class="chips">' +
        x.detail.map(function (d, k) {
          return '<span class="chip ' + (d.ok ? 'ok' : 'bad') + '">' + (k + 1) + (d.ok ? ' ✔' : ' ✘') + '</span>';
        }).join('') + '</div>';
    }
    openModal({ title: '成绩详情', html: html, buttons: [{ label: '关闭', cls: 'primary' }] });
  });

  reg('exam:clear', function () {
    confirmBox('清空成绩记录', '将删除全部模拟考试历史（不影响答题进度），确定吗？', '清空', function () {
      State.exams = []; saveExams(); render(false); toast('成绩记录已清空', '', 1400);
    });
  });

  /* ======================================================================
   * 15. 错题本 / 收藏夹
   * ==================================================================== */
  function listEmpty(icon, title, text, actLabel, actName) {
    return '<div class="card"><div class="empty"><div class="empty-ico">' + icon + '</div>' +
      '<strong>' + title + '</strong><p>' + text + '</p>' +
      (actLabel ? '<button class="btn primary" type="button" data-act="' + actName + '">' + actLabel + '</button>' : '') +
      '</div></div>';
  }

  function qListItem(q, right) {
    var p = entry(q.id);
    var meta = TYPE_LABEL[q.type] + ' · ' + esc(q.chapter) +
      (p ? '　答对 ' + p.correct + ' / 答错 ' + p.wrong + '　最近 ' + fmtDate(p.lastTs) : '') +
      (isUncertain(q) ? '　' + uncertTag() : '');
    return '<div class="list-item"><span class="li-idx">' + (TYPE_SHORT[q.type] || '') + '</span>' +
      '<span class="li-body"><strong class="clamp3">' + esc(q.stem) + '</strong><small>' + meta + '</small></span>' +
      '<span class="row" style="flex:0 0 auto">' + (right || '') + '</span></div>';
  }

  VIEWS.wrong = function () {
    // State.wrongQ：错题本搜索词（内存态，不落盘；刷新即清空）
    var ids = wrongIds();
    var html = '';
    if (!ids.length) {
      return listEmpty('🎉', '错题本是空的', '答错的题会自动收进这里，方便集中复习。', '去练习', 'home:startall');
    }
    var kw = String(State.wrongQ || '').trim();
    var shown = wrongFilter(ids, kw);
    html += '<div class="card"><div class="card-title">错题本<span class="card-sub">' + ids.length + ' 题</span></div>' +
      '<div class="search-bar">' +
      '<span class="search-ico" aria-hidden="true">🔍</span>' +
      '<input class="input search-input" type="search" data-act="wrong:search" value="' + esc(kw) + '"' +
      ' placeholder="搜索题干 / 选项关键词，快速定位错题" aria-label="搜索错题">' +
      '<button class="btn sm ghost" type="button" data-act="wrong:searchclear" aria-label="清空搜索"' + (kw ? '' : ' hidden') + '>清空</button>' +
      '</div>' +
      '<div class="small muted mt6" id="wrong-search-summary">' + wrongSearchSummary(ids, shown, kw) + '</div>' +
      '<div class="btn-row mt10">' +
      '<button class="btn primary" type="button" data-act="wrong:redo">重做' + (kw ? '筛选出的 ' + shown.length + ' 题' : '全部错题') + '</button>' +
      '<button class="btn danger" type="button" data-act="wrong:clear">清空错题本</button>' +
      '</div><div class="small muted mt6">在「错题重做」中答对的题目会自动移出错题本。</div></div>';
    return html + '<div id="wrong-search-results">' + wrongResultsHtml(shown, kw) + '</div>';
  };

  /** 搜索只替换结果区，输入框与移动端键盘保持原位。 */
  function wrongSearchSummary(ids, shown, kw) {
    return kw ? '命中 <b>' + shown.length + '</b> / ' + ids.length + ' 题' +
      (shown.length ? '，结果沿用错题顺序' : '，没有匹配的错题') : '';
  }
  function wrongResultsHtml(shown, kw) {
    if (kw && !shown.length) {
      return listEmpty('🔍', '没有匹配的错题', '换个关键词试试，或点「清空搜索」看全部。');
    }
    var html = '<div class="card"><div class="card-title">' + (kw ? '搜索结果' : '全部错题') +
      '<span class="card-sub">' + shown.length + ' 题</span></div><div class="list">';
    shown.forEach(function (id) {
      var q = qById(id);
      if (!q) return;
      html += qListItem(q,
        '<button class="btn sm" type="button" data-act="q:practice" data-id="' + esc(id) + '">练</button>' +
        '<button class="btn sm ghost" type="button" data-act="wrong:remove" data-id="' + esc(id) + '">移除</button>');
    });
    html += '</div></div>';
    return html;
  }

  var wrongSearchTimer = 0;
  var wrongSearchComposing = false;
  function cancelWrongSearch() {
    if (wrongSearchTimer) clearTimeout(wrongSearchTimer);
    wrongSearchTimer = 0;
  }
  function renderWrongSearchResults() {
    if (State.route !== 'wrong') return;
    var box = $('#wrong-search-results');
    if (!box) return;
    var ids = wrongIds(), kw = String(State.wrongQ || '').trim(), shown = wrongFilter(ids, kw);
    box.innerHTML = wrongResultsHtml(shown, kw);
    var summary = $('#wrong-search-summary'), clear = $('#view [data-act="wrong:searchclear"]');
    var redo = $('#view [data-act="wrong:redo"]');
    if (summary) summary.innerHTML = wrongSearchSummary(ids, shown, kw);
    if (clear) clear.hidden = !kw;
    if (redo) redo.textContent = '重做' + (kw ? '筛选出的 ' + shown.length + ' 题' : '全部错题');
  }

  VIEWS.fav = function () {
    var ids = favIds();
    if (!ids.length) {
      return listEmpty('⭐', '还没有收藏题目', '练习时点右上角「收藏」即可加入这里。', '去练习', 'home:startall');
    }
    var html = '<div class="card"><div class="card-title">收藏夹<span class="card-sub">' + ids.length + ' 题</span></div>' +
      '<div class="btn-row"><button class="btn primary" type="button" data-act="fav:practice">练习全部收藏</button>' +
      '<button class="btn" type="button" data-act="fav:recite">背收藏题</button></div></div>';
    html += '<div class="card"><div class="list">';
    ids.forEach(function (id) {
      var q = qById(id);
      if (!q) return;
      html += qListItem(q,
        '<button class="btn sm" type="button" data-act="q:practice" data-id="' + esc(id) + '">练</button>' +
        '<button class="btn sm ghost" type="button" data-act="fav" data-id="' + esc(id) + '">取消</button>');
    });
    html += '</div></div>';
    return html;
  };

  reg('q:practice', function (el) {
    var id = el.getAttribute('data-id');
    var q = qById(id);
    if (!q) return;
    startSession([id], '单题练习 · ' + TYPE_LABEL[q.type], 'seq', 'practice');
  });
  /**
   * 错题搜索：题干 / 选项 / 解析 / 考点 / 章节全字段匹配，**只返回命中项**。
   * 注意（2026-10-09 踩过）：初版写成「命中排前、未命中仍列在后面」，结果搜索后条数不变
   * （5 条还是 5 条），等于没过滤 —— 那只是排序，不是「搜索定位」。这里必须 filter。
   */
  function wrongFilter(ids, kw) {
    if (!kw) return ids;
    var k = kw.toLowerCase();
    return ids.filter(function (id) {
      var q = qById(id);
      if (!q) return false;
      var blob = (q.stem + ' ' + (q.options || []).join(' ') + ' ' + (q.explanation || '') + ' ' +
                  (q.keyConcept || '') + ' ' + (q.keywords || []).join(' ') + ' ' + (q.chapter || '')).toLowerCase();
      return blob.indexOf(k) >= 0;
    });
  }
  // input 与输入法结束事件统一调度，通用事件分派不能绕过防抖。
  reg('wrong:search', null);
  reg('wrong:searchclear', function () {
    cancelWrongSearch();
    State.wrongQ = '';
    var el = $('#view [data-act="wrong:search"]');
    if (el) { el.value = ''; el.focus(); }
    renderWrongSearchResults();
  });
  reg('wrong:redo', function () {
    var all = wrongIds();
    var kw = String(State.wrongQ || '').trim();
    var ids = kw ? wrongFilter(all, kw).slice(0, 999) : all;
    if (!ids.length) { toast(kw ? '没有匹配的错题' : '错题本是空的', '', 1400); return; }
    startSession(ids, '错题重做 · ' + ids.length + ' 题', State.settings.order, 'practice');
    if (State.sess) { State.sess.wrongMode = true; saveSession(); }
  });
  reg('wrong:recite', function () {
    var ids = wrongIds();
    if (!ids.length) { toast('错题本是空的', '', 1400); return; }
    startSession(ids, '背错题 · ' + ids.length + ' 题', 'seq', 'recite');
  });
  reg('wrong:remove', function (el) {
    var id = el.getAttribute('data-id');
    var p = entry(id);
    if (p) { p.wrongFlag = false; saveProgress(); }
    updateBadges(); invalidateStats(); render(false); toast('已移出错题本', '', 1200);
  });
  reg('wrong:clear', function () {
    confirmBox('清空错题本', '将把所有题目移出错题本（答题记录与收藏保留），确定吗？', '清空', function () {
      progressIds().forEach(function (k) { State.progress[k].wrongFlag = false; });
      saveProgress(); updateBadges(); render(false); toast('错题本已清空', '', 1400);
    });
  });
  reg('fav:practice', function () {
    var ids = favIds();
    if (!ids.length) { toast('收藏夹是空的', '', 1400); return; }
    startSession(ids, '收藏练习 · ' + ids.length + ' 题', State.settings.order, 'practice');
  });
  reg('fav:recite', function () {
    var ids = favIds();
    if (!ids.length) { toast('收藏夹是空的', '', 1400); return; }
    startSession(ids, '背收藏题 · ' + ids.length + ' 题', 'seq', 'recite');
  });

  /* ======================================================================
   * 16. 搜索
   * ==================================================================== */
  VIEWS.search = function () {
    return '<div class="card">' +
      '<div class="field mb0"><label>关键词搜索（题干 / 选项 / 章节）</label>' +
      '<input class="input" id="search-input" type="search" data-act="search:input" placeholder="如：南昌起义、国防教育日…" ' +
      'autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" value="' + esc(State.p.q || '') + '">' +
      '</div>' +
      '<div class="small muted mt6">支持空格分隔多个关键词（需同时命中）。按 <kbd>S</kbd> 可随时聚焦搜索框。</div>' +
      '</div><div id="search-results"></div>';
  };

  function searchMatch(q, kws) {
    if (!kws.length) return false;
    var hay = (q.stem + ' ' + q.options.join(' ') + ' ' + q.chapter + ' ' + (TYPE_LABEL[q.type] || '')).toLowerCase();
    return kws.every(function (k) { return hay.indexOf(k) >= 0; });
  }

  function renderSearchResults() {
    var box = $('#search-results');
    if (!box) return;
    var raw = (State.p.q || '').trim();
    if (!raw) {
      box.innerHTML = '<div class="card"><div class="empty"><div class="empty-ico">🔍</div>' +
        '<strong>输入关键词开始搜索</strong><p>在 ' + State.questions.length + ' 道题中查找题干、选项或章节。</p></div></div>';
      return;
    }
    var kws = raw.toLowerCase().split(/\s+/).filter(Boolean);
    var hits = State.questions.filter(function (q) { return searchMatch(q, kws); });
    if (!hits.length) {
      box.innerHTML = '<div class="card"><div class="empty"><div class="empty-ico">🕳️</div>' +
        '<strong>没有找到相关题目</strong><p>换个关键词试试，或减少关键词数量。</p></div></div>';
      return;
    }
    var html = '<div class="card"><div class="card-title">搜索结果<span class="card-sub">' + hits.length + ' 题</span></div>' +
      '<div class="btn-row mb10"><button class="btn primary sm" type="button" data-act="search:practice">练习全部结果</button>' +
      '<button class="btn sm" type="button" data-act="search:recite">背这些题</button></div><div class="list">';
    hits.slice(0, 200).forEach(function (q, i) {
      html += '<button type="button" class="list-item" data-act="search:go" data-id="' + esc(q.id) + '">' +
        '<span class="li-idx">' + (TYPE_SHORT[q.type] || '') + '</span>' +
        '<span class="li-body"><strong class="clamp3">' + hl(q.stem, kws[0]) + '</strong>' +
        '<small>' + esc(q.chapter) + ' · ' + esc(q.source) + '</small></span></button>';
    });
    html += '</div>' + (hits.length > 200 ? '<div class="small muted mt6">仅显示前 200 条</div>' : '') + '</div>';
    box.innerHTML = html;
  }

  reg('search:input', null);   // input 事件单独处理
  reg('search:go', function (el) {
    var id = el.getAttribute('data-id');
    if (!qById(id)) return;
    var ids = searchIds();
    var idx = ids.indexOf(id);
    var s = {
      ids: ids, i: idx < 0 ? 0 : idx, title: '搜索结果练习 · ' + ids.length + ' 题',
      order: 'seq', mode: 'practice', res: {}, draft: {}, perm: {}, startedAt: Date.now()
    };
    State.sess = s; State.lastSess = s;
    go('practice');
  });
  function searchIds() {
    var raw = (State.p.q || '').trim();
    var kws = raw.toLowerCase().split(/\s+/).filter(Boolean);
    return State.questions.filter(function (q) { return searchMatch(q, kws); }).map(function (q) { return q.id; });
  }
  reg('search:practice', function () {
    var ids = searchIds();
    if (!ids.length) { toast('没有搜索结果', '', 1400); return; }
    startSession(ids, '搜索结果练习 · ' + ids.length + ' 题', 'seq', 'practice');
  });
  reg('search:recite', function () {
    var ids = searchIds();
    if (!ids.length) { toast('没有搜索结果', '', 1400); return; }
    startSession(ids, '背搜索结果 · ' + ids.length + ' 题', 'seq', 'recite');
  });

  /* ======================================================================
   * 17. 统计
   * ==================================================================== */
  VIEWS.stats = function () {
    var d = derive();
    if (!d.attempts) {
      return listEmpty('📊', '还没有学习数据', '完成几道题后，这里会显示正确率、掌握度和每日做题量。', '开始练习', 'home:startall');
    }
    var maxDay = Math.max.apply(null, d.days.map(function (x) { return x.n; }).concat([1]));
    var html = '';

    html += '<div class="card"><div class="card-title">总览</div>' +
      '<div class="grid grid-4">' +
      '<div class="stat pri"><b>' + d.uniqueRate + '%</b><span>题目正确率</span></div>' +
      '<div class="stat ok"><b>' + d.mastered + '</b><span>已掌握</span></div>' +
      '<div class="stat bad"><b>' + d.review + '</b><span>待复习</span></div>' +
      '<div class="stat"><b>' + d.untouched + '</b><span>未做过</span></div>' +
      '</div>' +
      '<div class="report-row mt10"><span>已做题数</span><b>' + d.done + ' / ' + d.total + '</b></div>' +
      '<div class="report-row"><span>做对过的题</span><b>' + d.uniqueCorrect + ' / ' + d.done + '</b></div>' +
      '<div class="report-row"><span>累计作答</span><b>' + d.attempts + ' 次</b></div>' +
      '<div class="report-row"><span>错题本 / 收藏</span><b>' + d.wrong + ' / ' + d.fav + '</b></div>' +
      '<div class="small muted mt6">「题目正确率」与首页「总正确率」均按题去重（做对过的题 ÷ 做过的题）；导出页的「作答正确率」按作答次数计算。</div>' +
      '<div class="small muted mt6">掌握度规则：连续答对使「熟练度」累积到 3 以上记为已掌握；答错后回到待复习。</div>' +
      '</div>';

    // 按题型
    html += '<div class="card"><div class="card-title">按题型正确率</div><div class="bars">';
    TYPE_ORDER.forEach(function (t) {
      var s = d.byType[t];
      if (!s || !s.total) return;
      // 口径：按题目去重（做对过的题 ÷ 做过的题），避免重做同一题把百分比拉低（用户 2026-10-09）
      html += '<div class="bar-row"><span class="bar-name">' + TYPE_LABEL[t] + '</span>' +
        '<span class="bar-track"><i class="bar-fill' + (s.done && s.uniqueRate < 60 ? ' bad' : (s.done ? ' ok' : '')) + '" style="width:' + (s.done ? s.uniqueRate : 0) + '%"></i></span>' +
        '<span class="bar-num">' + (s.done ? s.uniqueRate + '%' : '未做') + ' · ' + s.uniqueCorrect + '/' + s.done + ' 题</span></div>';
    });
    html += '</div></div>';

    // 每日做题量：有新口径（按日期作答记录）就用它，否则回退旧口径并如实标注
    html += '<div class="card"><div class="card-title">最近 7 天做题量<span class="card-sub">' +
      (d.hasDaily ? '按当天实际作答记录' : '旧记录：按每题最近作答日统计') + '</span></div>' +
      '<div class="chart">';
    d.days.forEach(function (x) {
      var h = Math.round(x.n / maxDay * 100);
      html += '<div class="col"><span class="val">' + (x.n || '') + '</span>' +
        '<span class="track"><i class="bar' + (x.n ? '' : ' zero') + '" style="height:' + (x.n ? Math.max(4, h) : 3) + '%"></i></span>' +
        '<span class="lbl">' + x.label + '</span></div>';
    });
    var week = d.days.reduce(function (a, b) { return a + b.n; }, 0);
    var weekOk = d.days.reduce(function (a, b) { return a + (b.ok || 0); }, 0);
    html += '</div><div class="small muted mt6">近 7 天共作答 ' + week + ' 题' +
      (d.hasDaily ? '，答对 ' + weekOk + ' 题（正确率 ' + pct(weekOk, week) + '%；多次重做都会计入）'
                  : '（旧数据口径：同一题只计最近一次）') + '。</div></div>';

    // 章节
    var chs = Object.keys(d.byChapter);
    if (chs.length) {
      html += '<div class="card"><div class="card-title">按章节掌握情况</div><div class="bars">';
      chs.forEach(function (c) {
        var s = d.byChapter[c];
        // 条宽与数字同一口径：都是「做对过的题 ÷ 做过的题」（此前条画完成度、数字写正确率，两者对不上）
        html += '<div class="bar-row"><span class="bar-name" title="' + esc(c) + '">' + esc(c.length > 6 ? c.slice(0, 6) + '…' : c) + '</span>' +
          '<span class="bar-track"><i class="bar-fill' + (s.done && s.uniqueRate < 60 ? ' bad' : (s.done ? ' ok' : '')) + '" style="width:' + (s.done ? s.uniqueRate : 0) + '%"></i></span>' +
          '<span class="bar-num">' + (s.done ? s.uniqueRate + '%' : '未做') + ' · ' + s.uniqueCorrect + '/' + s.done + ' 题</span></div>';
      });
      html += '</div></div>';
    }

    html += '<div class="btn-row"><button class="btn" type="button" data-nav="wrong">去错题本</button>' +
      '<button class="btn ghost" type="button" data-nav="sync">导出学习数据</button></div>';
    return html;
  };

  /* ======================================================================
   * 17.5 设置（2026-10-09 新增）
   * ----------------------------------------------------------------------
   * 用户要求：在首页新增设置模块，把「声音与震动」挪进来，
   * 并在设置里提供「全局所有文字大小」调节（顶栏的字号/主题按钮已隐藏，改由此处统一管）。
   * 设置项全部落在 State.settings，与旧键兼容（sound / haptic / volume / fontSize / theme）。
   * ==================================================================== */
  var FONT_NAME = { s: '小', m: '标准', l: '大', xl: '特大' };
  var FONT_ORDER = ['s', 'm', 'l', 'xl'];

  function settingsCard() {
    var st = State.settings;
    return '<div class="card"><div class="card-title">文字大小<span class="card-sub">全站文字同比缩放</span></div>' +
      '<div class="seg" role="group" aria-label="文字大小">' +
      FONT_ORDER.map(function (k) {
        return '<button type="button" class="' + (st.fontSize === k ? 'active' : '') +
          '" data-act="set:font" data-v="' + k + '">' + FONT_NAME[k] + '</button>';
      }).join('') +
      '</div>' +
      '<div class="small muted mt6">当前：' + FONT_NAME[st.fontSize] + '。调大后若发现个别地方拥挤，可切回「标准」。</div>' +
      '<div class="field mt10"><label>外观主题</label><div class="seg" role="group" aria-label="外观主题">' +
      ['auto', 'light', 'dark'].map(function (k) {
        return '<button type="button" class="' + (st.theme === k ? 'active' : '') +
          '" data-act="set:theme" data-v="' + k + '">' + THEME_NAME[k] + '</button>';
      }).join('') +
      '</div></div>' +
      '<div class="small muted">当前主题：' + THEME_NAME[st.theme] + '</div>' +
      '</div>' +

      '<div class="card"><div class="card-title">声音与震动</div>' +
      '<div class="switch-row"><div class="sw-txt"><strong>操作音效</strong><small>Web Audio 实时合成，不使用任何音频文件</small></div>' +
      '<button type="button" class="switch" role="switch" aria-checked="' + (st.sound ? 'true' : 'false') +
      '" data-act="set:feedback" data-k="sound" aria-label="操作音效"></button></div>' +
      '<div class="switch-row"><div class="sw-txt"><strong>震动反馈</strong><small>Android / Windows 桌面浏览器有效</small></div>' +
      '<button type="button" class="switch" role="switch" aria-checked="' + (st.haptic ? 'true' : 'false') +
      '" data-act="set:feedback" data-k="haptic" aria-label="震动反馈"></button></div>' +
      '<div class="field mt10 mb0"><label>音效音量<small class="muted">（切换后立即试听）</small></label>' +
      '<div class="seg">' +
      [1, 2, 3].map(function (v) {
        return '<button type="button" class="' + (st.volume === v ? 'active' : '') +
          '" data-act="set:volume" data-v="' + v + '">' + VOLUME_NAME[v] + '</button>';
      }).join('') +
      '</div></div>' +
      '<div class="note small mt10">已启用 iOS 静音键兼容模式（常驻静音音轨）；若仍无声请检查静音键或系统音量。iPhone 不支持网页震动。</div>' +
      '</div>';
  }

  /**
   * 离线版本就绪状态（2026-10-09 新增，对应外部审查报告的「验证后提示」建议）。
   *
   * 为什么需要有这么一块：**页面显示了新内容 ≠ 离线缓存已经更新**。
   * 用户遇到的正是这个差异——联网时看到新版，断网重开还是旧版。
   * 所以这里不靠自己推断，而是向 Service Worker 发消息问：
   * 「当前构建标识对应的缓存里，到底有没有写入 HTML？」只有拿到肯定答复才显示「已就绪」。
   */
  var offlineState = { checked: false, ready: false, buildId: '', cacheName: '' };
  var offlinePending = false;

  /**
   * 安全取 ServiceWorkerContainer。
   * 不能只写「'serviceWorker' in navigator」：在部分环境（file:// / 老 WebView）里
   * 该属性**存在但值为 undefined**，in 判定为 true，紧接着读 .controller 就会抛错，
   * 整个设置页会变成「页面渲染出错」。
   */
  function swContainer() {
    try { return navigator.serviceWorker || null; } catch (e) { return null; }
  }

  function checkOfflineReady(cb) {
    var finish = function (payload) {
      offlineState = {
        checked: true,
        ready: !!(payload && payload.hasHtml),
        buildId: (payload && payload.buildId) || '',
        cacheName: (payload && payload.cacheName) || ''
      };
      if (cb) cb(offlineState);
    };
    var swc = swContainer();
    if (!swc || !swc.controller) {
      finish(null);
      return;
    }
    var ch = new MessageChannel();
    var done = false;
    var once = function (payload) { if (done) return; done = true; finish(payload); };
    ch.port1.onmessage = function (e) { once(e.data); };
    try {
      swc.controller.postMessage({ type: 'cache-status' }, [ch.port2]);
    } catch (e) {
      once(null);
      return;
    }
    // 兜底：旧版本 Worker 没有 message 处理时会一直不回复，不能让界面卡在「正在检查」
    setTimeout(function () { once(null); }, 1500);
  }

  /** 只在「本页尚未查过」时查一次并发起一次重绘，避免 render → 检查 → render 的自激循环 */
  function maybeCheckOffline() {
    if (offlinePending || offlineState.checked) return;
    offlinePending = true;
    checkOfflineReady(function () {
      offlinePending = false;
      if (State.route === 'settings') render(false);
    });
  }

  function offlineText() {
    var swc = swContainer();
    if (!swc) return '当前环境不支持离线缓存（单文件版或 file:// 打开时属正常）';
    if (!swc.controller) return offlineState.checked ? '尚未接管：刷新一次即可启用离线缓存' : '正在检查…';
    if (!offlineState.checked) return '正在检查…';
    if (offlineState.ready) {
      // 显示与首页一致的日期版本号；「是否已写入缓存」由 SW 的 cache-status 回答，不靠猜。
      // （SW 回传的 buildId 是内容哈希，直接显示会与首页版本号对不上。）
      var pv = buildTagTextSafe();
      return '已就绪（' + (pv ? 'v' + pv : '缓存 ' + offlineState.buildId) + '）';
    }
    return '尚未就绪：请联网打开一次本页以完成缓存';
  }

  function offlineRow() {
    maybeCheckOffline();
    return '<div class="switch-row"><div class="sw-txt"><strong>离线版本</strong>' +
      '<small>' + esc(offlineText()) + '</small></div></div>';
  }

  VIEWS.settings = function () {
    return '<div class="card" style="padding:12px 16px"><div class="small dim">' +
      '这里的设置会保存在本机，导入 / 导出时会一并带走。</div></div>' + settingsCard() +
      '<div class="card"><div class="card-title">离线与更新<span class="card-sub">PWA / 添加到主屏幕时生效</span></div>' +
      offlineRow() +
      '<div class="small muted mt6">「已就绪」表示当前版本的页面已经写入离线缓存，' +
      '断网重开也会看到这一版；显示「尚未就绪」时联网打开一次即可。</div></div>';
  };

  reg('set:font', function (el) {
    var v = el.getAttribute('data-v');
    if (FONT_ORDER.indexOf(v) < 0) return;
    State.settings.fontSize = v;
    saveSettings(); applyTheme(); render(false);
    toast('文字大小：' + FONT_NAME[v], '', 1200);
  });
  reg('set:theme', function (el) {
    var v = el.getAttribute('data-v');
    if (['auto', 'light', 'dark'].indexOf(v) < 0) { cycleTheme(); render(false); return; }
    State.settings.theme = v;
    saveSettings(); applyTheme(); render(false);
  });

  /* ======================================================================
   * 18. 导入 / 导出（iPhone ↔ Windows 手动同步）
   * ==================================================================== */
  function buildExport() {
    return {
      app: APP_NAME, ver: EXPORT_VER, exportedAt: new Date().toISOString(),
      progress: State.progress, settings: State.settings, exams: State.exams,
      /* 按日期作答记录（顶层显式给出，便于外部工具直接读取；同时 progress._daily 也带着它） */
      daily: State.progress[KEY_DAILY] || {}
    };
  }
  function exportText() { return JSON.stringify(buildExport(), null, 1); }

  function exportFileName() {
    var d = new Date();
    return '军理刷题-进度-' + d.getFullYear() + pad2(d.getMonth() + 1) + pad2(d.getDate()) + '-' + pad2(d.getHours()) + pad2(d.getMinutes()) + '.json';
  }

  function downloadText(filename, text) {
    try {
      var a = document.createElement('a');
      if (!('download' in a)) return false;
      var blob = new Blob([text], { type: 'application/json;charset=utf-8' });
      var url = URL.createObjectURL(blob);
      a.href = url; a.download = filename; a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        try { URL.revokeObjectURL(url); } catch (e) { /* noop */ }
        if (a.parentNode) a.parentNode.removeChild(a);
      }, 1500);
      return true;
    } catch (e) { return false; }
  }

  function copyText(text, okMsg) {
    function fallback() {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', 'readonly');
        ta.style.position = 'fixed'; ta.style.top = '-1000px'; ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select(); ta.setSelectionRange(0, text.length);
        var ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (ok) { toast(okMsg || '已复制到剪贴板', 'ok'); return true; }
      } catch (e) { /* noop */ }
      toast('复制失败，请长按文本框手动全选复制', 'bad', 2600);
      return false;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(okMsg || '已复制到剪贴板', 'ok'); })
        ['catch'](function () { fallback(); });
      return true;
    }
    return fallback();
  }

  function parseImport(text) {
    var data;
    try { data = JSON.parse(String(text || '').trim()); }
    catch (e) { toast('JSON 解析失败：' + (e.message || '格式错误'), 'bad', 2600); return null; }
    if (!isRecord(data) || !isRecord(data.progress) ||
        (data.app !== undefined && data.app !== APP_NAME) ||
        (data.ver !== undefined && data.ver !== EXPORT_VER)) {
      toast('不是支持的军理刷题备份（progress须为对象，应用与版本须匹配）', 'bad', 2600);
      return null;
    }
    return data;
  }

  function mergeProgress(a, b) {
    a = sanitizeProgress(a); b = sanitizeProgress(b);
    var out = {};
    [a, b].forEach(function (src) {
      if (src) Object.keys(src).forEach(function (k) {
        if (k === KEY_DAILY) return;                 // 按日期记录单独合并，不能当题目条目
        out[k] = src[k];
      });
    });
    Object.keys(out).forEach(function (k) { out[k] = ensureShape(out[k]); });
    if (a && b) {
      Object.keys(b).forEach(function (k) {
        if (k === KEY_DAILY) return;
        if (!a[k]) { out[k] = ensureShape(b[k]); return; }
        var x = ensureShape(a[k]), y = ensureShape(b[k]);
        var box = Math.max(x.box, y.box);
        out[k] = {
          seen: x.seen + y.seen, correct: x.correct + y.correct, wrong: x.wrong + y.wrong,
          lastTs: Math.max(x.lastTs, y.lastTs), box: box,
          fav: !!(x.fav || y.fav),
          wrongFlag: !!((x.wrongFlag || y.wrongFlag) && box < 3)
        };
      });
    }
    return out;
  }
  function ensureShape(p) {
    p = isRecord(p) ? p : {};
    var correct = Math.max(0, toInt(p.correct, 0)), wrong = Math.max(0, toInt(p.wrong, 0));
    return {
      seen: Math.max(0, toInt(p.seen, 0), correct + wrong), correct: correct, wrong: wrong,
      lastTs: Math.max(0, toInt(p.lastTs, 0)), box: clamp(toInt(p.box, 0), 0, 5),
      fav: !!p.fav, wrongFlag: !!p.wrongFlag
    };
  }

  /** 启动与导入共用清洗，保留尚未在当前题库出现的合法题号记录。 */
  function sanitizeProgress(src) {
    var out = {};
    if (isRecord(src)) Object.keys(src).forEach(function (id) {
      if (id === KEY_DAILY || ['__proto__', 'constructor', 'prototype'].indexOf(id) >= 0 || !isRecord(src[id])) return;
      out[id] = ensureShape(src[id]);
    });
    out[KEY_DAILY] = sanitizeDaily(isRecord(src) ? src[KEY_DAILY] : null);
    return out;
  }

  /** 成绩按时间标识去重；坏记录不进入可渲染历史，分数从合法计数计算。 */
  function sanitizeExams(src) {
    var out = [], seen = {};
    (Array.isArray(src) ? src : []).forEach(function (x) {
      if (!isRecord(x)) return;
      var ts = toInt(x.ts, 0), total = toInt(x.total, 0);
      if (ts <= 0 || ts > 8640000000000000 || total <= 0 || seen[ts]) return;
      seen[ts] = true;
      var correct = clamp(toInt(x.correct, 0), 0, total);
      out.push({ ts: ts, total: total, correct: correct, score: pct(correct, total),
        durationMs: Math.max(0, toInt(x.durationMs, 0)), detail: Array.isArray(x.detail) ? x.detail.filter(isRecord) : [] });
    });
    return out.sort(function (a, b) { return b.ts - a.ts; }).slice(0, 50);
  }

  function applyImport(data, mode) {
    var n = 0;
    // 导入文件里的按日期记录：优先取顶层 `daily`，兼容只写在 progress._daily 的形态
    var incomingDaily = sanitizeDaily(
      (data.daily && typeof data.daily === 'object') ? data.daily : (data.progress || {})[KEY_DAILY]);
    if (mode === 'replace') {
      State.progress = sanitizeProgress(data.progress);
      n = progressIds().length;
      State.progress[KEY_DAILY] = incomingDaily;
      State.exams = sanitizeExams(data.exams);
      // 覆盖导入等于换了一份进度：旧练习会话里的作答已不属于新进度，必须一并作废，
      // 否则首页「继续上次练习」会恢复出一份已不存在的会话。
      rawDel(KEY_SESSION); rawDel(KEY_RECITE); rawDel(KEY_EXAM_SESSION); stopExamTimer();
      if (sessSaveTimer) { clearTimeout(sessSaveTimer); sessSaveTimer = 0; }
      State.sess = null; State.lastSess = null; State.exam = null;
      State.reciteQ = ''; State.reciteSearchOpen = false;
      if (data.settings && typeof data.settings === 'object') {
        State.settings = Object.assign({}, DEFAULT_SETTINGS, data.settings);
        syncSettings(); saveSettings(); applyTheme();
      }
    } else {
      // 合并导入：先把本机的「按日期作答记录」取出来再合并 ——
      // mergeProgress 会跳过保留键 __daily，不先取出的话本机那部分会被导入文件覆盖。
      var localDaily = State.progress[KEY_DAILY];
      State.progress = mergeProgress(State.progress, data.progress || {});
      State.progress[KEY_DAILY] = mergeDaily(localDaily, incomingDaily);
      n = Object.keys(data.progress || {}).filter(function (k) { return k !== KEY_DAILY; }).length;
      State.exams = sanitizeExams(State.exams.concat(Array.isArray(data.exams) ? data.exams : []));
    }
    saveProgress(); saveExams();
    invalidateStats();          // 进度整批换过：统计缓存必须作废，否则首页/侧栏还是导入前的旧数字
    State.meta.lastExportTs = Date.now(); saveMeta();
    updateBadges();
    render(false);
    var dailyDays = Object.keys(State.progress[KEY_DAILY] || {}).length;
    toast('导入成功（' + (mode === 'replace' ? '覆盖' : '合并') + '）：' + n + ' 条进度记录' +
      (dailyDays ? ' · 含 ' + dailyDays + ' 天作答记录' : ''), 'ok', 2600);
  }

  VIEWS.sync = function () {
    var d = derive();
    var text = exportText();
    // 「声音与震动」已迁到「设置」页（2026-10-09），此处只保留导入/导出相关
    return '<div class="card"><div class="card-title">导出进度</div>' +
      '<div class="small dim">把当前进度（答题记录、**按日期的作答记录**、收藏、设置、考试成绩）导出为 JSON，' +
      '用于备份或在 iPhone ↔ Windows 之间手动同步。按日期的记录让「近 7 天做题量」在换设备后仍然准确。</div>' +
      '<div class="grid grid-3 mt10">' +
      '<div class="stat"><b>' + d.done + '</b><span>已做</span></div>' +
      '<div class="stat"><b>' + d.rate + '%</b><span>作答正确率</span></div>' +
      '<div class="stat"><b>' + Object.keys(State.progress[KEY_DAILY] || {}).length + '</b><span>作答天数</span></div>' +
      '</div>' +
      '<div class="btn-row mt16">' +
      '<button class="btn primary" type="button" data-act="sync:download">导出为文件</button>' +
      '<button class="btn" type="button" data-act="sync:copy">复制到剪贴板</button>' +
      '</div>' +
      '<div class="field mt16 mb0"><label>导出内容（可长按全选手动复制）</label>' +
      '<textarea class="sync-area" id="export-area" readonly>' + esc(text) + '</textarea></div>' +
      (State.meta.lastExportTs ? '<div class="small muted mt6">上次导出：' + fmtDate(State.meta.lastExportTs) + '</div>' : '') +
      '</div>' +

      '<div class="card"><div class="card-title">导入进度</div>' +
      '<div class="note">「合并」会把两边数据相加（同一题答对答错次数累加，熟练度取较高值）；「覆盖」会清空本机进度后写入导入内容。</div>' +
      '<div class="field mt16"><label>① 从文件导入</label>' +
      '<div class="btn-row"><button class="btn" type="button" data-act="sync:pick">选择 JSON 文件…</button></div></div>' +
      '<div class="field"><label>② 粘贴 JSON 文本导入</label>' +
      '<textarea class="sync-area" id="import-area" placeholder="把另一台设备上导出的 JSON 粘贴到这里…"></textarea>' +
      '<div class="btn-row mt10">' +
      '<button class="btn primary" type="button" data-act="sync:merge">合并导入</button>' +
      '<button class="btn danger" type="button" data-act="sync:replace">覆盖导入</button>' +
      '</div></div>' +
      '<div class="small muted">导入文件格式：<code>{ app, ver, exportedAt, progress, settings, exams }</code></div>' +
      '</div>' +

      '<div class="card"><div class="card-title">危险操作</div>' +
      '<div class="btn-row"><button class="btn danger" type="button" data-act="sync:reset">清空本机全部数据</button></div>' +
      '<div class="small muted mt6">会删除答题进度、错题本、收藏与成绩记录（不可恢复，建议先导出备份）。</div>' +
      '</div>';
  };

  reg('sync:download', function () {
    var text = exportText();
    var ok = downloadText(exportFileName(), text);
    State.meta.lastExportTs = Date.now(); saveMeta();
    if (ok) toast('已导出文件', 'ok', 2000);
    else { render(false); toast('当前浏览器不支持直接下载，请长按下方文本框复制', 'bad', 3200); }
  });
  reg('sync:copy', function () { copyText(exportText(), '进度 JSON 已复制到剪贴板'); });
  reg('sync:pick', function () {
    var f = $('#import-file');
    if (f) f.click();
  });
  reg('sync:merge', function () { doImportFromArea('merge'); });
  reg('sync:replace', function () { doImportFromArea('replace'); });

  function doImportFromArea(mode) {
    var ta = $('#import-area');
    if (!ta || !ta.value.trim()) { toast('请先粘贴 JSON 文本或选择文件', 'bad', 2000); return; }
    var data = parseImport(ta.value);
    if (!data) return;
    var n = Object.keys(data.progress || {}).filter(function (k) { return k !== KEY_DAILY; }).length;
    confirmBox(mode === 'replace' ? '覆盖导入' : '合并导入',
      (mode === 'replace' ? '将清空本机现有进度并写入 ' : '将与本机现有进度合并，共 ') + n + ' 条记录，确定吗？',
      '确定导入', function () { applyImport(data, mode); });
  }

  function doImportFromFile(file) {
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      var data = parseImport(reader.result);
      if (data) {
        var n = Object.keys(data.progress || {}).filter(function (k) { return k !== KEY_DAILY; }).length;
        openModal({
          title: '从文件导入',
          html: '<p>文件包含 ' + n + ' 条进度记录。选择导入方式：合并＝保留本机数据并累加；覆盖＝清空本机数据。</p>',
          buttons: [
            { label: '取消', cls: 'ghost' },
            { label: '合并导入', cls: 'primary', onClick: function () { applyImport(data, 'merge'); } },
            { label: '覆盖导入', cls: 'danger', onClick: function () { applyImport(data, 'replace'); } }
          ]
        });
      }
      var f = $('#import-file');
      if (f) f.value = '';
    };
    reader.onerror = function () { toast('文件读取失败', 'bad'); };
    reader.readAsText(file, 'utf-8');
  }

  reg('sync:reset', function () {
    confirmBox('清空全部数据', '将删除本机全部答题进度、错题、收藏与考试成绩，且无法恢复。确定吗？', '全部清空', function () {
      State.progress = { __daily: {} }; State.exams = []; State.settings = Object.assign({}, DEFAULT_SETTINGS);
      State.meta = { bankHash: State.meta.bankHash, ver: EXPORT_VER, lastExportTs: 0 };
      saveProgress(); saveExams(); saveSettings(); saveMeta();
      State.sess = null; State.exam = null;
      State.lastSess = null; stopExamTimer();
      if (sessSaveTimer) { clearTimeout(sessSaveTimer); sessSaveTimer = 0; }
      rawDel(KEY_SESSION); rawDel(KEY_EXAM_SESSION);
      State.reciteQ = ''; State.reciteSearchOpen = false; rawDel(KEY_RECITE);
      applyTheme(); updateBadges(); render(false);
      toast('已清空本机数据', 'ok', 2000);
    });
  });

  /* ======================================================================
   * 19. 全局事件绑定 / 快捷键 / 误触防护
   * ==================================================================== */
  function closestAct(el) {
    while (el && el !== document) {
      if (el.getAttribute && (el.hasAttribute('data-act') || el.hasAttribute('data-nav'))) return el;
      el = el.parentNode;
    }
    return null;
  }

  /* ======================================================================
   * 18.5 反馈模块（+）：音效（Web Audio 实时合成）+ 震动（navigator.vibrate）
   *  - 零外部音频文件；所有调用都包 try/catch，反馈失败绝不影响功能
   *  - 只在 bindGlobal 的派发点 + 少数几个独立监听 + 键盘路径挂钩，不散落到 reg() 回调
   *  - iOS 震动：navigator.vibrate 不存在 ⇒ 静默跳过（系统未开放，无解）
   *  - iOS 静音键（「双通道」策略）：
   *      主通道   = Web Audio 合成（音色好、零体积）
   *      保活通道 = 常驻的静音循环 <audio>（内联 WAV data URL）
   *    原理（社区验证，参考 swevans/unmute）：iOS 把音频会话切到 <audio>/<video>
   *    元素后不受静音键影响，而 Web Audio 会；让静音音轨常驻播放就能把音频会话
   *    保持在「媒体播放」类别，从而让 Web Audio 也绕过静音键。
   *  - AudioContext 惰性创建，且首次一定发生在用户手势（click/keydown）里
   * ==================================================================== */
  var AudioCtx = null;

  function ensureAudio() {
    try {
      if (AudioCtx) {
        if (AudioCtx.state === 'suspended' && AudioCtx.resume) {
          AudioCtx.resume()['catch'](function () { /* noop */ });
        }
        return AudioCtx;
      }
      var Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return null;
      AudioCtx = new Ctor();
      if (AudioCtx.state === 'suspended' && AudioCtx.resume) {
        AudioCtx.resume()['catch'](function () { /* noop */ });
      }
    } catch (e) { AudioCtx = null; }
    return AudioCtx;
  }

  /* ----iOS 静音键兼容用的常驻静音音轨 ---------------------------- */

  /**
   * 现场按 RIFF/WAVE 规范逐字节生成一段静音 PCM 的 data URL。
   * 为什么不直接硬编码 base64：WAV 头是字节精确的二进制格式，手写约 6KB base64
   * 在本机无法验证，一位写错整段就解不出来；这里按字段写入，结果完全等价且不可能写错。
   * 规格：44.1kHz / 单声道 / 16bit，时长 seconds（默认 0.05s ≈ 4454B，base64 约 5.9KB）。
   */
  function buildSilentWavUrl(seconds) {
    var rate = 44100, bits = 16, ch = 1;
    var frames = Math.max(1, Math.round(rate * seconds));
    var dataSize = frames * ch * (bits / 8);           // 2205 帧 × 2B = 4410B
    var buf = new ArrayBuffer(44 + dataSize);          // 44B 标准 PCM 头 + 数据
    var view = new DataView(buf);
    var pos = 0;
    function putStr(s) { for (var i = 0; i < s.length; i++) view.setUint8(pos++, s.charCodeAt(i)); }
    function putU32(v) { view.setUint32(pos, v, true); pos += 4; }
    function putU16(v) { view.setUint16(pos, v, true); pos += 2; }
    putStr('RIFF'); putU32(36 + dataSize); putStr('WAVE');
    putStr('fmt '); putU32(16); putU16(1); putU16(ch);
    putU32(rate); putU32(rate * ch * bits / 8); putU16(ch * bits / 8); putU16(bits);
    putStr('data'); putU32(dataSize);
    // pos 之后全部保持 0 —— 即静音采样
    var bytes = new Uint8Array(buf);
    var bin = '';
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return 'data:audio/wav;base64,' + btoa(bin);
  }

  var silentTrack = null;
  var silentUrl = null;

  /** 常驻静音音轨：首次用户手势里创建，之后每次播放前确保仍在播 */
  function ensureSilentTrack() {
    try {
      if (silentTrack) {
        if (silentTrack.paused && silentTrack.play) {
          var p0 = silentTrack.play();
          if (p0 && p0['catch']) p0['catch'](function () { /* noop */ });
        }
        return silentTrack;
      }
      if (!silentUrl) silentUrl = buildSilentWavUrl(0.05);
      var a = document.createElement('audio');
      a.id = 'jlx-silent-track';
      a.setAttribute('data-jlx-silent', '1');
      a.setAttribute('aria-hidden', 'true');
      a.loop = true;
      a.playsInline = true;
      a.setAttribute('playsinline', '');
      a.setAttribute('webkit-playsinline', '');
      a.preload = 'auto';
      // 关键：volume 是「极小非零」而不是 0，且 muted 必须为 false。
      // 任一写成静音属性，iOS 都会把会话归入 ambience 类别，绕过即失效。
      a.volume = 0.001;
      a.muted = false;
      a.src = silentUrl;
      a.style.display = 'none';
      silentTrack = a;
      try { document.body.appendChild(a); } catch (e0) { /* 插不进 DOM 也照样尝试播 */ }
      var pr = a.play();
      if (pr && pr['catch']) pr['catch'](function () { /* 自动播放被拦：静默忽略 */ });
    } catch (e) { /* 反馈绝不影响功能 */ }
    return silentTrack;
  }

  function pauseSilentTrack() {
    try { if (silentTrack && !silentTrack.paused) silentTrack.pause(); } catch (e) { /* noop */ }
  }

  /* 音效基准增益（×1000 的整数，避免浮点误差；播放时再按音量档位缩放）。
   * 数值＝原 SOUND 表增益的 3 倍＝「中档」，因此默认设置下音量即比历史版本明显提升。 */
  var GAIN_BASE = {
    tap: 150, confirm: 210, correct: 312, wrong: 210,
    fav: 180, tick: 105, complete: 240, danger: 270
  };
  /* 音量档位倍率（×100）：小=2 倍、中=3 倍（默认）、大=4 倍，对齐用户选择 */
  var VOLUME_MULT = { 1: 200, 2: 300, 3: 400 };
  var DEFAULT_VOLUME = 2;
  /* 答对音单独加权 1.3 倍（用户要求「强化答对音」） */
  var CORRECT_EXTRA = 130;

  /** 当前音量档位对应的增益缩放（×100） */
  function volumeMult() {
    var v = (State.settings && State.settings.volume) || DEFAULT_VOLUME;
    return VOLUME_MULT[v] || VOLUME_MULT[DEFAULT_VOLUME];
  }
  /** 某语义音效的最终峰值增益（0~1 的浮点） */
  function gainOf(semantic) {
    var base = GAIN_BASE[semantic] || 150;
    if (semantic === 'correct') base = Math.round(base * CORRECT_EXTRA / 100);
    return base * volumeMult() / 100000;
  }

  /** 单音：attack 5ms / 指数 release，避免爆音；音量走 gainOf() */
  function tone(ctx, freq, at, dur, semantic, type, glideTo) {
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    var vol = gainOf(semantic);
    osc.type = type || 'sine';
    osc.frequency.setValueAtTime(freq, at);
    if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, at + dur);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(vol, at + 0.005);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(at);
    osc.stop(at + dur + 0.03);
  }

  /** 语义 → 音色编排（音量由 GAIN_BASE + 音量档位决定，不写在这里） */
  var SOUND = {
    tap:      function (c, t) { tone(c, 1200, t, 0.035, 'tap', 'sine'); },
    confirm:  function (c, t) { tone(c, 523.25, t, 0.075, 'confirm', 'sine'); tone(c, 783.99, t + 0.08, 0.085, 'confirm', 'sine'); },
    correct:  function (c, t) { tone(c, 523.25, t, 0.06, 'correct', 'sine'); tone(c, 659.25, t + 0.055, 0.06, 'correct', 'sine'); tone(c, 783.99, t + 0.11, 0.09, 'correct', 'sine'); },
    wrong:    function (c, t) { tone(c, 330, t, 0.09, 'wrong', 'triangle'); tone(c, 220, t + 0.085, 0.13, 'wrong', 'triangle'); },
    fav:      function (c, t) { tone(c, 1568, t, 0.055, 'fav', 'sine', 2093); },
    tick:     function (c, t) { tone(c, 1500, t, 0.022, 'tick', 'sine'); },
    complete: function (c, t) { tone(c, 523.25, t, 0.07, 'complete', 'sine'); tone(c, 659.25, t + 0.09, 0.07, 'complete', 'sine'); tone(c, 783.99, t + 0.18, 0.07, 'complete', 'sine'); tone(c, 1046.5, t + 0.27, 0.13, 'complete', 'sine'); },
    danger:   function (c, t) { tone(c, 180, t, 0.16, 'danger', 'triangle', 140); }
  };

  var HAPTIC = {
    tap: 10, confirm: 12, correct: 18, wrong: [28, 45, 28], fav: 14,
    tick: 8, complete: [16, 40, 16, 40, 34], danger: [40, 60, 40]
  };

  /** data-act → 语义 */
  var ACT_SEMANTIC = {
    'ans:pick': 'tap', 'ans:submit': 'confirm', 'ans:reveal': 'confirm', 'ans:self': 'tap',
    'nav:next': 'tap', 'nav:prev': 'tap', 'nav:jump': 'tap',
    'grid:toggle': 'tick', 'sess:exit': 'tap', 'fav': 'fav',
    'set:order': 'tap', 'set:switch': 'tap', 'set:feedback': 'tap', 'set:volume': 'tap',
    'prac:start': 'confirm', 'prac:chapter': 'confirm', 'prac:type': 'confirm', 'prac:continue': 'confirm',
    'home:continue': 'confirm', 'home:startall': 'confirm', 'home:mode': 'confirm',
    'set:font': 'tap', 'set:theme': 'tap',
    'recite:start': 'confirm', 'recite:chapter': 'confirm', 'q:practice': 'confirm',
    'exam:new': 'tap', 'exam:count': 'tap', 'exam:min': 'tap', 'exam:scope': 'tap', 'exam:short': 'tap',
    'exam:start': 'confirm', 'exam:submit': 'confirm', 'exam:scoredone': 'complete', 'exam:detail': 'tap',
    'exam:clear': 'danger',
    'wrong:redo': 'confirm', 'wrong:recite': 'confirm', 'wrong:remove': 'tap', 'wrong:clear': 'danger',
    'fav:practice': 'confirm', 'fav:recite': 'confirm',
    'search:go': 'confirm', 'search:practice': 'confirm', 'search:recite': 'confirm',
    'sync:download': 'confirm', 'sync:copy': 'confirm', 'sync:pick': 'confirm',
    'sync:merge': 'confirm', 'sync:replace': 'danger', 'sync:reset': 'danger',
    'explain:toggle': 'tick',
    'nav:go': 'tap', 'modal:ok': 'confirm', 'modal:cancel': 'tap'
  };

  var lastPlay = {};
  var Feedback = {
    /** 按语义播放：同步、极轻、60ms 去抖、任何异常都吞掉 */
    play: function (semantic) {
      try {
        if (!semantic) return;
        var now = Date.now();
        if (lastPlay[semantic] && now - lastPlay[semantic] < 60) return;
        lastPlay[semantic] = now;
        if (State.settings.haptic) {
          try {
            if (typeof navigator.vibrate === 'function') navigator.vibrate(HAPTIC[semantic] || 10);
          } catch (e) { /* 反馈绝不影响功能 */ }
        }
        if (State.settings.sound) {
          ensureSilentTrack();   // iOS 静音键兼容：与 AudioContext 同一手势内启动常驻静音音轨
          var ctx = ensureAudio();
          if (ctx && SOUND[semantic]) SOUND[semantic](ctx, ctx.currentTime + 0.001);
        }
      } catch (e2) { /* 反馈绝不影响功能 */ }
    },
    /** 按 data-act 自动映射 */
    fire: function (act) {
      try { Feedback.play(ACT_SEMANTIC[act]); } catch (e) { /* noop */ }
    },
    /** 判分结果（由 submitPractice 在判分后回调一次） */
    result: function (ok) {
      try { Feedback.play(ok ? 'correct' : 'wrong'); } catch (e) { /* noop */ }
    },
    /** 供/ Playwright 观察 AudioContext 是否已创建 */
    audioCtx: function () { return AudioCtx; },
    /** 供/ Playwright 观察常驻静音音轨（iOS 静音键兼容） */
    silentTrack: function () { return silentTrack; },
    pauseSilentTrack: function () { pauseSilentTrack(); }
  };

  var touchInfo = { t: 0, x: 0, y: 0, long: false, moved: false };

  function bindGlobal() {
    // 280ms 合并输入，输入法组词期间不替换结果；离页即取消回调。
    function scheduleWrongSearch(e) {
      var el = closestAct(e.target);
      if (!el || el.getAttribute('data-act') !== 'wrong:search') return;
      State.wrongQ = String(el.value || '');
      cancelWrongSearch();
      if (e.isComposing || wrongSearchComposing) return;
      wrongSearchTimer = setTimeout(function () {
        wrongSearchTimer = 0;
        renderWrongSearchResults();
      }, 280);
    }
    document.addEventListener('input', scheduleWrongSearch);
    document.addEventListener('compositionstart', function (e) {
      var el = closestAct(e.target);
      if (!el || el.getAttribute('data-act') !== 'wrong:search') return;
      wrongSearchComposing = true; cancelWrongSearch();
    });
    document.addEventListener('compositionend', function (e) {
      wrongSearchComposing = false; scheduleWrongSearch(e);
    });
    document.addEventListener('click', function (e) {
      var el = closestAct(e.target);
      if (!el) return;
      if (touchInfo.long || touchInfo.moved) { touchInfo.long = false; touchInfo.moved = false; return; }
      if (el.hasAttribute('data-nav')) {
        var nav = el.getAttribute('data-nav');
        Feedback.fire('nav:go');
        go(nav, nav === 'practice' ? {} : undefined);
        return;
      }
      var act = el.getAttribute('data-act');
      if (act) Feedback.fire(act);
      if (act && typeof ACT[act] === 'function') { ACT[act](el, e); }
    }, false);

    document.addEventListener('input', function (e) {
      var el = closestAct(e.target);
      if (!el) return;
      var act = el.getAttribute('data-act');
      if (act === 'recite:search') {
        State.reciteQ = String(el.value || '');
        State.reciteSearchOpen = true;
        renderReciteSearchResults(); saveSession();
        return;
      }
      if (act === 'search:input') {
        State.p.q = el.value;
        renderSearchResults();
        return;
      }
      if (act && typeof ACT[act] === 'function') ACT[act](el, e);
    }, false);

    document.addEventListener('change', function (e) {
      var el = closestAct(e.target);
      if (!el) return;
      var act = el.getAttribute('data-act');
      if (act === 'exam:count-in' || act === 'exam:min-in') { Feedback.play('tap'); ACT[act](el, e); }
    }, false);

    var fileEl = $('#import-file');
    if (fileEl) {
      fileEl.addEventListener('change', function () {
        if (fileEl.files && fileEl.files[0]) doImportFromFile(fileEl.files[0]);
      });
    }

    var back = $('#btn-back');
    if (back) back.addEventListener('click', function () {
      Feedback.fire('nav:go');
      if (leaveRunningExam('home')) return;
      go('home');
    });
    var themeBtn = $('#btn-theme');
    if (themeBtn) themeBtn.addEventListener('click', function () {
      Feedback.play('tap'); cycleTheme();
      if (State.route === 'settings') render(false);   // 设置页上有「当前主题」，不重绘会与真实值不符
    });
    var fontBtn = $('#btn-font');
    if (fontBtn) fontBtn.addEventListener('click', function () {
      Feedback.play('tap'); cycleFont();
      if (State.route === 'settings') render(false);
    });

    var back2 = $('#modal-backdrop');
    if (back2) back2.addEventListener('click', function (e) {
      if (e.target === back2) { Feedback.fire('modal:cancel'); closeModal(); }
    });

    document.addEventListener('keydown', onKeydown, false);

    window.addEventListener('hashchange', function () {
      if (suppressHash) { suppressHash = false; return; }
      var r = currentRouteFromHash();
      if (r !== State.route) {
        // 浏览器返回同样走离场确认；先还原考试地址，取消后仍留在原页。
        if (State.route === 'exam' && State.exam && State.exam.phase === 'run' && !State.exam.paused) {
          suppressHash = true; window.location.hash = '#/exam';
        }
        go(r);
      }
    }, false);

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { pauseExam(); flushSession(); }
      else if (State.route === 'exam' && State.exam && State.exam.paused && State.exam.phase === 'run') render(false);
      else tickClock();
    }, false);
    function saveBeforePageClose() { pauseExam(); flushSession(); }
    window.addEventListener('pagehide', saveBeforePageClose, false);
    window.addEventListener('beforeunload', saveBeforePageClose, false);
    window.addEventListener('scroll', function () {
      if (State.route !== 'recite' || !State.sess || State.sess.mode !== 'recite') return;
      State.sess.scrollY = Math.max(0, toInt(window.scrollY || window.pageYOffset, 0));
      saveSessionSoon();
    }, { passive: true });

    // 误触防护：禁止 iOS 双击缩放手势
    ['gesturestart', 'gesturechange', 'gestureend'].forEach(function (ev) {
      document.addEventListener(ev, function (e) { e.preventDefault(); }, { passive: false });
    });
    // 长按不弹出系统菜单（输入框除外）
    document.addEventListener('contextmenu', function (e) {
      var t = e.target;
      var typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      if (!typing) e.preventDefault();
    }, false);

    document.addEventListener('touchstart', function (e) {
      var t = e.touches && e.touches[0];
      touchInfo.t = Date.now();
      touchInfo.x = t ? t.clientX : 0;
      touchInfo.y = t ? t.clientY : 0;
      touchInfo.long = false; touchInfo.moved = false;
    }, { passive: true });

    document.addEventListener('touchend', function (e) {
      var t = e.changedTouches && e.changedTouches[0];
      var moved = t ? (Math.abs(t.clientX - touchInfo.x) + Math.abs(t.clientY - touchInfo.y)) : 0;
      var dt = Date.now() - touchInfo.t;
      touchInfo.moved = moved > 14;       // 滑动（防误点）
      touchInfo.long = (dt > 700 && moved <= 14);  // 长按
    }, { passive: true });

    window.addEventListener('resize', debounce(function () {
      if (State.route === 'practice' || State.route === 'recite' || State.route === 'exam') return;
      render(false);
    }, 400));
  }

  function onKeydown(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    var tag = t && t.tagName ? t.tagName.toUpperCase() : '';
    var typing = tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable);
    var key = e.key;

    // Esc：关弹层 / 取消聚焦 / 回首页
    if (key === 'Escape' || key === 'Esc') {
      var back = $('#modal-backdrop');
      if (back && !back.hidden) { closeModal(); e.preventDefault(); return; }
      if (typing) { try { t.blur(); } catch (er) { /* noop */ } return; }
      if (State.route !== 'home') { go('home'); e.preventDefault(); }
      return;
    }
    var modalOpen = (function () { var b = $('#modal-backdrop'); return b && !b.hidden; })();
    if (modalOpen) return;

    if (typing) {
      // 填空框内回车 = 提交
      if (key === 'Enter' && tag === 'INPUT' && t.getAttribute('data-act') === 'ans:fill') {
        e.preventDefault();
        if (State.route === 'exam') { examSaveDraft(); move(1); }
        else if (typeof ACT['ans:submit'] === 'function') ACT['ans:submit'](t, e);
      }
      return;
    }

    // 暂停、设置和自评页面没有可修改的考试题卡。
    var inQ = (State.route === 'practice' || State.route === 'recite' ||
      (State.route === 'exam' && State.exam && State.exam.phase === 'run' && !State.exam.paused));
    if (key === 's' || key === 'S') {
      Feedback.play('tap');
      var reciteInput = State.route === 'recite' ? $('#recite-search-input') : null;
      if (reciteInput) reciteInput.focus(); else go('search');
      e.preventDefault(); return;
    }
    if (key === 'ArrowLeft') { if (inQ) { Feedback.play('tap'); move(-1); e.preventDefault(); } return; }
    if (key === 'ArrowRight') { if (inQ) { Feedback.play('tap'); move(1); e.preventDefault(); } return; }
    if (key === 'Home') { Feedback.play('tap'); go('home'); e.preventDefault(); return; }
    if (key === 'f' || key === 'F') {
      if (inQ) {
        var q = currentQ();
        if (q) { Feedback.fire('fav'); var on = toggleFav(q.id); toast(on ? '已加入收藏' : '已取消收藏', '', 1000); render(false); }
      }
      e.preventDefault(); return;
    }
    if (key === 'Enter') {
      if (!inQ) return;
      e.preventDefault();
      if (State.route === 'exam') {
        examSaveDraft();
        var c = State.exam;
        if (!c || c.phase !== 'run') return;
        if (c.i < c.ids.length - 1) { Feedback.play('tap'); move(1); } else { Feedback.fire('exam:submit'); ACT['exam:submit'](); }
        return;
      }
      var cur = currentQ();
      if (!cur) return;
      var cont = State.sess;
      var r = cont.res[cur.id];
      if (r) { Feedback.play('tap'); move(1); return; }
      if (cur.type === 'short' && cont.revealedRef && cont.revealedRef[cur.id]) return; // 等待自评
      Feedback.fire('ans:submit');
      ACT['ans:submit']();
      return;
    }
    if (/^[1-9]$/.test(key)) {
      if (!inQ) return;
      e.preventDefault();
      var n = parseInt(key, 10);
      var cont2 = activeContainer();
      var q2 = currentQ();
      if (!cont2 || !q2) return;
      if (State.route === 'recite') return;
      if (State.route === 'exam' && State.exam.phase !== 'run') return;
      if (State.route === 'practice') {
        var s2 = State.sess;
        if (s2.res[q2.id]) return;
        if (q2.type === 'short' && s2.revealedRef && s2.revealedRef[q2.id]) return;
      }
      Feedback.fire('ans:pick');
      // 判断题只有「1 = 正确 / 2 = 错误」两个有效键，3~9 一律忽略。
      // 此前 n>=3 被映射成 null，ans:pick 里 (k === 'true') 得 false，
      // 于是「随手按个数字」就把题判成错误、锁定并记进错题本（考试中更会被悄悄改成「错误」）。
      if (q2.type === 'judge') {
        if (n > 2) return;
        ACT['ans:pick']({ getAttribute: function () { return n === 1 ? 'true' : 'false'; }, classList: { toggle: function () {} }, querySelector: function () { return null; } }, e);
        return;
      }
      var opts = dispOpts(q2, cont2);
      if (n > opts.length) return;
      var letter = opts[n - 1].orig;
      var fake = { getAttribute: function (k) { return k === 'data-k' ? letter : null; } };
      ACT['ans:pick'](fake, e);
      return;
    }
  }

  function currentQ() {
    if (State.route === 'exam') return examCurrent();
    return sessCurrent();
  }

  /* ======================================================================
   * 20. Service Worker 注册（仅 http/https；file:// 直接跳过）
   * ==================================================================== */
  function registerSW() {
    var swc = swContainer();
    if (!swc) return;
    var proto = (window.location && window.location.protocol) || '';
    if (proto !== 'http:' && proto !== 'https:') return;
    var doReg = function () {
      swc.register('sw.js')['catch'](function () { /* 离线注册失败不影响使用 */ });
    };
    if (document.readyState === 'complete') doReg();
    else window.addEventListener('load', doReg);
  }

  /** http/https 下注入 PWA manifest；file:// 不注入（避免 CORS 控制台报错） */
  function ensureManifest() {
    var proto = (window.location && window.location.protocol) || '';
    if (proto !== 'http:' && proto !== 'https:') return;
    if (document.querySelector('link[rel="manifest"]')) return;
    try {
      var link = document.createElement('link');
      link.rel = 'manifest';
      link.href = 'manifest.webmanifest';
      document.head.appendChild(link);
    } catch (e) { /* noop */ }
  }

  /* ======================================================================
   * 21. 启动
   * ==================================================================== */
  function boot() {
    initState();
    applyTheme();

    var bootTimer = setTimeout(function () {
      // 极端情况下的兜底：即使 Promise 卡住也先渲染一版 UI
      if (State.route === 'home' && !State.questions.length) {
        State.questions = buildBank(MOCK_BANK);
        indexQuestions();
        State.from = '内置示例题库（mock）';
        render(true);
      }
    }, 6000);

    loadBank().then(function (res) {
      clearTimeout(bootTimer);
      State.bank = res.bank;
      State.from = res.from || '';
      State.questions = buildBank(res.bank);
      indexQuestions();
      if (!State.questions.length) {
        State.questions = buildBank(MOCK_BANK);
        indexQuestions();
        State.from = '内置示例题库（mock）';
      }
      var h = hashStr(State.questions.map(function (q) { return q.id + ':' + q.type; }).join('|'));
      var changed = !!State.meta.bankHash && State.meta.bankHash !== h;
      State.meta.bankHash = h;
      State.meta.ver = EXPORT_VER;
      saveMeta();
      State.route = currentRouteFromHash();
      render(true);
      if (changed) toast('题库已更新，学习进度按题目 ID 保留', '', 3000);
      maybeShowNotice();     // 开屏公告：每个版本只自动弹一次
    })['catch'](function () {
      clearTimeout(bootTimer);
      // 绝不白屏
      try {
        State.questions = buildBank(MOCK_BANK);
        indexQuestions();
        State.from = '内置示例题库（mock）';
        State.route = currentRouteFromHash();
        render(true);
      } catch (e) {
        var v = $('#view');
        if (v) v.innerHTML = '<div class="card"><h2 class="card-title">加载失败</h2><div class="note">' + esc(e && e.message ? e.message : String(e)) + '</div></div>';
      }
    });
  }

  function indexQuestions() {
    State.byId = {};
    State.chapters = [];
    var seen = {};
    State.questions.forEach(function (q) {
      State.byId[q.id] = q;
      if (!seen[q.chapter]) { seen[q.chapter] = 1; State.chapters.push(q.chapter); }
    });
  }

  function start() {
    bindGlobal();
    ensureManifest();
    boot();
    registerSW();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, false);
  else start();

  // 便于调试：暴露少量只读接口
  window.__JLX__ = {
    version: EXPORT_VER,
    state: State,
    derive: derive,
    deriveUncached: deriveUncached,   // 无缓存版本，供性能测量脚本对比缓存收益
    /* 复习提纲接口（2026-10-09 起内容为【26最新改版】军理课提纲 PDF）。
     * 外部脚本可直接调用：
     *   JSON.stringify(window.__JLX__.outline(), null, 1)
     *   window.__JLX__.outlineMarkdown()   // 直接取 Markdown 提纲
     * 返回结构见上方「19. 复习提纲」注释块（稳定契约）。
     * ⚠ 与旧版不兼容：不再返回按题目聚合的 points，改为 PDF 提纲的 章/节/小节。 */
    outline: function () { return loadOutlineData(); },
    outlineMarkdown: function () { return buildOutlineMarkdown(); },
    exportText: exportText,
    normalizeAnswer: normalizeAnswer,
    // 会话恢复的只读探针（/测试用）：看磁盘会话是否被判为可恢复，以及为什么
    sessionProbe: function () {
      var d = loadJSON(KEY_SESSION, null);
      return {
        hasResumable: hasResumable(),
        stored: !!d,
        ver: d && d.ver,
        idsInBank: !!(d && Array.isArray(d.ids) && d.ids.length
          && d.ids.every(function (id) { return !!State.byId[id]; })),
        idCount: d && d.ids ? d.ids.length : 0,
        missing: (d && Array.isArray(d.ids)) ? d.ids.filter(function (id) { return !State.byId[id]; }) : [],
        lastSessMode: State.lastSess ? State.lastSess.mode : null
      };
    },
    feedback: Feedback,
    MOCK_BANK: MOCK_BANK
  };
})();
