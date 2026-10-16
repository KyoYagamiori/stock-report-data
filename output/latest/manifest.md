# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-16T16:58:38+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-16

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261016-0118-early-full-38776223956 | output/archive/2026/10/16/early/20261016-0118-early-full-38776223956.json |
| noon | ready_b | B | 20261016-1259-noon-full-38853392975 | output/archive/2026/10/16/noon/20261016-1259-noon-full-38853392975.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-16-early | 2026-10-15 | 2026-10-15T15:36:00+08:00 | output/archive/2026/10/16/early/20261016-0118-early-full-38776223956.json | `3ae8d67ab63c287fcb42c4006081b1e2788c25d8471e2d74bb8cd76919797915` |
| noon | B | 2026-10-16-noon | 2026-10-16 | 2026-10-16T11:30:00+08:00 | output/archive/2026/10/16/noon/20261016-1259-noon-full-38853392975.json | `bdcdeeb4497a780d0a9d20a409031ab3a135f86d74d23cccb6e492519a738dd7` |
| close | A | 2026-10-16-close | 2026-10-16 | 2026-10-16T15:35:45+08:00 | output/archive/2026/10/16/close/20261016-1627-close-full-38873766757.json | `da3dff8af48eae601a043f7652135dc6ea5587a1fe828c141dee1bd4ac1857ab` |
| evening | A | 2026-10-15-evening | 2026-10-15 | 2026-10-15T15:36:00+08:00 | output/archive/2026/10/15/evening/20261015-2042-evening-full-38736707294.json | `79910bb7b525b2f33552359609d98d1ee3e7be96a08d6189306046377a44a59a` |
| intraday | B | 2026-10-15-intraday | 2026-10-15 | 2026-10-15T13:11:36+08:00 | output/archive/2026/10/15/intraday/20261015-1311-intraday-light-38685413504.json | `dd57861416df702240224cca98b0963ea2863169db041c6e852ba6d1f5af7beb` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
