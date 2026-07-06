# Feature Set Design

本文档解释 Feature Set 的设计概念。执行规范与系统约束统一见 `AGENTS.md`。

## Concept

Feature 是市场现象的数字化表达。

Feature Set 是一组 Feature 的结构化集合，用于将研究假设转化为模型可以消费的输入。

## Research Meaning

一个好的 Feature 通常对应某种可解释的市场行为，例如：

- trend
- momentum
- volatility
- volume
- pattern
- regime

这些类别帮助研究者从市场现象出发组织特征，而不是从任意数学变换出发堆叠变量。

## Artifact Role

Feature Set Artifact 连接 Dataset Artifact 与 Experiment Artifact。

它表达了“用什么方式观察市场”，并为后续实验提供稳定输入。
