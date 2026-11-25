# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-11-25T22:12:01+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-11-25

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261125-0645-early-full-45503545843 | output/archive/2026/11/25/early/20261125-0645-early-full-45503545843.json |
| noon | ready_b | B | 20261125-1131-noon-full-45540412087 | output/archive/2026/11/25/noon/20261125-1131-noon-full-45540412087.json |
| evening | ready_b | B | 20261125-2212-evening-full-45631100238 | output/archive/2026/11/25/evening/20261125-2212-evening-full-45631100238.json |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-11-25-early | 2026-11-24 | 2026-11-24T15:36:00+08:00 | output/archive/2026/11/25/early/20261125-0645-early-full-45503545843.json | `5f6ade52b9b1cc496b46629199d647484ff807f858a1dbe8631f4a59513a464c` |
| noon | B | 2026-11-25-noon | 2026-11-25 | 2026-11-25T11:30:00+08:00 | output/archive/2026/11/25/noon/20261125-1131-noon-full-45540412087.json | `e62e59a08531c6d47e60d34d86c88460006d747c6f53394d4087566b49dc7ea6` |
| close | B | 2026-11-25-close | 2026-11-25 | 2026-11-25T15:36:00+08:00 | output/archive/2026/11/25/close/20261125-1710-close-full-45582533778.json | `0f6deeb6549a12a2dad94e31e4f79b3d47c1abeab5322d025a482c457cc2675d` |
| evening | B | 2026-11-25-evening | 2026-11-25 | 2026-11-25T15:36:00+08:00 | output/archive/2026/11/25/evening/20261125-2212-evening-full-45631100238.json | `da1e2e64c591294a9c1daee6397cdb8c0c7b6f2440073601779f97c0ffa249c0` |
| intraday | B | 2026-11-20-intraday | 2026-11-20 | 2026-11-20T15:08:20+08:00 | output/archive/2026/11/20/intraday/20261120-1508-intraday-light-44692544503.json | `9151f237c75425327f0524ea9d6cef3d9d818cee9e382713ccea3abe4953c8c9` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
