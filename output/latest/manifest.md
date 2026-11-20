# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-11-20T15:48:00+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-11-20

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261120-0457-early-full-44613586765 | output/archive/2026/11/20/early/20261120-0457-early-full-44613586765.json |
| noon | ready_b | B | 20261120-1135-noon-full-44686789647 | output/archive/2026/11/20/noon/20261120-1135-noon-full-44686789647.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-11-20-early | 2026-11-19 | 2026-11-19T15:36:00+08:00 | output/archive/2026/11/20/early/20261120-0457-early-full-44613586765.json | `4f8623c54ba62ef22a5091cd43dd061e545d672e4395687a7b772fdefe6c61c9` |
| noon | B | 2026-11-20-noon | 2026-11-20 | 2026-11-20T11:30:00+08:00 | output/archive/2026/11/20/noon/20261120-1135-noon-full-44686789647.json | `3f7b98a0cd55d6537ce58e65ef721cb83d6b5a64d894f1da6c8a8fa4fa975938` |
| close | B | 2026-11-20-close | 2026-11-20 | 2026-11-20T15:36:00+08:00 | output/archive/2026/11/20/close/20261120-1546-close-full-44697171675.json | `9a7f13204d471be97dd2d2434c232d7a7e27371979dd59060989151f105d630a` |
| evening | A | 2026-11-19-evening | 2026-11-19 | 2026-11-19T15:36:00+08:00 | output/archive/2026/11/19/evening/20261119-2359-evening-full-44560790783.json | `bb2ad866255a4badfb4cd04f50f5ec608b64e506b129adfdb0f9602f7ffc2074` |
| intraday | B | 2026-11-20-intraday | 2026-11-20 | 2026-11-20T15:08:20+08:00 | output/archive/2026/11/20/intraday/20261120-1508-intraday-light-44692544503.json | `9151f237c75425327f0524ea9d6cef3d9d818cee9e382713ccea3abe4953c8c9` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
