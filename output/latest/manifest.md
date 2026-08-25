# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-08-25T13:01:55+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-08-24

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260825-0855-early-full-32800561402 | output/archive/2026/08/25/early/20260825-0855-early-full-32800561402.json |
| noon | ready_b | B | 20260825-1205-noon-full-32810246482 | output/archive/2026/08/25/noon/20260825-1205-noon-full-32810246482.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-08-25-early | 2026-08-24 | 2026-08-24T15:00:00+08:00 | output/archive/2026/08/25/early/20260825-0855-early-full-32800561402.json | `250a5c54642a7f8586271e784d67dc7d43b82dbb6cbc2385863b311fd438a91d` |
| noon | B | 2026-08-25-noon | 2026-08-25 | 2026-08-25T11:30:00+08:00 | output/archive/2026/08/25/noon/20260825-1205-noon-full-32810246482.json | `4373a6c9998c7b35c544a46ac68f19905b20f855f0756c2c061fbc064f81ffd1` |
| close | A | 2026-08-20-close | 2026-08-20 | 2026-08-20T15:35:45+08:00 | output/archive/2026/08/20/close/20260820-1520-close-full-32374413712.json | `48d5ae20aa80ca907e2730af7c3294a03e48c5b0a0ff5aa40d3af743897ebfd9` |
| evening | B | 2026-08-23-evening | 2026-08-21 | 暂无 | output/archive/2026/08/23/evening/20260823-2035-evening-full-32641585605.json | `d89d2797c4963a09692b207c87b8eee6756d6c2472e554137f1ba781e82e6fc1` |
| intraday | A | 2026-08-24-intraday | 2026-08-24 | 2026-08-24T11:30:00+08:00 | output/archive/2026/08/24/intraday/20260824-1035-intraday-light-32686790802.json | `66e90806308b6b5caa2d4b687364be56b9997c02811eae4cd4196cd3fe7390ff` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
