# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-15T13:11:38+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-14

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261015-0133-early-full-38607645381 | output/archive/2026/10/15/early/20261015-0133-early-full-38607645381.json |
| noon | ready_b | B | 20261015-1232-noon-full-38681990163 | output/archive/2026/10/15/noon/20261015-1232-noon-full-38681990163.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-15-early | 2026-10-14 | 2026-10-14T15:36:00+08:00 | output/archive/2026/10/15/early/20261015-0133-early-full-38607645381.json | `a6d06b8b2dc5550fa5f131d0c6541343c2246e612a05b1d1d21901e870377f6b` |
| noon | B | 2026-10-15-noon | 2026-10-15 | 2026-10-15T11:30:00+08:00 | output/archive/2026/10/15/noon/20261015-1232-noon-full-38681990163.json | `93783775bcecd7cc7ebbd41d9e85cda71ae59918f4acc2ebae5807a69176a450` |
| close | A | 2026-10-14-close | 2026-10-14 | 2026-10-14T15:36:00+08:00 | output/archive/2026/10/14/close/20261014-1736-close-full-38543527486.json | `86da9415dc7f363a390cb409fed45529a114c3dbdb024baa8f152f3299a19f1e` |
| evening | A | 2026-10-14-evening | 2026-10-14 | 2026-10-14T15:36:00+08:00 | output/archive/2026/10/14/evening/20261014-2055-evening-full-38567531329.json | `4899b786b8d3e54d6791d4415a5524c156e07a79b555f21885472e232faf0613` |
| intraday | B | 2026-10-15-intraday | 2026-10-15 | 2026-10-15T13:11:36+08:00 | output/archive/2026/10/15/intraday/20261015-1311-intraday-light-38685413504.json | `dd57861416df702240224cca98b0963ea2863169db041c6e852ba6d1f5af7beb` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
