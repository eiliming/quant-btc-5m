# Experiment Standard

本文档定义实验管理规范。目标是保证每个实验都可追踪、可复现、可比较。

## 核心要求

每个实验必须有明确目标、版本记录、参数记录、指标记录、观察结论和下一步行动。

禁止创建不可追踪的实验文件，例如：

```text
test.py
test2.py
final.py
```

这类命名无法表达实验目的、版本、输入、输出和结论，不允许作为正式实验资产进入项目。

## 实验编号

建议以后 `experiments/` 使用连续编号：

```text
EXP001
EXP002
EXP003
...
```

每个实验编号必须唯一，并在实验记录中引用。

## 实验必备字段

每个实验必须具有以下字段：

1. Experiment ID
2. Date
3. Objective
4. Dataset Version
5. Feature Version
6. Model Version
7. Parameters
8. Metrics
9. Observations
10. Conclusion
11. Next Action

## 字段说明

### Experiment ID

唯一实验编号，例如 `EXP001`。

### Date

实验日期。建议使用 `YYYY-MM-DD`。

### Objective

实验目标。必须说明本次实验要验证什么问题。

### Dataset Version

数据集版本，包括原始数据范围、清洗版本、Label 版本和样本过滤规则。

### Feature Version

Feature 集版本，必须能追踪到具体 Feature 文档和计算定义。

### Model Version

模型版本，包括模型类型、代码版本和训练流程版本。

### Parameters

关键参数，包括模型参数、阈值、训练区间、验证区间、随机种子和数据切分规则。

### Metrics

实验指标，包括模型指标和必要时的交易指标。

模型指标可以包括 Precision、LogLoss、AUC。

交易指标可以包括 Return、Sharpe、MaxDrawdown、WinRate、Profit Factor。

### Observations

实验观察，包括模型表现、概率分布、错误样本、重要 Feature、不同市场状态下的差异。

### Conclusion

实验结论。必须说明假设被支持、被否定，还是证据不足。

### Next Action

下一步行动。必须明确继续、修改、废弃或进入策略验证。

## 可复现要求

实验必须能够通过记录的信息重新运行，并得到可比较的结果。

最少需要记录：

1. 数据版本
2. Feature 版本
3. Label 版本
4. 代码版本
5. 参数
6. 时间切分
7. 指标
8. 结论
