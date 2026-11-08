# PolicyLens

Evidence-Grounded Enterprise Knowledge Agent · 小影科技 AI Agent 开发笔试 · 题目：企业知识问答 Agent。

通过真实 Function Calling 自主检索企业制度、读取原文，并输出可核验引用、冲突、资料缺口和任务状态。
Python CLI，无 Agent 框架、数据库或 Web UI。

**提交入口：[SUBMISSION.md](SUBMISSION.md)**。题目标识：企业知识问答 Agent；本人投入 **3 小时**（2026-11-08 确认）。
公开仓库：https://github.com/MarcusDog/policylens-ai-agent 。最终提交 SHA 见交付消息。

**已接入 MiniMax-M3.1-Flash，并完成真实模型验收。** 基础集两种检索器各 11 次真实运行，
扩展集 9 次真实运行，以及完整两轮对话均已保存。当前 **95 项 pytest 通过**，16 个离线案例通过。
原始评分曾有一项过宽禁止词误报，按条件引文回归重新评分，原始结果和修订说明均保留。
完整数字、失败记录和边界见 [Live 证据索引](docs/06-live-evidence.md)，设计取舍见 [答辩说明](docs/07-design-review.md)。
**最新默认 Prompt 为 v5。** 第二轮审查补了单文档/空库检索、来源元数据隔离、同文档冲突与中断留痕，
另有相同 8 个新主题案例的 v4/v5 配对实测：7/8 → 8/8，平均 token 减少 14.68%。
这是利用失败反馈优化后的冻结回归比较，不是独立盲测准确率；详见 [第二轮报告](docs/08-second-review.md)。
当前默认 v5 还重新实测了六项必验、文档替换和删除，**8/8 通过**，无需沿用旧 v4 作为通过证据。

## 安装

Python 3.11+。本机默认 `python` 是 LibreOffice 内置解释器，请使用 `py -3.11` 创建虚拟环境。

```powershell
cd D:\求职\小影科技\ai-agent\policylens
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pytest -q
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pytest -q
```

以下命令中的 `python` 指激活虚拟环境后的解释器；Windows 也可直接使用 `.\.venv\Scripts\python.exe`。
requirements.txt 表达兼容范围，requirements-lock.txt 保存本次实际安装版本。

## 立即运行（无需 API）

```bash
python -m src.cli ask --mode mock --question "报销提交期限是多久？" --data-dir data/scenarios/normal --save-trace runs/mock/normal.json --output runs/mock/normal-output.json
python -m src.cli ask --mode mock --question "报销提交期限是多久？" --data-dir data/scenarios/conflict
python -m src.cli ask --mode mock --question "火星基地宠物托管补贴是多少？" --data-dir data/scenarios/normal
python -m src.cli ask --mode mock --question "VPN怎么申请？" --fail-tool search_docs --fail-count 100
python -m src.cli ask --mode mock --question "那差旅报销呢？" --history-file data/example_history.json --data-dir data/scenarios/normal
```

`--json` 打印机器可读输出。未指定 Trace 时自动保存到 `runs/<mode>/latest-trace.json`；保留多次记录请指定不同路径。
`--max-model-steps` 默认 8，`--max-tool-calls` 默认 10。
`--save-history <path>` 保存实际问答，可作为下一轮的 `--history-file`，历史引用仍须本轮重读。
模型请求阶段 Ctrl-C 会保留观察并标记 CANCELLED，CLI 返回 130；强制结束可能留下 RUNNING/in_flight 的未完成记录。
退出码：0 为已回答/已报告冲突或资料缺口；1 为工具/API故障、限额或评测未通过；2 为配置/输入错误。

## 模型配置与 Live

复制 `.env.example` 为被 Git 忽略的 `.env`，设置：

```dotenv
OPENAI_API_KEY=<local-secret>
OPENAI_BASE_URL=https://api.minimax.cn/v1
MODEL_NAME=MiniMax-M3.1-Flash
MODEL_TIMEOUT_SECONDS=45
MODEL_PROVIDER=minimax
MODEL_REASONING_EFFORT=low
MODEL_JSON_MODE=off
MODEL_MIN_INTERVAL_SECONDS=2
```

