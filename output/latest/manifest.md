# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-08-27T18:37:31+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-08-27

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260827-0840-early-full-33063107262 | output/archive/2026/08/27/early/20260827-0840-early-full-33063107262.json |
| noon | ready_b | B | 20260827-1135-noon-full-33063107262 | output/archive/2026/08/27/noon/20260827-1135-noon-full-33063107262.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-08-27-early | 2026-08-27 | 2026-08-27T15:00:00+08:00 | output/archive/2026/08/27/early/20260827-0840-early-full-33063107262.json | `107aec37874f85ff3aab9059aa1d9a5a9208bf3ecd6e9a31143d80dff059eb7f` |
| noon | B | 2026-08-27-noon | 2026-08-27 | 2026-08-27T11:30:00+08:00 | output/archive/2026/08/27/noon/20260827-1135-noon-full-33063107262.json | `2bafc5b918fa2313aaa4349d393ebb24a41eaba98edaa5e4269ccc7c29a1ab30` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-08-26-evening | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/evening/20260826-2050-evening-full-32975728415.json | `a19935d52c22010f351f1ef892db06a28839bef5f6547684a62a9b2ba99d0236` |
| intraday | A | 2026-08-26-intraday | 2026-08-26 | 2026-08-26T11:30:00+08:00 | output/archive/2026/08/26/intraday/20260826-1035-intraday-light-32926897833.json | `5524b0a5b77d2fdf607f30912be33910d73bf8c05b20970ca1fe61563093938a` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
