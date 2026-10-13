# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-13T14:44:38+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-12

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261013-0523-early-full-38310286106 | output/archive/2026/10/13/early/20261013-0523-early-full-38310286106.json |
| noon | ready_b | B | 20261013-1135-noon-full-local20261013144048-1c76f6b9 | output/archive/2026/10/13/noon/20261013-1135-noon-full-local20261013144048-1c76f6b9.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-13-early | 2026-10-12 | 2026-10-12T16:29:45+08:00 | output/archive/2026/10/13/early/20261013-0523-early-full-38310286106.json | `b2e4eb1d5a80d5b9714782f2ffaaf088cc8379720b0cfe6692834f1099a0a9dd` |
| noon | B | 2026-10-13-noon | 2026-10-13 | 2026-10-13T11:30:00+08:00 | output/archive/2026/10/13/noon/20261013-1135-noon-full-local20261013144048-1c76f6b9.json | `4938083fdbc720b087c00340feaaf3a628a9192c656d0ac5e8b800d9c41043c2` |
| close | A | 2026-10-12-close | 2026-10-12 | 2026-10-12T16:29:45+08:00 | output/archive/2026/10/12/close/20261012-1520-close-full-38281320671.json | `ebc29ae322ae1bdffedb53cd23f7693f1e7aa3215979c67b8d606dd3a40435f7` |
| evening | A | 2026-10-12-evening | 2026-10-12 | 2026-10-12T16:29:45+08:00 | output/archive/2026/10/12/evening/20261012-2017-evening-full-38281320671.json | `87a6023068aa1bf904baa9f830e3c80c067f430b45ff490724f095d720012863` |
| intraday | B | 2026-10-13-intraday | 2026-10-13 | 2026-10-13T14:44:35+08:00 | output/archive/2026/10/13/intraday/20261013-1444-intraday-light-38358401626.json | `16465be6325138310c0e66d88535f3b88457865efcdfd4f4402e808486eb8671` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
