# 需求与验收矩阵

题目：企业知识问答 Agent；项目：PolicyLens。
只使用合成企业资料。Live 必须由真实模型使用 Function Calling 自主决定下一步。

用户为查询企业制度和产品 FAQ 的员工。目标是找到有出处的适用规则，遇到冲突、条件不明、缺资料和工具失败时明确说明。
范围为本地合成资料、CLI 与可选对话历史；不包含 Web UI、线上部署、真实企业系统接入和多 Agent。
成功标准为六项验收及资料变更行为正确，引用可核验，两条以上真实模型路径可审阅，额度耗尽不虚假成功。

| 编号 | 行为 | 自动化证据 | 运行证据 |
|---|---|---|---|
| T01 | 单一充分来源 | test_conflicts / test_mutation | normal |
| T02 | 同范围无优先级冲突 | test_conflicts | conflict |
| T03 | 资料外问题 | test_agent_loop | insufficient |
| T04 | 相似改写召回 | test_retrieval | paraphrase |
| T05 | 追问重新查证 | test_agent_loop | history |
| T06 | 工具故障 | test_agent_loop | tool_failure |
| T07 | 30 天替换为 45 天 | test_mutation | mutation |
| T08 | 删除竞争文档 | test_mutation | removed |
| T09 | 明确替代关系 / 部门范围 | test_conflicts | supersedes / scope |
| T10 | 文档注入隔离 | test_agent_loop | injection（已保存 Live） |
| T11 | 限额与 API 错误 | test_agent_loop | 单元测试 |
| T12 | 非法 / 未读 / 过期引用 | test_citations | 单元测试 |

Mock 记录仅证明运行时与工具路径真实执行，不证明真实模型推理。
本轮用户已提供 MiniMax 配置，Live 结果见 docs/06-live-evidence.md；不得用 Mock 冒充 Live。
