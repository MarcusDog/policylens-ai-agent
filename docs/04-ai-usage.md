# AI Coding 使用记录

## 1. 原始任务与拆解

用户提供完整笔试执行要求和开发地址。按 M0—M5 拆解为数据与检索、工具协议、
真实模型循环、证据校验、离线测试、Live 验收与交付文档。未使用多 Agent。

## 2. 提供给 Codex 的上下文

原始需求全文、Windows 工作目录、Python 3.12.12、空开发目录。
初始环境中 OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME 均未设置。
用户明确要求先完整开发，模型配置稍后提供。

## 3. 生成与修改

由 Codex 编写本项目代码、合成数据、pytest、CLI、评测脚本与文档。
技术边界：轻量 Python；模型自主动作；确定性引用和竞争资料核查；
Mock 仅为可重复的协议测试替身。具体执行与修复记录在后续追加。

## 4. 实际测试

实际执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/build_data.py
.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/test-results.xml
.\.venv\Scripts\python.exe -m src.cli eval --mode mock --output examples/evaluation-mock.json --examples-dir examples
.\.venv\Scripts\python.exe -m src.cli eval --retrieval-only --output docs/retrieval-evaluation.json
uvx ruff format src tests scripts
uvx ruff check src tests scripts --select E9,F63,F7,F82,F401
.\.venv\Scripts\python.exe scripts/verify_live.py
```

最终 pytest 72 passed；Ruff 静态检查通过。
16 个案例在 Baseline / Improved 下均符合预期；Recall@5 两者均为 1.0。
CLI 额外真实执行明确答案并保存 runs/mock/cli-smoke.json 与输出。
Live 预检查已执行，因缺配置明确返回 NOT_VERIFIED，未发出真实 API 请求。
examples/live-summary.json 保存未验证状态；没有任何真实模型成功记录。

## 5—7. 观察、修复与复验

实际问题与修复：

- 默认解释器是 LibreOffice 自带 Python，venv 报 Permission denied；改用系统 py -3.11。
- 首轮测试 59 passed / 1 failed：设备资料未定义电脑；补充合成资料定义，原断言保留，复验 60 passed。
- 首次完整 Mock 评测发现泛词“公司”误召回，以及跨标点 n-gram 造成改写排名退化。
  保存原始 JSON 后修正停用词和字符边界，添加回归案例，复验 62 passed。
- 审查补充同轮变更、异常与 CLI 端到端验证，最终 72 passed。
- 来源正确但答案错误：单测构造 30 天引文搭配 90 天回答，证实来源校验无法单独证明语义；
  独立 fixture 事实检查可检测此例。没有声称它等价完整语义蕴涵评估。
- 完整失败数据和指标口径见 docs/03-evaluation.md 与 docs/evaluation-first-mock.json。

代码、测试、合成数据、示例和文档均在项目内生成；当前提交哈希由 git 实测后交付。

## 8. 本人真实技术决策

用户确认题目、开发路径、先开发后配置的顺序。
候选人本人其他手工贡献和实际投入时间：待本人确认。
代码中的实现取舍由 AI 提出并实现，不冒充候选人手工成果。

## 9. 使用范围与限制

AI 参与代码、测试、合成资料和文档。真实语义正确性仍需 Live 验收与人工抽查；
字符串引用校验不等于完整语义蕴涵判断。不记录内部思维链或真实密钥。