使用支持 Chat Completions、Function Calling 和 `tool_choice=auto` 的模型/兼容网关。
JSON 模式按网关能力配置；MiniMax 用 Prompt 约束输出 JSON。设置禁用并行调用，但运行时仍防御性处理多调用回复。
模型名不硬编码。环境变量优先于配置文件；`--env-file` 支持外部绝对路径，不会复制或显示密钥。

```bash
python -m src.cli ask --mode live --env-file /absolute/path/model.env --question "报销期限是多久？" --save-trace runs/live/conflict.json
python scripts/verify_live.py --env-file /absolute/path/model.env
```

Windows 路径示例：`--env-file "D:\私有配置\model.env"`。
完整 Live 验收会对两种检索器分别运行 11 个案例，产生真实 API 费用，默认每次 API 超时 45 秒，不做 SDK 隐式重试。
工具失败后的重试由模型决定。服务商若不支持上述协议，会返回明确错误，不会降级为 Mock。

Live 入口检查六项必验、替换/删除、替代关系、部门范围和文档注入，并汇总真实工具序列，要求至少两条不同路径。
基础 Live 的六项必验已覆盖；替换、删除、明确替代、部门范围及注入均有真实记录。
扩展数据和模型判断仍不能代表生产准确率，补充语义检查也不是独立真值。

## 动态 ReAct 与可靠性边界

`Agent.run(question, history)` 把问题和历史发给模型。模型可以选择任意工具、换关键词、继续核查、澄清或直接输出最终 JSON。
每个工具结果以真实 `tool` 消息回传，下一步重新调用模型；运行时没有预设 Live 工具序列。
`parallel_tool_calls=False`，仍能防御处理模型在一个回复中返回多个调用。
Live 对带企业结论的候选答案在同一 Agent 对话内增加一次最终复核，计入模型上限。
它能保留、修改答案或继续查证；NOT_FOUND/TOOL_ERROR 不额外复核，避免故障退出耗尽预算。
`--no-final-review` 可做消融；`--prompt-file prompts/v1.txt` 可复现旧提示。
v5 将适用范围从部门推广到租户版本、地区和身份，并禁止从片段 ID 的 old/new 字样推断替代关系。

正式引用必须满足：文档/片段存在、版本正确、quote 为精确子串、本轮成功读取、读取内容与当前磁盘一致。
已经发现但未读取的同主题候选会阻止确定回答。错误会反馈模型，额度用尽返回 `LIMIT_REACHED`，不会代写正确引用。
来源读取证明同时绑定标题、主题、范围、版本及原文；片段不能覆盖文档级元数据。
同一文档的不同片段也可形成 CONFLICT，不能将“两个冲突证据”误限定成“两份文档”。
小语料还要求查完已知候选的全部片段，防止只读简介就掩盖另一段冲突；长文档可能因此耗尽额度。
历史只接受 user/assistant 角色，历史引用不能直接复用。文档与工具内容当作不可信数据处理。

**Mock 是确定性协议测试替身**：固定检索、读取首个主题的候选、用有限合成模式构造结果。
其规则只在 `MockModel` 中，用于检查工具、循环、故障和输出结构。`ScriptedModel` 用于精确单元测试。
Mock 不具备通用语义理解、灵活部门推断或模型自主决策能力，不应部署为知识助手。

## 数据与冲突

`data/documents.jsonl` 含 14 份纯合成制度/FAQ，覆盖报销、差旅、请假、VPN、权限、账号、设备和支持。
每份包含 doc_id、title、version_date、topic、scope、supersedes、sections；每节含 span_id、text。

| 场景目录 | 资料变化 | 预期 |
|---|---|---|
| normal | 只有 D01 期限来源 | ANSWERED：30 天 |
| conflict | D01=30，D02=15，无优先级 | CONFLICT，引用两份，询问财务 |
| mutation | D01 原文改为 45 天 | ANSWERED：45 天 |
| removed | 移除 D02 | ANSWERED：30 天，无 D02 引用 |
| supersedes | D02 明确替代 D01，同范围 | ANSWERED：15 天 |
| scope | 分别适用研发部/销售部 | NEEDS_CLARIFICATION |
| injection | VPN 文档含恶意指令 | 已实测读取附录后按制度回答，未输出攻击标记 |

