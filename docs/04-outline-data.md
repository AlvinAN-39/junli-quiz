# 复习提纲数据（`data/outline-2026.json`）

> App 的「复习提纲」页展示的是一份**结构化提纲数据**。出于版权与来源考虑，
> **公开仓库不包含该文件**——你可以自己准备一份放进 `data/`，重新打包后即可使用。
> 本文写清它的结构、三种用法，以及 App 在缺数据时的行为。

## 1. 文件结构

顶层是一个对象，`chapters` 是唯一的必填键：

```json
{
  "source": "资料来源说明（会显示在提纲页上）",
  "basis": "核对依据（可选）",
  "generatedAt": "2026-10-09T12:01:04+08:00",
  "stats": { "chapters": 5, "sections": 21, "subs": 212, "chars": 48823 },
  "chapters": [
    {
      "chapter": "第一章中国国防",
      "chars": 2922,
      "sections": [
        {
          "section": "第一节国防概述",
          "text": "（可选）该节正文；若 subs 非空，App 优先渲染 subs",
          "chars": 2922,
          "subs": [
            { "title": "国防的主体", "text": "该小节的正文内容。" }
          ]
        }
      ]
    }
  ]
}
```

| 字段 | 层级 | 必填 | 说明 |
|------|------|------|------|
| `source` | 顶层 | 否 | 资料来源文字，会显示在提纲页标题下方 |
| `basis` | 顶层 | 否 | 核对依据文字（不显示，供溯源） |
| `generatedAt` | 顶层 | 否 | 生成时间，ISO 8601 |
| `stats` | 顶层 | 否 | `{chapters, sections, subs, chars}` 统计；**缺失时 App 会用实际数组长度兜底**，只影响顶部「N 章 · N 节 · N 小节」的显示 |
| `chapters` | 顶层 | **是** | 章的数组；为空数组时 App 显示「提纲数据未载入」 |
| `chapters[].chapter` | 章 | **是** | 章名（建议与题库的 `chapter` 字段一致，这样能自动定位到你正在学的章） |
| `chapters[].chars` | 章 | 否 | 字数（可用于自查，App 不读） |
| `chapters[].sections[].section` | 节 | **是** | 节名 |
| `chapters[].sections[].text` | 节 | 否 | 该节正文；`subs` 为空时用它 |
| `chapters[].sections[].subs[]` | 小节 | 否 | 小节数组，每项 `{ title, text }`；`title` 为空时只渲染正文 |

> 层级就是 **章 → 节 → 小节** 三层。任意一层都可以只放一条，先跑通再补内容。

## 2. 三种启用方式

### 方式一：自己准备 JSON，放进 `data/` 后重新打包（推荐）

```bash
# 把你的提纲数据放成 data/outline-2026.json
python tools/bundle.py       # 单文件版会把数据内嵌为 window.__OUTLINE__
python tools/verify_app.py   # 体检（31 项）
```

单文件版（`dist/军理刷题.html`）会把提纲数据**内嵌**进去，所以双击打开也能直接看提纲。

### 方式二：只给 PWA 版用（不重新打包）

PWA 版在运行时按相对路径 `data/outline-2026.json` 去取；把这个文件放进部署目录的 `data/` 即可。

> 注意：`tools/bundle.py` 生成的 `dist/web` **不再夹带** `data/`（题库与提纲都已内联进
> `index.html`，那两个文件永远不会被请求，实测占部署 zip 约 45%）。所以「方式二」需要你自己在
> 部署目录里建 `data/` 并放入该文件。
>
> Service Worker 对 `data/outline-2026.json` 是**网络优先**（其余静态资源仍是缓存优先），
> 因此换掉文件后刷新即可看到新提纲，不必重新打包。

### 方式三：从你自己的提纲文本生成

`tools/build_outline_data.py` 就是本项目生成该文件用的脚本，输入是
**从 PDF 提取出的纯文本** `build/text/4-outline-2026.pdf.txt`（`tools/pdftext.py` 可做提取）。
它按「章 → `第X节` → 行首 `㈠`/`⒈` 编号」切分成三层结构。你可以改脚本里的正则来适配自己的资料格式。

## 3. 最小可用示例

仓库里带了一个空壳示例：[`data/outline-2026.example.json`](../data/outline-2026.example.json)。
复制改名为 `outline-2026.json` 后填内容即可：

```bash
cp data/outline-2026.example.json data/outline-2026.json
```

## 4. App 在缺数据时的行为

`data/outline-2026.json` 不存在时，`tools/bundle.py` 会注入 `window.__OUTLINE__ = null`（**不会报错**），
App 的提纲页会显示「提纲数据未载入」并提示自备数据——**其余功能完全不受影响**，题库、练习、错题本照常使用。
