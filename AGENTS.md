# AGENTS.md

本文档是本项目唯一的系统执行规范，也就是 Research OS 的治理宪法。

所有执行规则、系统约束、研究治理、Feature / Label / Experiment 准入标准，均以本文档为准。

## 1. 系统定位（System Identity）

本项目是：

> 🧠 研究型量化操作系统（Research OS）

核心目标：

- 所有研究必须可复现
- 所有数据必须可追溯
- 所有结果必须结构化沉淀

本系统不是为了训练一个单次表现最好的模型，而是为了持续提出市场假设、验证市场假设、沉淀研究证据，并最终形成可回测、可复盘、可迭代的量化研究闭环。

## 2. 核心执行原则（必须遵守）

### 原则1：一切皆为 Artifact

所有输出必须是可保存、可追踪、可引用的研究产物，包括：

- 数据集
- 特征集
- 标签集
- 切分结果
- 模型
- 实验结果
- QA 报告
- 回测结果

任何不能被保存、追踪、引用和复现的输出，都不能作为正式研究结果。

### 原则2：不可修改性（Immutable）

任何结果：

- ❌ 不能覆盖
- ❌ 不能修改
- ✔ 只能生成新版本

已有 Artifact 一旦生成，就代表一次历史事实。修正、重跑、参数变化、代码变化都必须生成新的 Artifact。

### 原则3：可追溯性（Traceability）

任何实验必须能回答：

- 用了哪个数据集
- 用了哪套特征
- 用了哪个标签
- 用了哪种数据切分
- 用了什么模型参数
- 用了哪段代码
- 由哪个 builder 或 runner 生成
- 得到了哪些指标和结论

实验必须记录数据版本、Feature 版本、Label 版本、模型版本、参数、指标、观察结论和下一步行动。

### 原则4：配置驱动执行（Config-driven）

所有实验必须通过配置文件执行：

- ❌ 禁止写死参数
- ❌ 禁止 notebook 手动训练
- ✔ 必须通过 experiment config

配置 + 代码 + 输入 Artifact 必须能够完全复现实验结果。

### 原则5：先理解，再编码

任何实现之前，必须先明确：

- 要解决的问题
- 市场假设
- 输入和输出
- 验证方式
- 失败标准
- 结果如何复盘

Codex 负责把明确的研究设计转化为代码、测试、文档和工程结构，不替代研究者做市场判断。

### 原则6：先闭环，再复杂

优先建立数据、Label、Feature、模型、策略、回测、复盘的最小可运行流程。

复杂数据源、复杂模型和复杂策略只能在闭环存在后逐步引入。

### 原则7：模型不是策略

模型只负责输出概率信号，例如 `p_up`。

是否交易、如何交易、交易多少、何时退出，必须由策略层决定。

### 原则8：交易结果是最终裁判

Precision、LogLoss、AUC 等模型指标只能作为中间证据。

最终必须检验模型概率是否能稳定转化为正期望交易。

### 原则9：禁止未来函数

任何数据处理、Feature、Label、切分、训练、回测过程都不得使用决策时刻不可获得的信息。

### 原则10：设计必须可解释

任何设计必须能够解释为什么存在。

无法解释研究目的、市场含义、验证方式或交易意义的设计，应当删除、推迟或重新定义。

## 3. Pipeline 流程规范（强约束）

标准流程如下：

```text
数据集 → 特征生成 → 标签生成 → 数据切分 → 实验执行 → 评估结果
```

每一步必须独立，禁止混合职责。

职责边界：

- Dataset Builder 只负责生成数据集 Artifact
- FeatureBuilder 只负责生成特征集 Artifact
- LabelBuilder 只负责生成标签 Artifact
- Split Builder 只负责生成数据切分 Artifact
- ExperimentRunner 只负责消费 Artifact 并执行实验
- Evaluation 只负责评估和记录结果

禁止在实验阶段临时构造数据集、临时计算特征、临时生成标签或绕过切分。

## 4. Artifact 规范（非常重要）

每个 Artifact 必须包含：

- `artifact_id`
- `artifact_type`
- 输入 Artifact 引用（`inputs`）
- 生成方式（`provenance`）
- 配置（`config`）
- 时间戳（`created_at`）
- 统计信息（`stats`）

标准磁盘结构：

```text
artifact_root/
  data.parquet
  metadata.json
```

`metadata.json` 标准结构：

```json
{
  "artifact_id": "...",
  "artifact_type": "...",
  "created_at": "...",
  "inputs": [
    {
      "artifact_id": "...",
      "artifact_type": "..."
    }
  ],
  "provenance": {
    "builder": "...",
    "version": "...",
    "git_commit": "..."
  },
  "config": {},
  "stats": {}
}
```

`artifact_id` 标准结构：

```text
{artifact_type}_{artifact_identity}_{run_id}
```

- `artifact_identity`：由 artifact type、输入 Artifact 引用和核心配置计算得到，必须可复现。
- `run_id`：单次执行 ID，必须唯一，用于支持同一身份的重复运行。

