# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-15T13:41:46+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-14

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260915-0855-early-full-34933378138 | output/archive/2026/09/15/early/20260915-0855-early-full-34933378138.json |
| noon | ready_b | B | 20260915-1135-noon-full-34932042216 | output/archive/2026/09/15/noon/20260915-1135-noon-full-34932042216.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-15-early | 2026-09-14 | 2026-09-14T15:00:00+08:00 | output/archive/2026/09/15/early/20260915-0855-early-full-34933378138.json | `49427a50662818bf8497513b70f2539c1b3276df1cef4a2241bdd30d4e785c0a` |
| noon | B | 2026-09-15-noon | 2026-09-15 | 2026-09-15T11:30:00+08:00 | output/archive/2026/09/15/noon/20260915-1135-noon-full-34932042216.json | `a87a78fef6a1a12226532953815691a0ab0ba160b4569ec00f560450b67a883d` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-12-evening | 2026-09-11 | 暂无 | output/archive/2026/09/12/evening/20260912-2050-evening-full-34623942689.json | `0694fc7ab2d62b5009b2a494416a03e7787e51fd8687f09937dfadaca038b83a` |
| intraday | A | 2026-09-14-intraday | 2026-09-14 | 2026-09-14T15:35:45+08:00 | output/archive/2026/09/14/intraday/20260914-1005-intraday-light-34819715536.json | `8b9e50a3bf8b6bcbd633835319c06b5f60bbf08a74418e5633fcab6e7eaf3a02` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
