# 题库数据格式说明

> 本文说明 `data/questions.json` 的结构与前端消费方式，供想基于本项目数据做二次开发、校验或自建同类工具的人参考。
> 面向使用者的说明见 [README](../README.md)；题目质量口径见 [题目质量与依据说明.md](题目质量与依据说明.md)。

## 1. `data/questions.json`

顶层是一个对象（**不是**数组）：

```json
{
  "schema": 1,
  "generatedAt": "2026-09-30T00:00:00+08:00",
  "counts": { "single": 200, "multi": 30, "judge": 40, "fill": 20, "short": 10, "total": 300 },
  "sources": ["真题", "模拟题", "提纲", "教程"],
  "questions": [ /* Question[] */ ]
}
```

> ⚠️ **当前实际数据只含 `questions` 一个顶层键**：上面四个元数据字段（`schema` / `generatedAt` /
> `counts` / `sources`）属于**约定含义但尚未写入**，详见 README 的「已知偏差」一节。
> 读取方请对这四个字段做空值容错，不要依赖它们存在。

### Question 对象

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 稳定唯一，格式 `q-0001`（4 位递增，从 1 开始） |
| `type` | string | ✅ | 枚举：`single` \| `multi` \| `judge` \| `fill` \| `short` |
| `stem` | string | ✅ | 题干，已去除选项与答案、去首尾空白；判断题不含末尾「（  ）」 |
| `options` | string[] | 条件 | `single`/`multi` 必填，长度 ≥ 2；**不含** "A." 前缀，是纯选项文本。`judge`/`fill`/`short` 为 `[]` |
| `answer` | string \| string[] \| boolean | ✅ | 见下方「答案规范」 |
| `explanation` | string | ✅ | 解析全文（作答后显示）；当前 1531 / 1531 题非空 |
| `explanationSrc` | string | ✅ | 依据等级：`textbook`（教材原文）\| `web`（权威网页）\| `manual`（人工校订）\| `bank`（题库自带/派生说明）\| `template`（未收录直接出处，如实说明） |
| `explanationRef` | string | ✅ | 出处位置，如 `教材《普通高校军事课教程》·中国国防`；`bank`/`template` 时为空串或来源说明 |
| `source` | string | ✅ | `真题` \| `模拟题` \| `提纲` \| `教程` |
| `chapter` | string | ✅ | 章节名；取不到时为 `未分类` |
| `section` | string | ✅ | 原卷题型标题（如 `一、单选题`）；取不到时为 `""` |
| `explanationParts` | object | ❌ | 结构化解析：`answer`（正确答案行）/ `reason`（为什么）/ `ref`（依据）/ `note`（提示，如派生说明） |
| `answerUncertain` | boolean | ❌ | 仅 `multi` 可能出现且为 `true`：原卷把多选答案压成连续字母串，切分存在固有歧义（当前为 0 道） |
| `raw` | string | ❌ | 原始文本片段（调试用，**不进打包产物**） |
| `webSourceUrl` | string | ❌ | 依据来源的权威网页地址（`explanationSrc = web` 时存在） |

### 答案规范

- `single`：**大写单字母字符串**，如 `"A"`。必须是 `options` 的合法下标字母。
- `multi`：**排序后的大写字母数组**，如 `["A","C","D"]`（升序、无重复）。
- `judge`：**布尔值** `true`（对/正确/√/T）或 `false`（错/错误/×/F）。
- `fill`：**字符串数组**，按空格顺序每个空一个元素，如 `["南昌","1927"]`；无法拆分时长度为 1 的数组。
- `short`：**字符串**，参考答案要点全文（可含换行）。

## 2. 前端怎么消费这份数据

打包后，App 只依赖 `window.__QUESTION_BANK__`（单文件版由 `tools/bundle.py` 注入；
开发时从 `data/questions.json` 读取）：

```js
const bank = window.__QUESTION_BANK__;   // 等价于 questions.json 的内容
bank.questions.forEach(q => { /* ... */ });
```

前端**必须**做防御性归一化：`answer` 可能是 string / array / boolean，统一转成内部表示：

```js
function normalizeAnswer(q) {
  if (q.type === 'single') return String(q.answer).trim().toUpperCase();
  if (q.type === 'multi')  return (Array.isArray(q.answer) ? q.answer : String(q.answer).split(''))
                             .map(s => String(s).trim().toUpperCase()).filter(Boolean).sort();
  if (q.type === 'judge')  return q.answer === true || q.answer === 'true' || q.answer === '对' || q.answer === '正确';
  if (q.type === 'fill')   return (Array.isArray(q.answer) ? q.answer : [q.answer]).map(String);
  return String(q.answer ?? '');
}
```

## 3. 本机存储键名

App 只把数据存在浏览器 `localStorage`，键名如下（不与其他项目共用）：

| 键 | 内容 |
|----|------|
| `jlx.progress.v1` | `{ [questionId]: { seen, correct, wrong, lastTs, box, fav, wrongFlag }, __daily: { 'YYYY-MM-DD': { n, ok } } }`（`__daily` 是保留键，不是题目） |
| `jlx.settings.v1` | `{ theme, fontSize, order, shuffleOptions, autoNext, examCount, examMinutes, explainOpen, sound, haptic, volume }` |
| `jlx.exams.v1` | 考试历史 `[{ ts, total, correct, score, durationMs, detail }]` |
| `jlx.meta.v1` | `{ bankHash, ver, lastExportTs, noticeSeen }` |
| `jlx.session.v1` | 练习会话（用于「继续上次练习」）：`{ ver, ts, title, seed, order, i, ids, res, wrongMode, perm, draft, revealedRef }`；`ver` 不匹配即作废 |
| `jlx.recite.v1` | 背题独立存档，退出、刷新与关页均保留题集、位置、排列、搜索词、展开状态及滚动位置；明确从头开始或清空数据时重置 |
| `jlx.exam-session.v1` | 未完成的考试（仅 `run` / `selfcheck` 阶段；交卷出分后删除）：保存题集、位置、草稿、排列、自评、剩余时间与已用时间。退出、刷新及关页时暂停，重新打开后须主动继续；剩余时间为零时，继续后自动交卷 |

导出文件格式：`{ app: "军理刷题", ver: 1, exportedAt, progress, settings, exams, daily }`
（`daily` 与 `progress.__daily` 是同一份按日期作答记录的两种写法）。

## 4. 文件布局

```text
junli-quiz/
├─ app/                      前端源码（index.html / app.css / app.js / sw.js / manifest / icons）
├─ data/questions.json       题库与解析
├─ tools/                    构建与质检脚本
│  ├─ pdftext.py             纯标准库的 PDF 文字层提取器
│  ├─ parse_questions.py     文本 → 题库 JSON
│  └─ bundle.py              组装单文件版 + PWA 版 + 一键部署 zip
├─ docs/                     数据格式、参考书目、题目质量说明
├─ build/text/*.txt          4 份资料提取出的纯文本（**不随仓库发布**）
├─ qa/                       质检中间产物与浏览器 E2E 套件（**不随仓库发布**）
└─ dist/                     打包产物（**不随仓库发布**，另见 Releases）
```
