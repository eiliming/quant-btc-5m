# BTCUSDT 5分钟涨跌预测量化项目

本项目采用 Research OS 架构。

所有执行准则、系统约束与治理内容统一收敛于 AGENTS.md。

所有执行规范与系统约束请参见 AGENTS.md。

## 项目介绍

这是一个面向 BTCUSDT 5分钟 K 线预测研究的量化研究系统。

项目目标是基于历史 OHLCV 数据，预测下一根 5分钟 K 线的上涨概率，并为后续策略设计、回测和研究复盘提供结构化基础。

模型层输出概率信号，策略层基于概率、交易成本、风控和持仓设定进行交易决策。

## 系统概览

Research OS 将研究过程组织为一组可追溯的产物：

```text
Dataset Artifact
-> Feature Set Artifact
-> Label Artifact
-> Split Artifact
-> Experiment Artifact
-> Evaluation Result
```

当前已实现：

- raw market data ingestion
- raw data QA
- research dataset build
- artifact metadata
- unified CLI entry

## 目录概览

```text
artifacts/      本地研究产物
src/core/       Artifact、Registry、Pipeline 基础层
src/ingestion/  数据获取
src/validation/ 数据质量检查
src/transformation/ Research dataset 构建
docs/           架构与设计说明
tests/          自动化测试
```

## CLI 使用方法

统一入口：

```bash
python cli.py build-dataset
python cli.py run-qa
python cli.py build-research
```

示例：

```bash
python cli.py build-dataset \
  --exchange binance_spot \
  --symbol BTCUSDT \
  --timeframe 5m \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-02-01T00:00:00Z
```

```bash
python cli.py run-qa
```

```bash
python cli.py build-research \
  --exchange binance_spot \
  --symbol BTCUSDT \
  --timeframe 5m
```

## 开发验证

运行测试：

```bash
pytest -q
```

编译检查：

```bash
python -m compileall -q src cli.py
```

## 文档

- `AGENTS.md`: 唯一执行准则与治理宪法
- `docs/ARCHITECTURE_RESEARCH_OS.md`: Research OS 架构说明
- `docs/DATA_DESIGN.md`: Artifact 存储设计说明
- `docs/data/DATA_CONTRACT.md`: Dataset Artifact 结构说明
- `docs/FEATURE_PRINCIPLES.md`: Feature Set 概念说明
- `docs/LABEL_DESIGN.md`: Label 概念说明
