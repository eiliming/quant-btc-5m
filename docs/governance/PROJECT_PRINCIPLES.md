# Project Principles

本文档是本项目的最高研究原则。所有数据、Feature、Label、模型、策略和回测设计都必须服从这些原则。

## 项目使命

建立一套能够持续发现市场规律、验证市场规律、迭代交易系统的量化研究体系，而不仅仅训练一个高准确率模型。

本项目关注的是从市场观察到交易结果的完整研究闭环。模型只是表达和检验市场假设的工具，交易结果才是最终验证标准。

## 核心原则

### 1. Understand before Coding

先理解，再编码。

任何实现之前，必须先明确要解决的问题、市场假设、输入输出、验证方式和失败标准。

### 2. Research before Engineering

先完成研究设计，再让 Codex 实现。

Codex 负责把明确的研究设计转化为代码、测试、文档和工程结构，不负责替代研究者做市场判断。

### 3. Close the Loop First

先完成完整闭环，再增加复杂度。

优先建立数据、Label、Feature、模型、策略、回测、复盘的最小可运行流程。复杂数据源、复杂模型和复杂策略必须在闭环存在后逐步引入。

### 4. Every Feature Must Describe A Market Phenomenon

每一个 Feature 必须对应一种市场现象。

如果无法说明某个 Feature 描述了什么市场行为、微观结构或价格状态，则该 Feature 不允许进入项目。

### 5. Model Is Not Strategy

模型只负责概率输出。

模型输出 `p_up` 等概率信号，不直接决定买卖。是否交易、如何交易、交易多少、何时退出，必须由策略层决定。

### 6. Trading Result Is Final Judge

最终评价标准永远是交易结果。

Precision、LogLoss、AUC 等模型指标只能作为中间证据。最终必须检验模型概率是否能稳定转化为正期望交易。

### 7. No Lookahead

严禁未来函数。

任何数据处理、Feature、Label、切分、训练、回测过程都不得使用决策时刻不可获得的信息。

### 8. Every Experiment Must Be Reproducible

每一个实验必须可复现。

实验必须记录数据版本、Feature 版本、Label 版本、模型版本、参数、指标、结论和下一步行动。

### 9. Keep Everything Explainable

任何设计必须能够解释为什么存在。

无法解释研究目的、市场含义、验证方式或交易意义的设计，应当被删除、推迟或重新定义。