强制规则：

- 所有结果必须落盘
- 所有结果必须版本化
- 所有 Artifact 必须包含 `metadata.json`
- `inputs` 必须是 Artifact 引用列表，禁止使用字符串路径或非结构化 dict 作为正式依赖
- 禁止覆盖已有 Artifact
- 禁止使用 `latest` / `final` / `temp` / `tmp` 文件名表达正式结果

标准依赖模型：

```text
artifact -> inputs -> upstream artifacts
```

Registry 是 Artifact System of Record，必须支持依赖索引、上游查询、下游查询、lineage tracing 和 impact analysis。

## 5. 特征生成规范（Feature Rules）

特征必须满足：

- 只能使用当前及历史数据
- 不能使用未来信息（禁止数据泄漏）
- 必须通过 FeatureBuilder 生成
- 禁止在 notebook 或训练代码中临时计算特征
- 每个 Feature 必须描述一种明确的市场现象

Feature 不是数学变换的堆叠，而是对某种市场现象的结构化表达。

每个 Feature 必须能回答：

- Feature ID 是什么
- Feature Name 是什么
- 描述了什么 Market Phenomenon
- 背后的 Research Hypothesis 是什么
- Calculation Method 是什么
- Expected Effect 是什么
- Potential Risks 是什么
- Version 是什么
- Status 是什么

Feature Review 必须确认：

- 是否描述明确市场现象
- 是否只使用当前和过去数据
- 是否存在未来函数风险
- 是否与已有 Feature 重复
- 是否有清晰实验目的
- 是否能在失败后被解释和复盘

## 6. 标签生成规范（Label Rules）

标签必须满足：

- 只能通过 LabelBuilder 生成
- 表示未来信息（未来收益 / 未来方向）
- 不允许在特征阶段生成标签
- 不允许在实验阶段临时生成标签

Label 的作用是定义研究问题的监督信号。Label 可以包含未来信息，但这些未来信息只能进入标签 Artifact，不能泄漏到 Feature、Split、Experiment 输入特征或回测决策中。

## 7. 实验执行规范（Experiment Rules）

实验必须：

- 完全依赖配置文件
- 通过 ExperimentRunner 执行
- 不允许在代码中手动训练模型
- 不允许绕过 pipeline
- 不允许从 ad hoc dataframe 直接训练
- 不允许在实验中计算 Feature 或 Label

实验 Artifact 必须记录：

- Experiment ID
- Objective
- 输入 Artifact ID
- Dataset Version
- Feature Version
- Label Version
- Split Version
- Model Version
- Parameters
- Random Seed
- Metrics
- Observations
- Conclusion
- Next Action

一次 Experiment 是一次完整的假设验证，而不是一次随手训练。

## 8. 禁止行为清单（必须严格遵守）

以下行为一律禁止：

- 在 notebook 中直接训练模型
- 使用 pandas 手写特征逻辑并绕过 FeatureBuilder
- 覆盖已有 Artifact
- 跳过 QA 或数据校验
- 绕过 Feature / Label Builder
- 绕过 ExperimentRunner
- 使用 `latest` / `final` / `tmp` / `temp` 命名正式结果
- 使用随机打乱时间序列的 Train/Test 切分
- 在 Feature 中使用未来信息
- 在实验代码中临时生成标签
- 将模型输出直接等同于交易决策

## 9. 可复现性要求

任何实验必须满足：

> 配置 + 代码 + 输入数据 = 可完全复现结果

否则视为无效实验。

最低复现信息包括：

- 输入 Artifact ID
- experiment config
- builder / runner 名称
- builder / runner 版本
- git commit
- random seed
- 输出 Artifact ID
- 指标与结论

## 10. Review 与研究日志规范

Review 不能只看指标是否提高。

每次 Review 必须回答：

- 这个结果是否可信
- 这个结果是否可复现
- 这个结果是否有市场解释
- 这个结果是否能转化为交易收益
- 下一步应该继续、修改、废弃，还是进入回测

研究日志不是开发日志。

每个阶段结束后，研究日志必须记录：

- Objective
- Key Decisions
- Why
- Alternatives Considered
- What Worked
- What Failed
- Lessons Learned
- Next Step

研究日志关注研究判断和证据，不是简单记录改了哪些代码文件。

## 11. 回测与策略规范

回测必须严格按照时间顺序。

回测必须考虑：

- 手续费
- 滑点
- 持仓规则
- 止盈止损
- 市场状态稳定性

策略层根据模型概率、交易成本、风控规则和持仓规则决定是否开仓、平仓或保持空仓。

交易结果必须作为最终验证标准。

## 12. 系统身份声明

本系统不是：

- ❌ 交易机器人
- ❌ 简单机器学习项目
- ❌ notebook 实验集合
- ❌ 临时脚本集合

而是：

> 🧠 研究型量化操作系统（Research OS）

从现在开始：

> 系统规则不再分散，而是统一由 AGENTS.md 作为唯一执行宪法进行管理。
