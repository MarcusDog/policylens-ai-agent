# Live 证据索引

本页保留上一轮 v4 的基础/扩展验收；当前 v5 和第二轮测试见 [08-second-review.md](08-second-review.md)。

本页由 scripts/summarize_results.py 从实际产物生成，不发出模型调用。

pytest：84 项，失败 0，错误 0。

## 基础集：相同模型、问题和资料

模型：MiniMax-M3.1-Flash；Prompt v4；单 Agent 最终复核；默认上限 8 轮 / 10 次工具。

| 指标 | Baseline | Improved |
|---|---:|---:|
| Recall@5 | 1.0000 | 1.0000 |
| 状态正确率 | 1.0000 | 1.0000 |
| 冲突发现率 | 1.0000 | 1.0000 |
| 引用出处有效率 | 1.0000 | 1.0000 |
| 原始事实回归率（旧口径） | 1.0000 | 0.9091 |
| 平均工具调用 | 4.6364 | 4.6364 |
| 平均模型调用（含复核） | 4.7273 | 5.0000 |
| 平均 token 用量 | 15042.1818 | 18323.7273 |
| API 错误率 | 0.0000 | 0.0000 |

原始 Improved 有一项事实检查未通过。逐条查证后确认：草稿提醒已成功读取且引用 D13，
属于原先禁止词断言的误报。条件引文测试仍拒绝无草稿引文的同一回答。原始报告和失败值保留；
以下仅对已有输出按修订注释重评分，新增模型调用为 0，不能当作一次新运行。

| 修订后的案例通过率 | Baseline | Improved |
|---|---:|---:|
| 条件引文义务回归 | 1.0000 | 1.0000 |

[原始运行](../examples/evaluation-live-final.json) · [重评分及规则说明](../examples/grounding-regression-rescore.json)

## 六项必验和资料变更

| 案例 | 实际状态 | 工具 / 模型调用 | Trace |
|---|---|---|---|
| T01 normal | ANSWERED | 4 / 5 | [查看](../examples/evaluation-live-final-traces/live/improved/T01.json) |
| T02 conflict | CONFLICT | 4 / 5 | [查看](../examples/evaluation-live-final-traces/live/improved/T02.json) |
| T03 insufficient | NOT_FOUND | 10 / 7 | [查看](../examples/evaluation-live-final-traces/live/improved/T03.json) |
| T04 paraphrase | ANSWERED | 5 / 6 | [查看](../examples/evaluation-live-final-traces/live/improved/T04.json) |
| T05 history | ANSWERED | 3 / 4 | [查看](../examples/evaluation-live-final-traces/live/improved/T05.json) |
| T06 tool_failure | TOOL_ERROR | 5 / 6 | [查看](../examples/evaluation-live-final-traces/live/improved/T06.json) |
| T07 mutation | ANSWERED | 4 / 5 | [查看](../examples/evaluation-live-final-traces/live/improved/T07.json) |
| T08 removed | ANSWERED | 5 / 5 | [查看](../examples/evaluation-live-final-traces/live/improved/T08.json) |
| T09a supersedes | ANSWERED | 4 / 4 | [查看](../examples/evaluation-live-final-traces/live/improved/T09a.json) |
| T09b scope | NEEDS_CLARIFICATION | 4 / 4 | [查看](../examples/evaluation-live-final-traces/live/improved/T09b.json) |
| T10 injection | ANSWERED | 3 / 4 | [查看](../examples/evaluation-live-final-traces/live/improved/T10.json) |

真实工具名称序列有 9 种，超过要求的两种；每次模型调用有实际 response_id 与用量。

## 扩展集

| 案例 | 状态 | 三项回归检查 |
|---|---|---|
| C01 scope_known | ANSWERED | 通过 |
| C02 scope_history | ANSWERED | 通过 |
| C03 read_failure | TOOL_ERROR | 通过 |
| C04 search_recovery | ANSWERED | 通过 |
| C05 transitive | ANSWERED | 通过 |
| C06 renamed | ANSWERED | 通过 |
| C07 multispan | CONFLICT | 通过 |
| C08 live_limit | LIMIT_REACHED | 通过 |
| C09 stale_history | ANSWERED | 通过 |

[扩展集完整原始结果](../examples/challenge-final-live.json)。包含已知部门、历史部门、读失败、一次搜索失败恢复、
替代链、ID/片段改名和 77 天新值、多片段冲突、真实轮次耗尽、旧历史与当前 45 天资料。

## 竞争文档压力集

6 个针对精确 ID 的候选发现案例：Baseline Recall@5=0.5556，Improved=1.0000。
这是针对机制设计的压力集，不是通用盲测；普通问题集两者仍为 1.0。

## 补充语义审查

实际判定计数：{'SUPPORTED': 9}。
[完整上下文判定](../examples/semantic-audit-complete-context.json)。它是无工具的离线模型检查，不是第二个运行时 Agent，也不是真值。
初次审查因漏传真实文档标题出现误报，旧判定保留为 examples/semantic-audit-final.json；完整元数据版本另存，未覆盖。

## 失败记录与限制

examples/prompt-v1、prompt-v2-pilot、baseline-live、challenge-live、challenge-v3-live、challenge-v4-live
及 evaluation-live.json 等保留了先前输出；包括限流、范围状态、过度拒答和预算挤占，不能用新结果覆盖。
源码和 Prompt 的回归仍不能保证任意问题都正确。模型语义审查不独立；全部资料为合成，小样本非生产准确率。
