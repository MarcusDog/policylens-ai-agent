# 第二轮设计审查与 Prompt 对比

2026-11-06。上一轮的真实运行记录保留在 06-live-evidence.md，本页记录随后一次代码审查发现的缺口。
当前完整 pytest 为 **95 项通过**；Ruff 格式与指定静态检查通过。

## 从失败复现开始

先新增反例，再运行原实现，得到 **6 failed**；修复后同一组断言 **6 passed**。
原始记录：[修复前 XML](review-before.xml)、[修复后 XML](review-after.xml)。没有删测试或改成更宽松断言。

| 缺口 | 根因与修复 |
|---|---|
| 字面意义上只有一篇文档时检不到已有词 | Okapi 的负 IDF 下限仍可能为负，再被候选正分门槛过滤。保留 BM25 的词频与长度归一化，采用 Lucene 式正 IDF；Baseline 和 Improved 同时使用 |
| 空知识库被当作坏数据 | 允许有效的空 JSONL；搜索返回空集合，模型可如实 NOT_FOUND。格式错误仍报 DATA_ERROR |
| section 覆盖 scope 等文档元数据 | 拒绝片段中的保留字段，只从文档级获取来源信息 |
| 修改标题/主题后旧读取仍能通过 | 本轮读取证明比较全部关键元数据，另一篇文档的新读取不能“刷新”旧证明 |
| 同一文档两段冲突被拒绝 | CONFLICT 要求至少两条不同原文片段，不再错误限定为两份不同文档 |

正 IDF 为 `log(1 + (N-df+0.5)/(df+0.5))`，参考 [Lucene BM25Similarity](https://lucene.apache.org/core/9_12_1/core/org/apache/lucene/search/similarities/BM25Similarity.html)。
这是小语料边界修复，不是改用另一套模型制造检索增益。

## 运行中断也能留下证据

Trace 在模型请求前、观察返回后、校验和复核后逐步原子写入。
运行中为 RUNNING，记录 in_flight；正常退出为 FINISHED；用户中断为 CANCELLED，CLI 返回 130。
FINISHED 只表示循环退出，是否完成问题仍看 task_state.completed。未完成的 Trace 没有伪造最终答案。

运行记录增加 Python 版本、依赖锁文件哈希和已装载源码指纹。指纹在模块装载时固定，
不会因为运行过程中有人改文件而给旧代码贴上新版本标签。公开记录不包含密钥或模型内部思考。
新回归实际在第二次模型请求前检查磁盘，证明前一条工具观察已经落盘。

## 冻结的新主题案例

新增 8 例租户导出、小时级保留和账号共享案例，数据及注释在首次 v4 运行前冻结，
记录 SHA-256，见 [冻结清单](../data/generalization-freeze.json)。
覆盖单文档、跨文档冲突、未知/已知租户版本、同文档冲突、跨范围 supersedes、空库和未标记注入。

同一 AI 作者构造了资料和注释，这不是独立作者盲测。v5 还利用了 v4 的失败反馈，
因此后续比较应称为冻结回归集的配对比较，不能称为未见测试准确率。

## v4 真正犯的错

G05 只有一份文档，两段分别写 5 小时和 11 小时，片段 ID 为 old/new。
没有任何替代声明，模型却从 ID 名称推断“旧版已被新版替代”，给出确定的 11 小时。
它读取并引用了两段，来源验证通过，事实关键词检查也通过，但状态和替代关系错误。
原始输出：[v4 G05](../examples/generalization-v4-live-traces/live/improved/G05.json)。

v5 明确规定 ID 和段落顺序只负责定位，不能决定优先级；同时将 scope 从部门推广到租户版本、地区、身份等。
提示词还合并了重复规则。最终默认提示为 [v5.txt](../prompts/v5.txt)，没有加入任何案例 ID 或期限答案。

## 同条件真实对比

比较脚本逐例核对同一问题、历史、语料、源码指纹、预算、模型和最终复核设置，
任一不同就拒绝计算。结果：[机器可核对的配对报告](prompt-v4-v5-comparison.json)。

| 指标 | v4 | v5 |
|---|---:|---:|
| 案例通过 | 7/8 | 8/8 |
| 状态正确率 | 87.5% | 100% |
| 冲突发现率 | 50% | 100% |
| 引用出处有效率 | 100% | 100% |
| 平均工具调用 | 4.250 | 3.875 |
| 平均模型调用，含复核 | 4.750 | 4.625 |
| 平均总 token | 13,840.125 | 11,808.125 |
| API 错误率 | 0 | 0 |

这批运行观察到平均 token 减少 **14.68%**。每个版本只运行了一次；模型有随机性，不能据此给出总体提升或显著性结论。
两份原始报告及全部 Trace 均保留：[v4](../examples/generalization-v4-live.json)、[v5](../examples/generalization-v5-live.json)。

补充语义检查对 G05 的判定为 v4 UNSUPPORTED、v5 SUPPORTED，见 [原始审查](../examples/generalization-grounding-audit.json)。
它是同模型的辅助检查，不是独立真值。当前默认 v5 和最终源码还额外真实运行一次 G05，
返回 CONFLICT，明确引用同一文档的两个片段，见 [默认运行 Trace](../examples/current-runtime/live/trace.json)。

## 复现与界限

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts --select E9,F63,F7,F82,F401
.\.venv\Scripts\python.exe scripts/compare_prompts.py
.\.venv\Scripts\python.exe -m src.cli eval --mode live --cases data/generalization_cases.jsonl --methods improved --prompt-file prompts/v5.txt --output runs/generalization-v5.json
```

比较脚本只核对已有记录，不请求模型；最后一条命令才会产生新的真实模型调用。
旧 22 次基础和 9 次扩展记录属于上一轮源码/提示。它们没有被冒充为当前 v5 的新运行。
当前 v5 的新增实证包括本页 8 个回归案例和默认配置实测；更大、独立的新资料评测仍未开展。

## 当前 v5 的原题验收复验

最终源码与默认 v5 另跑了原题六项必验，加上文档替换与删除，**8/8 通过**，没有重评分或改写输出。
原始记录：[current-v5-acceptance-live.json](../examples/current-v5-acceptance-live.json)。

| 案例 | 当前真实结果 |
|---|---|
| 明确答案 | ANSWERED，30 天 |
| 文档冲突 | CONFLICT，引用双方 |
| 资料外问题 | NOT_FOUND |
| 相似改写 | ANSWERED，30 天 |
| 上下文追问 | ANSWERED，重新读取差旅资料 |
| 持续工具失败 | TOOL_ERROR，未虚构流程 |
| 文档替换 | ANSWERED，45 天 |
| 删除竞争文档 | ANSWERED，30 天，无 D02 引用 |

这 8 个案例均使用当前默认 Prompt、8 轮/10 次上限，状态、事实回归、引用期望及澄清检查均通过，API 错误为 0。
单独一次 8 例运行不能推断总体稳定性；其平均调用成本不与不同题目集合直接比较。

## 演示时建议展示的证据

先打开 G05 的 v4/v5 输出：两者都读了原文，但只有 v5 没有凭 ID 编造优先级。
再打开两份 Trace 的 Prompt 哈希、相同源码指纹和工具事件，说明对比控制了什么条件。
随后展示修复前 6 failed 与修复后 6 passed 的 XML，解释哪些错误由程序约束解决、哪些仍由模型判断。
最后展示一次 CANCELLED 单测和当前默认配置 Trace，说明额度、中断与未完成状态怎么保存。
候选人应先亲自运行、阅读并确认这些结论；这段演示顺序不代表已经有人完成了人工复核。
