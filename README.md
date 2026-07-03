# BTCUSDT 5分钟涨跌预测量化项目

## 信条

Every feature must describe a market phenomenon. Every model improvement must be validated by trading results.

每一个特征都必须描述一种市场现象；每一次模型提升，都必须最终通过交易结果验证。

## 项目目标

本项目目标是使用 BTCUSDT 5分钟 K 线历史 OHLCV 数据，预测下一根 5分钟 K 线的上涨/下跌概率，并最终接入交易策略和回测系统。

模型层只输出概率，不直接交易。策略层根据概率阈值、交易成本、风控规则和持仓规则决定是否开仓、平仓或保持空仓。

## 研究哲学（Research Philosophy）

本项目不是为了训练一个准确率最高的模型。

本项目的目标是：

建立一套能够不断提出市场假设、
验证市场假设、
构建 Feature、
训练模型、
分析模型、
优化策略、
最终形成稳定盈利交易系统的完整研发流程。

模型只是研究市场规律的工具。

交易收益才是最终目标。

## 项目原则（Project Principles）

1. 永远先理解，再编码。
2. 永远先完成闭环，再增加复杂度。
3. 每增加一个 Feature，必须能够描述一种市场现象。
4. 每一个实验必须可复现。
5. 模型不能作弊（禁止 Lookahead）。
6. 回测必须符合真实交易。
7. 所有设计都应该服务于最终交易收益。

## 项目角色

### Researcher（我）

负责：

市场理解

Feature设计

实验设计

模型分析

交易策略

最终决策

### AI Mentor（ChatGPT）

负责：

引导学习

Review方案

提出质疑

监督规范

帮助分析结果

不直接替代思考

### Coding Assistant（Codex）

负责：

实现明确需求

编写代码

重构代码

生成测试

维护工程

不负责研究方向

## 研发流程（Research Workflow）

提出市场假设

↓

定义Label

↓

设计Feature

↓

生成Dataset

↓

训练Baseline

↓

分析错误案例

↓

提出新的市场假设

↓

继续迭代

## 项目路线

1. 数据获取
2. 数据清洗
3. EDA
4. Label 设计
5. Feature 设计
6. 模型训练
7. 模型分析
8. 策略设计
9. 回测

## （研发治理）Research Governance

本项目遵循 `docs/governance/` 中定义的研究规范。

任何新增 Feature、实验、模型、策略，都应遵循治理规范。研究决策必须先被清晰描述和 Review，再进入实现阶段。

核心治理文档包括：

1. `docs/governance/PROJECT_PRINCIPLES.md`
2. `docs/governance/RESEARCH_WORKFLOW.md`
3. `docs/governance/FEATURE_STANDARD.md`
4. `docs/governance/EXPERIMENT_STANDARD.md`
5. `docs/governance/REVIEW_CHECKLIST.md`
6. `docs/governance/RESEARCH_JOURNAL_TEMPLATE.md`

## V1 原则

先完成闭环，再增加复杂度。

V1 只使用 BTCUSDT 5分钟 OHLCV 数据，优先建立从数据、标签、特征、模型、策略到回测的可验证流程。不要在早期引入过多外部数据源、复杂特征或复杂交易规则。
