# 题库数据格式说明

> 本文说明 `data/questions.json` 的结构与前端消费方式，供想基于本项目数据做二次开发、校验或自建同类工具的人参考。
> 面向使用者的说明见 [README](../README.md)；题目质量口径见 [题目质量与依据说明.md](题目质量与依据说明.md)。

## 1. `data/questions.json`

顶层是一个对象（**不是**数组），**当前实际数据只有一个键**：

```json
{ "questions": [ /* Question[] */ ] }
```

历史上还约定了四个元数据字段 —— `schema`（格式版本）、`generatedAt`（生成时间）、
`counts`（各题型数量与总数）、`sources`（来源清单）。若它们存在，形如：

```json
{
  "schema": 1,
  "generatedAt": "2026-09-30T00:00:00+08:00",
  "counts": { "single": 748, "multi": 322, "judge": 170, "fill": 155, "short": 136, "total": 1531 },
  "sources": ["真题", "模拟题"],
  "questions": [ /* Question[] */ ]
}
```

> ⚠️ **这四个字段目前并未写入数据文件**（详见 README 的「已知偏差」一节）。
> 读取方必须对它们做空值容错，不要依赖其存在；`tests/test_questions_data.py`
> 已把这条现状固化成断言，避免有人照本文件去读 `bank["counts"]`。

### Question 对象

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 稳定唯一，格式 `q-0001`（4 位递增，从 1 开始；当前 q-0001…q-1531 连续无空洞） |
| `type` | string | ✅ | 枚举：`single` \| `multi` \| `judge` \| `fill` \| `short` |
| `stem` | string | ✅ | 题干，已去除选项与答案、去首尾空白；判断题不含末尾「（  ）」 |
| `options` | string[] | 条件 | `single`/`multi` 必填，长度 ≥ 2（当前实测 2~4）；**不含** "A." 前缀，是纯选项文本。`judge`/`fill`/`short` 为 `[]` |
| `answer` | string \| string[] \| boolean | ✅ | 见下方「答案规范」 |
| `explanation` | string | ✅ | 解析全文（作答后显示）；当前 1531 / 1531 题非空 |
| `explanationSrc` | string | ✅ | 依据等级：`textbook`（教材原文）\| `web`（权威网页原文）\| `bank`（题库自带/派生说明）\| `manual`（人工校订）\| `template`（未收录直接出处，如实说明） |
| `explanationRef` | string | ✅ | 出处位置（如 `教材《普通高校军事课教程》`）或权威 URL；`bank`/`template` 时可能为空串（当前 421 题为空） |
| `explanationParts` | object | ❌ | 结构化解析：`answer`（正确答案行）/ `reason`（为什么）/ `ref`（依据）/ `note`（提示，如派生说明）；各键都可能缺失 |
| `source` | string | ✅ | `真题` \| `模拟题` \| `提纲` \| `教程`（当前数据只出现前两种） |
| `chapter` | string | ✅ | 章节名；取不到时为 `未分类`。当前为 `第一章中国国防` … `第五章信息化装备` 五章 |
| `section` | string | ✅ | 原卷题型标题，如 `单选题` / `不定项选择题` / `判断题（派生）` / `填空题（由简答区识别）`；取不到时为 `""` |
| `keyConcept` | string | ✅ | 考点短语，答错时在「关键词解析」里显示；未通过质量闸时为空串（当前 12 题为空） |
| `keywords` | string[] | ✅ | 关键词（取源材料里真实存在的术语），前端最多显示 8 个 |
| `distractorWhy` | object | ❌ | `{ 选项字母: 该干扰项为什么不对 }`，只在选择题上出现（当前 1068 题有该键，其中 1012 题非空） |
| `isHard` | boolean | ✅ | 难题标记（当前 584 题为 `true`），App 用于「难题挑战」与题卡「难题」角标 |
| `subsection` | string | ✅ | 第二版考纲的小节 ID；未挂接时为空串（当前 1116 题已挂接） |
| `sectionName` | string | ✅ | 第二版考纲的节 ID；未挂接时为空串 |
| `answerUncertain` | boolean | ❌ | 历史上用于标记「多选答案切分存疑」，仅 `multi` 出现。**当前 19 道保留该字段且全部为 `false`**（为 `true` 的题 0 道），App 的存疑提示不会出现 |
| `webSourceUrl` | string | ❌ | 联网核查时的原始链接（当前 403 题），前端不显示 |
| `relatedSection` | string | ❌ | 语料定位信息（当前 249 题），前端不显示 |
| `lawCitationIssue` | string | ❌ | 法条复核标记（当前 12 题），结论已写进 `explanation`，前端不显示 |
| `lawCitationStatus` | string | ❌ | 同上 |
| `raw` | string | ❌ | 原始文本片段（调试用，**不进打包产物**） |

> 打包时 `tools/bundle.py` 会删掉**前端零读取**的字段：`raw` / `webSourceUrl` / `relatedSection` /
> `lawCitationIssue` / `lawCitationStatus` / `answerUncertain`，以及与 `explanationRef` 逐字重复的
> `explanationParts.ref`。`tests/test_bundle.py` 会校验「该删的删掉了、前端真正读取的字段一个不少」。

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
| `jlx.progress.v1` | `{ [questionId]: { seen, correct, wrong, lastTs, box, fav, wrongFlag } }`；另有特殊键 `__daily` 存按日期的作答记录 `{ "YYYY-MM-DD": { n, ok } }` |
| `jlx.settings.v1` | `{ theme, fontSize, order, shuffleOptions, autoNext, examCount, examMinutes, explainOpen, sound, haptic }` |
| `jlx.exams.v1` | 考试历史 `[{ ts, total, correct, score, durationMs, detail }]`（最多保留 50 条） |
| `jlx.meta.v1` | `{ bankHash, ver, lastExportTs }` |
| `jlx.session.v1` | 未完成练习的会话快照（题号顺序与进度），用于首页「继续上次练习」 |

导出文件格式：`{ app: "军理刷题", ver: 1, exportedAt, progress, settings, exams, daily }`
（`daily` 与 `progress.__daily` 内容相同，顶层再给一份便于外部工具直接读取）。

## 4. 文件布局

```text
junli-quiz/
├─ app/                      前端源码（index.html / app.css / app.js / sw.js / manifest / icons）
├─ data/questions.json       题库与解析
├─ tools/                    构建与质检脚本
│  ├─ pdftext.py             纯标准库的 PDF 文字层提取器
│  ├─ parse_questions.py     文本 → 题库 JSON
│  └─ bundle.py              组装单文件版 + PWA 版 + 一键部署 zip
├─ tests/                    自动化测试（纯标准库 unittest，零第三方依赖）
├─ docs/                     数据格式、参考书目、题目质量说明
├─ build/text/*.txt          4 份资料提取出的纯文本（**不随仓库发布**）
├─ qa/                       质检中间产物与浏览器 E2E 套件（**不随仓库发布**）
└─ dist/                     打包产物（**不随仓库发布**，另见 Releases）
```

本文件描述的字段与枚举由 `tests/test_questions_data.py` 逐题校验（当前 1531 题）：
改数据或改契约时，两边必须同时更新，否则 CI 会失败。
