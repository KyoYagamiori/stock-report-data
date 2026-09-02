# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-02T17:17:10+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-02

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260902-0855-early-full-33594021660 | output/archive/2026/09/02/early/20260902-0855-early-full-33594021660.json |
| noon | ready_b | B | 20260902-1225-noon-full-33610980520 | output/archive/2026/09/02/noon/20260902-1225-noon-full-33610980520.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-02-early | 2026-09-01 | 2026-09-01T15:00:00+08:00 | output/archive/2026/09/02/early/20260902-0855-early-full-33594021660.json | `9fa288437f0476fd20bba8e994969b49af19af2e2c99c29f3e9e8248d77b9f5d` |
| noon | B | 2026-09-02-noon | 2026-09-02 | 2026-09-02T11:30:00+08:00 | output/archive/2026/09/02/noon/20260902-1225-noon-full-33610980520.json | `2988bc93b46892a8f04857aad24f973a122bb68a237b4bfb1fbdeb9ee4badc79` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-08-30-evening | 2026-08-28 | 暂无 | output/archive/2026/08/30/evening/20260830-2035-evening-full-33264053821.json | `2784a42124a1b7b4e78d2193064ec21804003c214cb00efc558e96275eb622ac` |
| intraday | A | 2026-09-02-intraday | 2026-09-02 | 2026-09-02T15:00:04+08:00 | output/archive/2026/09/02/intraday/20260902-1005-intraday-light-33601639418.json | `9a7dba4c0af55df7ddc9a8ddf056d93a341387de2d01f4f8034fc671e47552f0` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
