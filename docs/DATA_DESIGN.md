# 数据设计

## 存储格式

原始数据优先保存为 CSV，方便 Python 和 TypeScript 共同使用。

后续特征数据可以保存为 Parquet，以提升读取效率、压缩率和类型表达能力。

## V1 数据范围

V1 只使用 OHLCV。

暂不引入订单簿、资金费率、持仓量、链上数据。

详细 Data Contract 见：

`docs/data/DATA_CONTRACT.md`

## 数据质量检查

必须检查以下问题：

1. 缺失 K 线
2. 重复 K 线
3. 时间间隔异常
4. OHLC 逻辑错误
5. 成交量异常
