# 数据契约 v1（冻结）— 题库 JSON 与前端 API

> 本文件是 T3（解析）、T4（App）、T5（质检）之间**唯一**的接口约定。任何一方不得单方面修改字段名/类型。
> 如需变更，先改本文件并通知 Lead。

## 1. `data/questions.json`

顶层对象（**不是**数组）：

```json
{
  "schema": 1,
  "generatedAt": "2026-09-30T00:00:00+08:00",
  "counts": { "single": 200, "multi": 30, "judge": 40, "fill": 20, "short": 10, "total": 300 },
  "sources": ["真题", "模拟题", "提纲", "教程"],
  "questions": [ /* Question[] */ ]
}
```

### Question 对象

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 稳定唯一，格式 `q-0001`（4 位递增，从 1 开始） |
| `type` | string | ✅ | 枚举：`single` \| `multi` \| `judge` \| `fill` \| `short` |
| `stem` | string | ✅ | 题干，已去除选项与答案，去首尾空白；判断题不含末尾「（  ）」 |
| `options` | string[] | 条件 | `single`/`multi` 必填，长度 ≥ 2；**不含** "A." 前缀，纯选项文本。`judge`/`fill`/`short` 为 `[]` |
| `answer` | string \| string[] \| boolean | ✅ | 见下方「答案规范」 |
| `explanation` | string | ✅ | 解析；**已验证 1171/1171 非空**（作答后显示） |
| `explanationSrc` | string | ✅ | 依据等级：`textbook`（教材原文）\| `manual`（人工校订）\| `bank`（题库自带/派生说明）\| `template`（未收录直接出处，如实说明） |
| `explanationRef` | string | ✅ | 出处位置，如 `教材《普通高校军事课教程》·中国国防`；`bank`/`template` 时为空串 |
| `source` | string | ✅ | `真题` \| `模拟题` \| `提纲` \| `教程` |
| `chapter` | string | ✅ | 章节名；取不到时 `未分类` |
| `section` | string | ✅ | 原卷题型标题（如 `一、单选题`）；取不到时 `""` |
| `answerUncertain` | boolean | ❌ | **仅 `multi` 会出现且为 `true`**：源 PDF 把多选答案压成连续字母串，切分存在固有歧义，答案集合需人工复核 |
| `raw` | string | ❌ | 原始文本片段（调试用，**不进 dist**） |

### 答案规范（**必须严格遵守**）

- `single`：**大写单字母字符串**，如 `"A"`。必须是 `options` 的合法下标字母。
- `multi`：**排序后的大写字母数组**，如 `["A","C","D"]`（升序、无重复）。
- `judge`：**布尔值** `true`（对/正确/√/T）或 `false`（错/错误/×/F）。
- `fill`：**字符串数组**，按空格顺序每个空一个元素，如 `["南昌","1927"]`；无法拆分时长度为 1 的数组。
- `short`：**字符串**，参考答案要点全文（可含换行）。
- 解析不出来的题 → **不要输出**该题（宁缺毋滥），并在解析脚本 stdout 计数。

## 2. 前端消费 API（T4 使用）

App 只依赖 `window.__QUESTION_BANK__`（单文件版由构建脚本注入；开发时从 `data/questions.json` fetch）：

```js
const bank = window.__QUESTION_BANK__;      // 等价于上面 questions.json 的内容
bank.questions.forEach(q => { ... });
```

前端**必须**做防御性归一化：`answer` 可能是 string/array/boolean，统一转成内部表示：

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

## 3. localStorage 键名（App 专用，勿与其他项目冲突）

| 键 | 内容 |
|----|------|
| `jlx.progress.v1` | `{ [questionId]: { seen, correct, wrong, lastTs, box, fav, wrongFlag } }` |
| `jlx.settings.v1` | `{ theme, fontSize, order, shuffleOptions, autoNext, examCount, examMinutes }` |
| `jlx.exams.v1` | 考试历史 `[{ ts, total, correct, score, durationMs, detail }]` |
| `jlx.meta.v1` | `{ bankHash, ver, lastExportTs }` |

导出文件格式：`{ app:"军理刷题", ver:1, exportedAt, progress, settings, exams }`。

## 4. 文件布局（T6 组装目标）

```
军理刷题/
├─ app/                      # 前端源码（T4）
│  ├─ index.html
│  ├─ app.css
│  ├─ app.js
│  ├─ manifest.webmanifest
│  ├─ sw.js
│  └─ icons/icon.svg
├─ data/questions.json       # T3
├─ build/text/*.txt          # T2
├─ tools/pdftext.py          # T2
├─ tools/parse_questions.py  # T3
├─ tools/bundle.py           # T6 单文件打包
├─ qa/                       # T5
└─ dist/
   ├─ 军理刷题.html           # ★ 单文件离线版（内含题库，真·双击即用）
   ├─ index.html             # ★ PWA 版（引用 data/questions.json）
   └─ ...
```
