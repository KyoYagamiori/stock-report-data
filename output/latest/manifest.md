# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-23T13:22:35+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-22

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_b | B | 20260923-0840-early-full-35821059710 | output/archive/2026/09/23/early/20260923-0840-early-full-35821059710.json |
| noon | ready_b | B | 20260923-1135-noon-full-35821059710 | output/archive/2026/09/23/noon/20260923-1135-noon-full-35821059710.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | B | 2026-09-23-early | 2026-09-22 | 2026-09-22T15:00:00+08:00 | output/archive/2026/09/23/early/20260923-0840-early-full-35821059710.json | `cd6430b70c891a9252b8eb3ae34ea5f94fdbfa03c2be6b047c68f5aab351869e` |
| noon | B | 2026-09-23-noon | 2026-09-23 | 2026-09-23T11:30:00+08:00 | output/archive/2026/09/23/noon/20260923-1135-noon-full-35821059710.json | `2dce30c17746f2ed29a24ddbc7d1d7ac56e7e429204f07045492e5dd431f5444` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-20-evening | 2026-09-18 | 暂无 | output/archive/2026/09/20/evening/20260920-2035-evening-full-35453562908.json | `b401bb62c0bcd9b79cc072dcab610210c4ff69124297ec2af48021057d61690e` |
| intraday | A | 2026-09-22-intraday | 2026-09-22 | 2026-09-22T15:35:45+08:00 | output/archive/2026/09/22/intraday/20260922-1005-intraday-light-35700600005.json | `be0d2689193aca475227b92dea376a6c43b94a6adb242b1f1983d90db9300f61` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
