# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-08-27T23:13:17+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-08-27

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260827-0855-early-full-33064461231 | output/archive/2026/08/27/early/20260827-0855-early-full-33064461231.json |
| noon | ready_b | B | 20260827-1205-noon-full-33086008157 | output/archive/2026/08/27/noon/20260827-1205-noon-full-33086008157.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-08-27-early | 2026-08-27 | 2026-08-27T15:00:00+08:00 | output/archive/2026/08/27/early/20260827-0855-early-full-33064461231.json | `0eaaf0695dc5ebb5ea4eb56fc0da23599bf9f760f874b4d6c51fec1dbd332eae` |
| noon | B | 2026-08-27-noon | 2026-08-27 | 2026-08-27T11:30:00+08:00 | output/archive/2026/08/27/noon/20260827-1205-noon-full-33086008157.json | `65890bb571f97f6c3adbfa546ccbb4994d7d7d3e0c8eec22057f866562007968` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-08-26-evening | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/evening/20260826-2050-evening-full-32975728415.json | `a19935d52c22010f351f1ef892db06a28839bef5f6547684a62a9b2ba99d0236` |
| intraday | A | 2026-08-26-intraday | 2026-08-26 | 2026-08-26T11:30:00+08:00 | output/archive/2026/08/26/intraday/20260826-1035-intraday-light-32926897833.json | `5524b0a5b77d2fdf607f30912be33910d73bf8c05b20970ca1fe61563093938a` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