日期新、分数高、主题相同都不能单独决定制度优先级或是否冲突。最终语义判断属于模型。
Corpus 每次工具操作检查磁盘内容哈希，变更时重新载入；索引随之刷新。更换资料无需修改 Agent 代码。
`scripts/build_data.py` 可重建合成数据，会覆盖合成 fixture，请先保存自己的资料修改。

## 检索与工具协议

Baseline：jieba + BM25。Improved：BM25 + 字符 2/3-gram + RRF（k=60）+ 同主题候选扩展。
两者均使用 Lucene 式正 IDF，修复单文档语料的负分过滤；空语料可正常返回无结果。
精确 ID / 完整标题优先；默认 top_k=5，最多 8。通用停用词、字符重叠门槛与标点边界降低无关召回。
同主题扩展优先保留竞争文档；即使 top_k 截断，同主题元数据仍列出待核查候选。

| 工具 | 参数 | 返回 |
|---|---|---|
| search_docs | query, top_k, purpose | doc_id、标题、版本、主题、范围、片段预览、排名和同主题元数据 |
| read_doc_span | doc_id, span_id, purpose | 精确原文、版本、范围、替代关系、语料哈希 |

统一结果为 `{"ok":true,"data":...}` 或 `{"ok":false,"error":{"code":...,"message":...,"retryable":...}}`。
purpose 只记录行动目的，不索取内部思维链。支持 `--fail-tool search_docs/read_doc_span --fail-count N` 注入连续故障。

## 输出

六种 status：ANSWERED、CONFLICT、NEEDS_CLARIFICATION、NOT_FOUND、TOOL_ERROR、LIMIT_REACHED。
顶层包含 answer、citations、missing_information、clarification_question、task_state。
citation 含 doc_id、version_date、span_id、quote；task_state 的真实调用计数由运行时写入。
completed 只有 ANSWERED / NOT_FOUND 为 true（表示本轮信息查询结束），需要用户介入或未完成时为 false。
不输出伪置信度。

## 测试与评测

```bash
python -m pytest -q --junitxml=docs/test-results.xml
python -m src.cli eval --retrieval-only --output docs/retrieval-evaluation.json
python -m src.cli eval --mode mock --output examples/evaluation-mock.json --examples-dir examples
python -m src.cli eval --mode live --cases data/live_cases.jsonl --output runs/evaluation-live.json
python -m src.cli eval --mode live --cases data/challenge_cases.jsonl --methods improved --output runs/challenge-live.json
python -m src.cli eval --retrieval-only --cases data/retrieval_stress_cases.jsonl --output runs/stress.json
python scripts/audit_grounding.py --report examples/evaluation-live-final.json --method improved --output runs/semantic-audit.json
python scripts/summarize_results.py
python scripts/compare_prompts.py
python -m src.cli eval --mode live --cases data/generalization_cases.jsonl --methods improved --prompt-file prompts/v5.txt --output runs/generalization-v5.json
```

Baseline 与 Improved 使用相同问题和语料；Recall@5 按文档 ID 计算，排除无相关文档的案例。
当前两者 Recall@5 均为 1.0；Mock 状态、冲突和引用来源校验指标均为 1.0，平均工具调用均为 2.0625。
这些指标来自实际运行，**Mock 状态正确率不代表 LLM 能力**。
无依据回答率是状态/fixture 事实检查代理，引用有效率只衡量来源；二者都不是完整语义蕴涵评测。
详细公式、失败记录、原始数据见 [评测报告](docs/03-evaluation.md)。
Live 基础集两者状态正确率、冲突发现率和引用出处有效率均为 1.0，平均工具调用均为 4.6364。
条件引文回归重评分两者均为 1.0，原始 Improved 旧口径为 10/11，差异和原文件均保留。
9 个扩展 Live 案例全部符合预期；6 个精确 ID 竞争文档压力例 Recall@5 为 0.5556 / 1.0。
压力集是特定机制测试，不能与普通问题集混算或宣称普遍提升。
补充语义审查对 Improved 的 9 个带企业结论输出均判为 SUPPORTED；这属于同模型的辅助检查，不是独立真值。
完整真实两轮对话见 `examples/conversation/live/`，第二轮历史由第一轮实际输出生成。

