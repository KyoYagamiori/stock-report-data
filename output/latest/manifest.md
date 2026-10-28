# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-28T14:17:09+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-27

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261028-0213-early-full-40557870390 | output/archive/2026/10/28/early/20261028-0213-early-full-40557870390.json |
| noon | ready_b | B | 20261028-1135-noon-full-40638777428 | output/archive/2026/10/28/noon/20261028-1135-noon-full-40638777428.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-28-early | 2026-10-27 | 2026-10-27T15:36:00+08:00 | output/archive/2026/10/28/early/20261028-0213-early-full-40557870390.json | `4ec2de455d8250485162d3b1bd23ebedb8f55b002312595f59a18a36f23066a8` |
| noon | B | 2026-10-28-noon | 2026-10-28 | 2026-10-28T11:30:00+08:00 | output/archive/2026/10/28/noon/20261028-1135-noon-full-40638777428.json | `e9fc612d64885bab57a5b685e7ede1539d14cbc208724da262e854309952353c` |
| close | A | 2026-10-27-close | 2026-10-27 | 2026-10-27T15:36:00+08:00 | output/archive/2026/10/27/close/20261027-1753-close-full-40484226723.json | `f639ab61dc2cb02a6ecf66a336229ce03a692058586adaa84336b236b770dbdf` |
| evening | A | 2026-10-27-evening | 2026-10-27 | 2026-10-27T15:36:00+08:00 | output/archive/2026/10/27/evening/20261027-2121-evening-full-40511278022.json | `4608315f4b2cb1dbf3454830b81ab97298f7651d4806340d1dce81649cbf1b7b` |
| intraday | B | 2026-10-28-intraday | 2026-10-28 | 2026-10-28T14:17:06+08:00 | output/archive/2026/10/28/intraday/20261028-1417-intraday-light-40642861818.json | `ab7bf1814f27c69b7fa0ff004673be5e7cb7291370c5e5e3cc9d97f530a3ae01` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
