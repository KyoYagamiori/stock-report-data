# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-16T17:36:51+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-16

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260916-0840-early-full-35058450713 | output/archive/2026/09/16/early/20260916-0840-early-full-35058450713.json |
| noon | ready_b | B | 20260916-1225-noon-full-35079023262 | output/archive/2026/09/16/noon/20260916-1225-noon-full-35079023262.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-16-early | 2026-09-15 | 2026-09-15T15:00:00+08:00 | output/archive/2026/09/16/early/20260916-0840-early-full-35058450713.json | `16936aee7eac963de9e995b6e12e5e3be7ec9d52466a52c116599559e7291287` |
| noon | B | 2026-09-16-noon | 2026-09-16 | 2026-09-16T11:30:00+08:00 | output/archive/2026/09/16/noon/20260916-1225-noon-full-35079023262.json | `5fd6c260e2bf4b1ddae4c6a543b86d663c8a3d4bb6f27e5ab9d9cf26da29ab1c` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-12-evening | 2026-09-11 | 暂无 | output/archive/2026/09/12/evening/20260912-2050-evening-full-34623942689.json | `0694fc7ab2d62b5009b2a494416a03e7787e51fd8687f09937dfadaca038b83a` |
| intraday | A | 2026-09-16-intraday | 2026-09-16 | 2026-09-16T15:35:45+08:00 | output/archive/2026/09/16/intraday/20260916-1005-intraday-light-35069343260.json | `226c5c7b7a87a702b27f4cacd08ff691499fa9298af0cd9d21c109187e3193e7` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
