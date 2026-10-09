# 参与贡献

感谢你愿意花时间。这个项目很小，规则也简单。

## 报告问题

请到 [Issues](https://github.com/AlvinAN-39/junli-quiz/issues) 提交，尽量附上：

- **题库问题**：题号（`q-xxxx`，App 里每题都能看到）、你认为的正确答案、以及**依据出处**
  （教材名与页码、或权威网页链接）。带依据的反馈我会逐条核对。
- **功能问题**：你用的设备（iPhone / Windows）、浏览器、复现步骤、期望结果与实际结果。
- **界面问题**：截图最有帮助。

> 本项目**不收集任何使用数据**，我也看不到你设备上的任何内容，所以描述得越具体越好。

## 先了解一下题库的口径

提交题库修正前，建议先读 [docs/题目质量与依据说明.md](docs/题目质量与依据说明.md)，其中说明了：

- 每道题的解析都要有依据（教材原文 / 权威网页 / 题库自带说明 / 人工校订）；
- 多选题答案来自原卷被排版压缩的字母串，切分存在**固有歧义**——这类题会如实说明，而不是硬凑一个答案；
- 找不到任何权威来源的题，会明确写「教材中未收录与该题直接对应的内容」。**不接受编造的"依据"。**

## 修改代码或题库

1. Fork 本仓库，从 `main` 拉一个分支；
2. 改完后在仓库根跑自查（只需 Python 3.12+，**零第三方依赖**）：

   ```bash
   python tools/bundle.py       # 生成产物（单文件版 + PWA 版 + 部署 zip）
   python tools/verify_app.py   # 29 项静态体检 + Node 沙箱

   python -m unittest discover -s tests -t . -v   # 回归套件（纯标准库、不联网、不需要 dist/）
   ```

   期望输出：`合计 29 项：通过 29，失败 0，警告 0`，以及 unittest 的 `OK`。
   CI（[.github/workflows/verify.yml](.github/workflows/verify.yml)）会在这两组检查上自动跑，
   Ubuntu（Python 3.12 / 3.13 / 3.14）与 Windows（Python 3.12）都有覆盖。

3. 如果改动了 `data/questions.json`，请另外跑：

   ```bash
   python tools/qa_explanations.py        # 解析质量：期望 0 问题
   python tools/audit_selfconsistent.py   # 自洽性：期望"待处置 0"
   python tools/verify_relevance.py       # 依据相关性独立复核：期望退出码 0
   ```

4. 提 Pull Request 时说明**改了什么、依据是什么**。

> 有几类脚本依赖 `build/text/` 语料（教材全文，因版权不随仓库发布），clone 后无法运行：
> `parse_questions.py`、`gen_explanations.py`、`audit_corpus.py` 等；`audit_disputed.py` 返回退出码 1
> 表示"有待人工确认的题"，不是脚本故障。README 的「已知偏差」一节列了完整清单。

## 请不要做的事

- 不要提交 `build/`、`dist/`、`qa/`、`work/` 里的内容（`.gitignore` 已排除）；
- 不要在题库里加入**没有出处**的答案或解析；
- 不要把教材正文或试卷原文整段抄进仓库。
