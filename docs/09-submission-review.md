# 提交前检查

审查日期：2026-11-08（候选人客户端日期）。范围为当前源码、测试、实际运行记录、提交规范及公开交付内容。
未发现阻塞原题验收的代码问题；此结论限于本次审查与合成资料，不保证任意输入的语义正确性。

| 规范 | 证据／处理 |
|---|---|
| 单题、可运行 | 企业知识问答 Agent；Python 原生 CLI，无额外 Agent 框架 |
| 可复制运行 | README、SUBMISSION.md 及依赖锁文件 |
| 模型动态决策 | Function Calling / auto，实际工具观察回传后再次调用模型 |
| 至少两条真实路径 | 当前 v5 的 8 例存在 6 种实际工具序列，非预设日志 |
| 上限与未完成 | 8 轮／10 次工具；单测及 G08 Live 均留有 LIMIT_REACHED |
| 三组实际记录 | 当前 normal、insufficient、tool_failure 均有输入、输出、Trace |
| 全部验收点 | 当前六项必验与替换、删除 8/8；另有新主题回归 8/8 |
| 测试结果在 examples | [pytest XML](../examples/submission/test-results.xml)、[检查日志](../examples/submission/check-results.txt) |
| AI 与本人贡献 | 本人确认投入 3 小时并验证全部描述功能；实现辅助范围保留 |
| 密钥与业务隐私 | 合成资料；忽略 `.env`；当前密钥全历史扫描通过，发布前再扫描暂存内容 |
| GitHub 可读性 | 用户选择公开仓库，发布后核对匿名访问与远端 commit |

本轮复验为 95 项测试通过，格式与指定静态检查通过，pip check 无依赖冲突。
还从待发布的 Git 索引导出干净副本，不复制 `.env`、虚拟环境或缓存，再次得到 95 项测试通过。
证据：[干净导出日志](../examples/submission/clean-checkout-results.txt)、[JUnit XML](../examples/submission/clean-checkout-tests.xml)。
本轮仅补交付入口、检查证据与说明，不改 Agent 行为，也不把旧运行伪装成新模型运行。

## 保留的边界

- 引用核验不等于完整语义蕴涵检查；模型辅助审查也不是真值。
- v5 的配对集利用了 v4 失败反馈，属于冻结回归集，不称独立盲测。
- 没有线上服务、真实企业资料或生产可用性承诺。
- 强制终止可能留下 RUNNING/in_flight；模型请求阶段正常 Ctrl-C 有 CANCELLED 记录。
- GitHub Actions 跨平台状态发布后实际核对，不预先声明通过。

题目标识按候选人给出的“企业知识问答 Agent”填写；原材料没有数字编号，不自行推测。