六项必验同时保留 Mock 和 Live 记录（`examples/<场景>/live/`）：

| 项目 | 实际 Mock 结果 | 证据目录 |
|---|---|---|
| 明确答案 | ANSWERED，30 天 | examples/normal/mock |
| 文档冲突 | CONFLICT，30 / 15 天 | examples/conflict/mock |
| 资料外问题 | NOT_FOUND | examples/insufficient/mock |
| 相似改写 | ANSWERED，30 天 | examples/paraphrase/mock |
| 上下文追问 | ANSWERED，差旅凭证 | examples/history/mock |
| 工具失败 | TOOL_ERROR | examples/tool_failure/mock |

每个目录保存 input.json、output.json、trace.json。真实执行的 Mock 路径分别包括
`search_docs → read_doc_span → final`、`search_docs → read_doc_span → read_doc_span → final`、
`search_docs → final`；这些不是 Live 路径。
Trace 含 run_id、UTC 时间、mode、模型标识、问题、历史摘要、实际工具参数/结果/耗时、校验结果及最终状态。
新增 Prompt 哈希、语料哈希、真实 response_id、返回模型名、token 用量和最终复核事件。
新增已装载源码与依赖指纹、RUNNING/FINISHED/CANCELLED 及 in_flight 状态，便于核对中断和实现版本。
UTC 时间展示时应按所在时区换算。没有记录模型隐藏推理或 API Key。

## 目录

```text
src/          agent.py model.py tools.py retriever.py evidence.py trace.py cli.py evaluation.py
data/         documents.jsonl test_cases.jsonl live_cases.jsonl scenarios/
tests/        retrieval / loop / citations / conflicts / mutation / evaluation
examples/     各场景实际输入、输出、Mock Trace 与评测 JSON
docs/         需求、方案、评测、AI 使用、复盘及原始测试报告
scripts/      数据重建、Live 验收、重评分、补充语义检查、报告生成
prompts/      v1—v5 真实提示版本及可复用的 Codex 维护提示
```

## 已知限制与提交信息

- Live 路径已验证，历史失败完整保留；更多真实措辞、长文档及非合成资料的泛化仍未充分验证。
- 旧基础/扩展实录对应上一轮 v4；当前 v5 有 8 个冻结回归案例、8 个原题验收案例及默认配置实测，没有把旧运行改标成 v5。
- 程序能验证来源与候选核查，不能证明回答的全部语义受原文支持；有独立事实回归检查，仍需人工审查。
- 字符检索不是语义向量；泛化同义词、长文档、跨主题隐式冲突、部门包含关系未充分评测。
- 语料在一次执行中频繁变化时可能耗尽核查额度；当前设计为小规模单机合成语料。
- GitHub Actions 覆盖 Windows/Linux、Python 3.11/3.12；实际远端状态见 Actions，发布检查见 [提交前审查](docs/09-submission-review.md)。
- 实际投入 3 小时；本人已验证全部描述功能（2026-11-08 确认）。实现、数据、测试与文档由 Codex 辅助，未宣称本人独立手写。
- AI 使用声明：代码、测试、数据、文档由 Codex 协助编写；详见 [真实工作记录](docs/04-ai-usage.md)。
- 最终 commit SHA：运行 `git rev-parse HEAD` 获取，具体 SHA 在交付消息中提供；避免将 commit 自身的哈希嵌入同一提交造成自引用。

Function Calling 协议参考 [OpenAI 官方文档](https://developers.openai.com/api/docs/guides/function-calling)。
MiniMax 兼容细节参考 [服务商官方文档](https://platform.minimax.cn/docs/api-reference/text-openai-api)。
