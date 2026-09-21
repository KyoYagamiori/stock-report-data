# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-21T17:57:03+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-21

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260921-0840-early-full-35564407247 | output/archive/2026/09/21/early/20260921-0840-early-full-35564407247.json |
| noon | ready_b | B | 20260921-1205-noon-full-35585436309 | output/archive/2026/09/21/noon/20260921-1205-noon-full-35585436309.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-21-early | 2026-09-18 | 2026-09-18T15:00:00+08:00 | output/archive/2026/09/21/early/20260921-0840-early-full-35564407247.json | `32a9ca841b306774fbac24db28e1eddf7cef590584ccdb785f47e76bf048aad7` |
| noon | B | 2026-09-21-noon | 2026-09-21 | 2026-09-21T11:30:00+08:00 | output/archive/2026/09/21/noon/20260921-1205-noon-full-35585436309.json | `51f26f1c9630f172ed90ec08cc9fb6f0bee3c9d54c95b60f853801cb95ed5f6d` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-20-evening | 2026-09-18 | 暂无 | output/archive/2026/09/20/evening/20260920-2035-evening-full-35453562908.json | `b401bb62c0bcd9b79cc072dcab610210c4ff69124297ec2af48021057d61690e` |
| intraday | A | 2026-09-16-intraday | 2026-09-16 | 2026-09-16T15:35:45+08:00 | output/archive/2026/09/16/intraday/20260916-1005-intraday-light-35069343260.json | `226c5c7b7a87a702b27f4cacd08ff691499fa9298af0cd9d21c109187e3193e7` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
