# 军理刷题 · 军事理论课复习 App

[![verify](https://github.com/AlvinAN-39/junli-quiz/actions/workflows/verify.yml/badge.svg)](https://github.com/AlvinAN-39/junli-quiz/actions/workflows/verify.yml)

一个**完全离线**的军事理论课刷题应用：纯静态网页，同一份代码同时服务 **iPhone** 与 **Windows 11**，
零第三方依赖、零外部请求；装到主屏幕后断网也能用。

> ### 下载 & 使用
>
> **Windows 11** —— 从 [Releases](https://github.com/AlvinAN-39/junli-quiz/releases) 下载 **`junli-quiz.html`**，
> 双击即用（Edge / Chrome 均可）。想变成桌面应用：打开后点浏览器右上角 `…` → **应用** → **安装此站点为应用**，
> 之后从开始菜单就能直接启动。
>
> **iPhone** —— 下载 **`junli-quiz-web.zip`**，用 Safari 打开 https://app.netlify.com/drop 上传该 zip，
> 得到网址后在 Safari 里「分享 → **添加到主屏幕**」。首次打开后页面与题库会缓存到本机，之后断网可用。
>
> ⚠️ iOS **无法可靠运行本地 `.html` 文件**（「文件」App 只给只读预览，`file://` 下还禁止网页保存数据，
> 错题本与进度会存不住），所以 iPhone 必须走一个 http/https 网址——这就是"网页版 zip"的用途。
>
> **两台设备互通** —— App 内「设置 → 导入/导出」可导出 JSON，在另一台导入即可同步错题本、收藏与成绩。
>
> **快捷键** —— `1`~`9` 选选项、`Enter` 提交/下一题、`←`/`→` 翻题、`F` 收藏、`S` 搜索、`Esc` 回首页。

## 功能

| 模块 | 说明 |
|------|------|
| 练习 | 顺序 / 随机 / 按章节 / 按题型 |
| 题型 | 单选、多选（不定项）、判断、填空、简答（主观题自评）—— 5 种全覆盖 |
| 答题反馈 | 点选即判（单选/判断）、多选提交后判，立刻显示答案与解析 |
| **解析** | **每题作答后都显示解析**，分行标注「正确答案 / 为什么 / 依据出处」，默认展开（可折叠并记住选择） |
| 错题本 | 答错自动入库；**支持按题干 / 选项 / 解析 / 考点 / 章节搜索过滤**（输入即筛、显示命中数、可按筛选结果重做）；可重做、单题移除、答对自动移出、一键清空 |
| 收藏夹 | 任意题收藏，集中复习 |
| 模拟考试 | 自定义题量与时长、倒计时、答题卡网格跳题、交卷评分、历史成绩 |
| 背题模式 | 直接看题干 + 答案 + 解析，快速过一遍 |
| 复习提纲 | 按 **章 → 节 → 小节** 展示提纲内容与考点结构，可复制 / 导出 Markdown |
| 搜索 | 关键词搜题干 / 选项 / 章节，命中高亮 |
| 统计 | 总正确率、复习进度（已掌握 / 待复习）、按题型与章节的正确率（**按题目去重**）、近 7 天做题量 |
| **答错关键词解析** | 答错时额外显示「考点 + 关键词 + 你选错的那项为什么不对」 |
| **设置** | 独立设置页：**文字大小（4 档，全局生效）**、外观主题（浅色 / 深色 / 跟随系统）、声音与震动（含音量） |
| **音效** | 8 种语义化音效，Web Audio **实时合成**（不含任何音频文件），含 iOS 静音键兼容模式 |
| **震动** | 语义化震动，`navigator.vibrate` —— **Android / Windows 有效，iPhone 无效** |
| 进度保存 | 每答一题即写入本机 `localStorage`，随时关掉不丢；**不上传任何服务器** |
| 版本号 | 首页左上角显示 `vYYYY.MM.DD-HHMM`（打包时刻注入），一眼可见手上是哪一版 |

## 题库

**1531 题**（统计于 2026-10-09）：

| 题型 | 数量 | 来源 |
|------|------|------|
| 单选题 | 748 | 真题集合 + 模拟题集合原卷 |
| 不定项选择题 | 322 | 同上 |
| 判断题 | 170 | 派生题 + 原卷判断题 |
| 填空题 | 155 | 派生题 + 简答区识别 |
| 简答题 / 论述题 | 136 | 原卷参考答案全文 |

- **来源**：作者备考期间整理的 4 份资料（复习提纲 / 教材精要 / 历年真题 / 模拟题集合），
  并以**徐亮、李隽隽、刘捷 主编．《普通高校军事课教程》［M］．广州：中山大学出版社，2023 年 8 月第 1 版．
  ISBN 978-7-306-07893-3** 为章节框架与答案核校依据（App 首页底部有同一张「参考书目」卡片，
  详细说明见 [docs/03-reference.md](docs/03-reference.md)）。
- **每题都有解析并标注依据**：有依据 **1514 / 1531** —— 教材原文 794 · 权威网页 404 · 题库自带说明 309 ·
  人工校订 7；其余如实标注「教材中未收录与该题直接对应的内容」，不硬凑依据。
- **判断题与填空题是派生题**（300 道）：由「题干恰好含一个空格 + 4 个选项」的单选题自动生成，
  解析里注明原题号，方便回溯核对。
- **不确定的地方如实标注**：多选题答案在原卷里被排版成连续字母串，区间切分存在固有歧义——
  这类题在 App 里会显示提示，建议对照原卷核实。

> 质量口径、联网核查的收录规则、派生题机制、历史处置记录 → **[docs/题目质量与依据说明.md](docs/题目质量与依据说明.md)**

## 技术特点

**纯静态、零依赖、零外部请求**：没有前端框架、没有 CDN、没有外部字体或图标（图标是手写内联 SVG）。
`tools/bundle.py` 把 CSS / JS / 题库全部内联进一个 HTML，所以单文件版可以「双击即用」——
`file://` 协议下浏览器会禁用 Service Worker 与 `fetch`，只有全内联才能绕开这个限制。

**离线**：PWA 版注册 Service Worker，首次打开后页面与题库缓存到本机，断网重载仍是完整题库。

**为什么是网页而不是 exe / App**：iPhone 无法安装没有签名的第三方应用，而 Electron / Tauri 只能覆盖 Windows。
纯静态 Web App 是唯一能同时满足「iPhone 能用 + Windows 能用 + 离线 + 双击即用」的形态。

**音效跨平台**：iOS Safari 会连同 Web Audio 一起静音，所以除了 Web Audio 主通道，还加了一条
**常驻的静音音轨**（运行时生成的内联 data URL，约 6 KB，无外部文件），让音频会话停留在「媒体播放」类别，
从而让 Web Audio 也绕过静音键（原理与 [swevans/unmute](https://github.com/swevans/unmute) 同源）。

> **如实说明**：这是「兼容模式」，不是保证——Apple 在持续收紧此类绕过，也没有 iPhone 真机逐一验证过各 iOS 版本；
> 但即使失效也只是「听不到声音」，**不影响任何功能**。
> 震动方面 `navigator.vibrate()` 从未在 iOS 上提供，iPhone 上静默跳过；
> 两项都可在「设置 → 声音与震动」里单独关闭（默认开）。

## 目录结构

```text
junli-quiz/                    ← 公开仓库根目录
├─ app/                        前端源码（index.html / app.css / app.js / sw.js / manifest / icons）
├─ data/questions.json         题库与解析（含依据出处）
├─ tools/                      构建与质检脚本（Python 3.12+，零第三方依赖）
│  ├─ bundle.py                组装单文件版 + PWA 版 + 一键部署 zip
│  ├─ verify_app.py            产物静态体检 + Node 沙箱（缺 Playwright 时自动降级）
│  ├─ parse_questions.py       文本 → 题库 JSON（需要 build/text 语料）
│  └─ …                        其余为题库生成与核查脚本
├─ docs/
│  ├─ 02-data-contract.md      数据契约（已冻结）
│  ├─ 03-reference.md          参考书目与核对依据
│  └─ 题目质量与依据说明.md      题库质量口径、核查规则与历史处置
├─ README.md
├─ LICENSE                     Apache-2.0
└─ NOTICE                      许可证范围与题库版权说明

不包含在仓库中的目录（.gitignore 已排除）：
  dist/    打包产物；运行 `python tools/bundle.py` 生成，成品另见 Releases
  build/   4 份资料提取出的语料，含受版权保护的教材原文，不公开
  qa/      质检中间产物与浏览器 E2E 套件（依赖项目外的 Playwright 环境）
```

## 从源码构建

需要 **Python 3.12+**，**不需要 pip 安装任何东西**（只用标准库）：

```powershell
python tools/bundle.py       # 生成 dist/军理刷题.html、dist/web/、dist/军理刷题-网页版.zip
python tools/verify_app.py   # 产物体检（29 项 + Node 沙箱）
```

> 想重新从 PDF 解析题库（`tools/parse_questions.py`）需要 `build/text/` 语料，
> 该目录含受版权保护的教材原文，**不随仓库发布**。

## 验收与 CI

每次 `push` / PR 会自动跑 `python tools/bundle.py` + `python tools/verify_app.py`
（配置见 [.github/workflows/verify.yml](.github/workflows/verify.yml)），结果就是仓库顶部那个徽章。

**clone 下来就能跑、不需要额外数据的检查**（2026-10-09 实测）：

| 检查 | 命令（在仓库根执行） | 实测结果 |
|------|--------------------|---------|
| 生成产物 | `python tools/bundle.py` | 退出码 0 |
| **产物体检** | `python tools/verify_app.py` | **29/29 通过、0 失败**（缺 Playwright 时浏览器部分降级为 WARN） |
| 解析质量 | `python tools/qa_explanations.py` | 0 问题 |
| 解析质量诊断 | `python tools/diag_explanations.py` | 退出码 0 |
| 存疑盘点 | `python tools/audit_disputed.py` | 3 道待人工确认；**退出码 1 表示「有待处置项」，不是脚本故障** |
| 自洽性复核 | `python tools/audit_selfconsistent.py` | 待处置 0 |
| 依据相关性独立复核 | `python tools/verify_relevance.py` | 退出码 0 |
| 多选答案 / 选项冲突 | `python tools/check_multi_answers.py`、`tools/check_answer_conflicts.py` | 退出码 0 |

> 这些脚本的输出写到 `qa/`、`work/`（均已被 `.gitignore` 忽略），不会污染工作区。
>
> **浏览器 E2E 套件**（Playwright + Chromium，18 个 `.mjs`，覆盖 PWA 离线、iPhone 模拟、音效指纹、
> 选项乱序一致性、二维码可扫性等）依赖与仓库同级的 `qa-env/` 环境（套件与 `node_modules` 必须同处），
> 未随仓库发布；缺少它时 `verify_app.py` 会自动跳过浏览器部分并降级为 Node 沙箱，核心逻辑仍会被验证。

## 已知偏差（待修复）

1. **顶层元数据缺失**：`docs/02-data-contract.md` 要求 `data/questions.json` 顶层含 `schema` / `generatedAt` /
   `counts` / `sources` 四个字段，而实际顶层只有 `questions`。这会让独立质检脚本报出两类 P0
   （顶层字段缺失、`counts` 与实际题量不一致），但**对 App 运行没有影响**：前端不读这四个字段，
   `bundle.py` 也只在日志里打印它们。
2. **题库仍有一处待人工确认**：`tools/audit_disputed.py` 盘点出 3 道题的依据与答案存在出入可能，
   正在逐条核实（该脚本因此返回退出码 1）。
3. **依赖语料的脚本无法开箱运行**：`build/text/`（教材全文）因版权不随仓库发布，因此
   `parse_questions.py`、`gen_explanations.py`、`audit_corpus.py` 等在 clone 后无法直接运行；
   `qa_explanations.py`、`audit_textbook.py` 等在无语料时仍能跑完，但结论范围受限。
4. **公开版不含提纲正文数据**：`data/outline-2026.json`（第三方整理的约 4.9 万字提纲全文）与
   `build/` 同理**不入库**。缺少它时 `tools/bundle.py` 会注入 `null`，App 的「复习提纲」页会提示
   数据缺失——**其余功能完全不受影响**。

## 自己准备提纲数据

公开版不含提纲正文，但**你可以自己准备一份**来启用「复习提纲」页：

- 结构是 **章 → 节 → 小节** 三层，文件名固定为 `data/outline-2026.json`；
- 仓库里带了空壳示例 [`data/outline-2026.example.json`](data/outline-2026.example.json)，
  复制改名为 `outline-2026.json` 后按你的资料填内容即可；
- 放好后跑 `python tools/bundle.py`（单文件版会把数据**内嵌**进去，双击打开也能看提纲）；
  也可以用 `tools/build_outline_data.py` 从你自己的 PDF 提取文本生成该文件。

> 完整的字段说明与三种启用方式 → **[docs/04-outline-data.md](docs/04-outline-data.md)**

## 参与贡献与安全问题

- 想反馈题目、提建议或改代码 → [CONTRIBUTING.md](CONTRIBUTING.md)
- 想报告安全问题（含"本项目不收集任何数据"的说明）→ [SECURITY.md](SECURITY.md)

## 许可证与声明

- **代码**采用 [Apache-2.0](LICENSE)。
- **题库与教材引文不在该许可证授权范围内**，仅供个人学习、非商业用途，详见 [NOTICE](NOTICE)。
- 题库整理自作者备考期间获取的资料，并以《普通高校军事课教程》（中山大学出版社 2023 年 8 月第 1 版）
  为章节框架与答案核校依据。**若权利人认为内容不当，请提 Issue，会立即移除。**
- 数据只存在你自己的浏览器里（`localStorage`），App 不上传任何信息、不发起任何外部请求。
