# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-29T13:43:00+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-28

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261029-0229-early-full-40745386285 | output/archive/2026/10/29/early/20261029-0229-early-full-40745386285.json |
| noon | ready_b | B | 20261029-1135-noon-full-40824897210 | output/archive/2026/10/29/noon/20261029-1135-noon-full-40824897210.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-29-early | 2026-10-28 | 2026-10-28T15:36:00+08:00 | output/archive/2026/10/29/early/20261029-0229-early-full-40745386285.json | `3e9143dfc4eb40b5dd9ce2ccb42d32346ec1a2c6ff949ae15e3d2bc5454fcaf4` |
| noon | B | 2026-10-29-noon | 2026-10-29 | 2026-10-29T11:30:00+08:00 | output/archive/2026/10/29/noon/20261029-1135-noon-full-40824897210.json | `c81bc0d58ab5d94b11803d5c8f55b52a63d54110b27ae0cb0729f8d23122d48d` |
| close | A | 2026-10-28-close | 2026-10-28 | 2026-10-28T15:36:00+08:00 | output/archive/2026/10/28/close/20261028-1840-close-full-40673944596.json | `923d7f13c2ccbd72a79795d7067ca95e6ef07036d855544c3244923cd69acb63` |
| evening | A | 2026-10-28-evening | 2026-10-28 | 2026-10-28T15:36:00+08:00 | output/archive/2026/10/28/evening/20261028-2207-evening-full-40702717902.json | `e96faaa282c10233b490c766eed3963fd391644305b585c1b4027bcb03334eed` |
| intraday | B | 2026-10-29-intraday | 2026-10-29 | 2026-10-29T13:42:39+08:00 | output/archive/2026/10/29/intraday/20261029-1342-intraday-light-40824897210.json | `bf46817b8e407d0952fa46cd1203fa24283cf9fa8350512af6d0e2582c8aed39` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
