# 实际评测

当前评测日：2026-11-06（Asia/Shanghai）。本页保留初次离线交付阶段的结果与失败历史。
**Live 已验证**；上一轮 84 项测试、基础/扩展真实运行、评分修订及语义检查见 [证据索引](06-live-evidence.md)。
当前 95 项测试及 v4/v5 的冻结回归对比见 [第二轮审查](08-second-review.md)。

## 命令与记录

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/test-results.xml
.\.venv\Scripts\python.exe -m src.cli eval --retrieval-only --output docs/retrieval-evaluation.json
.\.venv\Scripts\python.exe -m src.cli eval --mode mock --output examples/evaluation-mock.json --examples-dir examples
```

初次交付最后一次已执行 pytest：**72 passed**。
16 个外部化案例，每种检索器各执行一次；Mock 运行时验收全部符合预期。
原始数据：[pytest XML](test-results.xml)、[检索结果](retrieval-evaluation.json)、
[Mock 完整评测](../examples/evaluation-mock.json)。

## 指标

| 指标 | Baseline | Improved | 解读 |
|---|---:|---:|---|
| Recall@5 | 1.0000 | 1.0000 | 15 个非空相关集合的文档召回宏平均 |
| 状态正确率 | 1.0000 | 1.0000 | 16 次 Mock 状态与预期相符 |
| 冲突发现率 | 1.0000 | 1.0000 | 当前只有一个标注冲突案例 |
| 引用有效率 | 1.0000 | 1.0000 | 通过当前来源校验的引用 / 所有输出引用 |
| 无依据回答率（代理） | 0.0000 | 0.0000 | 按状态与 fixture 事实检查判定 / 所有运行 |
| 事实回归通过率 | 1.0000 | 1.0000 | 必含/禁止事实字符串代理 |
| 平均工具调用 | 2.0625 | 2.0625 | 来自实际计数 |

平均运行时间保留在 JSON 中。这是 Mock 本机耗时，不是 LLM 延迟，不能用于比较模型速度。
Recall@5 = 每题 |相关 ID ∩ top5 命中 ID| / |相关 ID| 的平均。
状态准确率 = 状态等于期望的运行数 / 总数；冲突发现率仅以期望 CONFLICT 为分母。
引用有效率不把无引用回答当作满分；没有引用时指标为 null。
无依据代理将期望资料不足/冲突/澄清/故障却给出 ANSWERED，或事实检查失败的确定回答计入。
它不检测所有潜在无依据语句，不能作为完整语义安全度量。

当前数据集小、措辞集中，两种方法都能召回标注文档，**未观察到 Recall@5 提升**。
Improved 的可验证作用是 top_k 截断时仍发现同主题候选，测试覆盖精确 ID、主题扩展和候选未读门禁。
没有人为降低 Baseline 或改写指标来制造优势。

## 六项验收与变更

| 验收 | 离线实录 | 初次交付时的 Live 状态 |
|---|---|---|
| 明确答案 | normal：30 天，D01 | 待配置 |
| 文档冲突 | conflict：CONFLICT，引用 D01/D02 | 待配置 |
| 资料外 | insufficient：NOT_FOUND，无引用 | 待配置 |
| 相似改写 | paraphrase：30 天 | 待配置 |
| 上下文追问 | history：差旅申请、发票等，重新读 D05 | 待配置 |
| 工具失败 | tool_failure：真实注入搜索错误后 TOOL_ERROR | 待配置 |
| 文档替换 | mutation：45 天，新的精确引用 | 待配置 |
| 删除冲突文档 | removed：30 天，无 D02 | 待配置 |
| 明确替代 | supersedes：15 天 | 待配置 |
| 部门范围 | scope：请求所属部门 | 待配置 |
| 注入 | 只验证 tool 通道隔离；未声称模型抵抗通过 | 待配置 |

test_mutation 还在同一 Agent / Corpus 对象上修改磁盘并再次运行，避免“重新手动切换答案”假象。
运行实际读取新文件并重建索引；已读但随后修改/删除的引用不能通过验证。

## 实际失败与修复

1. 虚拟环境：默认 python 是 LibreOffice 解释器，创建 venv 时 Permission denied。
   改用 py -3.11，虚拟环境与依赖安装成功。未修改全局 Python。
2. 首轮 pytest：59 passed / 1 failed。口语“公司配的电脑丢了”与设备规范缺乏共享词。
   在合成文档中明确定义设备包含公司配发电脑，保留原测试；复验 60 passed。
   这是资料覆盖改善，不是证明 n-gram 能理解同义词。
3. 首次完整评测：两者状态准确率 0.9375；Improved 事实回归率 0.9375。
   完整资料外问题因“公司”误命中；字符拼接在“申请单、交通”处造出“单交”，
   对改写问题产生错误排名。原始失败结果保留为 [evaluation-first-mock.json](evaluation-first-mock.json)。
   加入通用停用词、保留字符边界，新增两个回归测试和全量离线矩阵；复验 62 passed，16 案例全部通过。
   首次评测的无依据代理尚未将“期望 NOT_FOUND 却 ANSWERED”计入；修正了该统计口径，未修改原始失败文件。
4. 交付审查补充“本轮观察后新增竞争文档”的语料哈希门禁，以及 CLI JSON/文件、退出状态、
   历史参数、异常输出和非法类型测试。静态检查发现一处未使用的测试 import，已移除；
   Ruff 格式化与指定静态检查通过，最终复验 72 passed。

## Live 执行约束

`python scripts/verify_live.py --env-file <absolute-path>` 不会降级 Mock。
执行 data/live_cases.jsonl 中 11 个案例 × 两个检索器，保存真实执行结果，并计算 Improved 的不同工具路径数量。
至少两条成功的真实工具路径才满足路径验收；不能以 SDK mock 或离线脚本代替。
模型路径允许不同，评测按状态、事实代理、引用期望和实际来源校验判断。
完整语义支持、冲突解释和注入抵抗仍需要逐条人工复核。
