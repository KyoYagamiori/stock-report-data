# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-30T14:26:50+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-29

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261030-0238-early-full-40932590155 | output/archive/2026/10/30/early/20261030-0238-early-full-40932590155.json |
| noon | ready_b | B | 20261030-1135-noon-full-41009790751 | output/archive/2026/10/30/noon/20261030-1135-noon-full-41009790751.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-30-early | 2026-10-29 | 2026-10-29T15:36:00+08:00 | output/archive/2026/10/30/early/20261030-0238-early-full-40932590155.json | `314d3729ce16b66b7e50b40a58e8db97844845b30f2c371f8f39a1983930b564` |
| noon | B | 2026-10-30-noon | 2026-10-30 | 2026-10-30T11:30:00+08:00 | output/archive/2026/10/30/noon/20261030-1135-noon-full-41009790751.json | `a468e46cfb599a6bacd96604136df420df527afa4d56630c95244d32dcce6e00` |
| close | A | 2026-10-29-close | 2026-10-29 | 2026-10-29T15:36:00+08:00 | output/archive/2026/10/29/close/20261029-1858-close-full-40861608597.json | `45a7a834d4ddf29271664eec9b5035890442b0c096c0cda2ef96bc92dcf401df` |
| evening | A | 2026-10-29-evening | 2026-10-29 | 2026-10-29T15:36:00+08:00 | output/archive/2026/10/29/evening/20261029-2228-evening-full-40891780353.json | `6f46168f4ef6245415ea61ff8cd8ba39b2718e142e504929f901d1a23179497a` |
| intraday | B | 2026-10-30-intraday | 2026-10-30 | 2026-10-30T14:26:47+08:00 | output/archive/2026/10/30/intraday/20261030-1426-intraday-light-41014061614.json | `a2b4fe39a716b6a77642e764028a952a0363fcf7e707624549367f32809ba119` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
