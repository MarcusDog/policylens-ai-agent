# 小影校招 AI Agent 开发笔试提交说明

- 所选题目／题目标识：企业知识问答 Agent。
- 项目：PolicyLens — Evidence-Grounded Enterprise Knowledge Agent。
- GitHub：https://github.com/MarcusDog/policylens-ai-agent
- 提交版本：`submission-v1` 标签；最终 commit SHA 以交付消息及 `git rev-parse HEAD` 的实际值为准。
- 本人实际投入：**3 小时**，候选人于 2026-11-08 确认。
- 本人贡献：确定题目、开发顺序与模型选择，对项目描述的全部功能进行了亲自验证和结果核对。
- AI 使用：Codex 辅助实现、合成数据、测试、提示词和文档；未将这些代码说成本人独立手写。

## 评审入口

| 内容 | 文件 |
|---|---|
| 安装、运行、边界 | [README](README.md) |
| 用户、目标、范围和成功标准 | [需求](docs/01-requirements.md) |
| 动态模型循环与工具职责 | [方案](docs/02-solution.md) |
| 当前 v5 原题验收，8/8 | [实际报告](examples/current-v5-acceptance-live.json) |
| 当前 v5 新主题回归，8/8 | [实际报告](examples/generalization-v5-live.json) |
| Prompt 对比与失败 | [第二轮审查](docs/08-second-review.md) |
| 提交前检查与本轮测试 | [检查报告](docs/09-submission-review.md) |
| AI 辅助与个人贡献 | [AI 使用记录](docs/04-ai-usage.md) |
| 难点、学习与下一步 | [复盘](docs/05-retrospective.md) |

## 快速复现

Python 3.11+，在仓库根目录：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.cli ask --mode mock --question "报销期限是多少？"
```

macOS/Linux 用 `python3` 创建环境，后续使用 `.venv/bin/python`。
Live 需自行配置 `.env`，密钥不随仓库交付：

```powershell
.\.venv\Scripts\python.exe -m src.cli ask --mode live --question "报销期限是多少？" --save-trace runs/reviewer-live.json
```

Mock 只验证流程，不证明模型决策。已有 Live 实录来自 MiniMax-M3.1-Flash。
普通问题集和针对机制的压力集分别报告，模型语义审查不是独立真值，不将小样本通过率当作生产准确率。

## 三组最短审阅入口

- 正常：[输入](examples/current-v5/normal/live/input.json)、[输出](examples/current-v5/normal/live/output.json)、[Trace](examples/current-v5/normal/live/trace.json)。
- 资料不足：[输入](examples/current-v5/insufficient/live/input.json)、[输出](examples/current-v5/insufficient/live/output.json)、[Trace](examples/current-v5/insufficient/live/trace.json)。
- 工具失败：[输入](examples/current-v5/tool_failure/live/input.json)、[输出](examples/current-v5/tool_failure/live/output.json)、[Trace](examples/current-v5/tool_failure/live/trace.json)。

冲突、改写、上下文追问、替换和删除也在 `examples/current-v5/`，工具参数、目的、结果、后续动作和实现指纹均保留。
