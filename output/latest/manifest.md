# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-14T17:50:43+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-14

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260914-0855-early-full-34810131620 | output/archive/2026/09/14/early/20260914-0855-early-full-34810131620.json |
| noon | ready_b | B | 20260914-1205-noon-full-34829651521 | output/archive/2026/09/14/noon/20260914-1205-noon-full-34829651521.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-14-early | 2026-09-11 | 2026-09-11T15:00:00+08:00 | output/archive/2026/09/14/early/20260914-0855-early-full-34810131620.json | `34cd1278ffdda8838ea027482db2160682beab2fc0698154570a00e3a1dec1c2` |
| noon | B | 2026-09-14-noon | 2026-09-14 | 2026-09-14T11:30:00+08:00 | output/archive/2026/09/14/noon/20260914-1205-noon-full-34829651521.json | `27c3fcd9efb9bd4df5f90f54825851de742df5223844870296a7ea057f5dfb90` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-12-evening | 2026-09-11 | 暂无 | output/archive/2026/09/12/evening/20260912-2050-evening-full-34623942689.json | `0694fc7ab2d62b5009b2a494416a03e7787e51fd8687f09937dfadaca038b83a` |
| intraday | A | 2026-09-14-intraday | 2026-09-14 | 2026-09-14T15:35:45+08:00 | output/archive/2026/09/14/intraday/20260914-1005-intraday-light-34819715536.json | `8b9e50a3bf8b6bcbd633835319c06b5f60bbf08a74418e5633fcab6e7eaf3a02` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
