# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-11-11T23:25:53+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-11-11

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261111-0359-early-full-42890575844 | output/archive/2026/11/11/early/20261111-0359-early-full-42890575844.json |
| noon | ready_a | A | 20261111-1135-noon-full-42953681092 | output/archive/2026/11/11/noon/20261111-1135-noon-full-42953681092.json |
| evening | ready_b | B | 20261111-2325-evening-full-43048081531 | output/archive/2026/11/11/evening/20261111-2325-evening-full-43048081531.json |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-11-11-early | 2026-11-10 | 2026-11-10T15:35:57+08:00 | output/archive/2026/11/11/early/20261111-0359-early-full-42890575844.json | `6519fc3b6bffb2be52caa1ef2155f5c9c49f72d8787b0d0aba191bb40e9e197e` |
| noon | A | 2026-11-11-noon | 2026-11-11 | 2026-11-11T11:30:00+08:00 | output/archive/2026/11/11/noon/20261111-1135-noon-full-42953681092.json | `d0e91d8d80926b10b0f94de5f3164727b85aa72338f33deaf523a9accfd13474` |
| close | B | 2026-11-11-close | 2026-11-11 | 2026-11-11T15:35:57+08:00 | output/archive/2026/11/11/close/20261111-1958-close-full-43016170058.json | `a169fb26b2e6f71e678146a61b3cd37f8e1b7db9aa18108d325c3f909af0427f` |
| evening | B | 2026-11-11-evening | 2026-11-11 | 2026-11-11T15:35:57+08:00 | output/archive/2026/11/11/evening/20261111-2325-evening-full-43048081531.json | `bbdf7cdf7d3b0a326a943a61daecf7fb32a43d2229d501830ee414254b577813` |
| intraday | B | 2026-11-11-intraday | 2026-11-11 | 2026-11-11T15:07:58+08:00 | output/archive/2026/11/11/intraday/20261111-1507-intraday-light-42977140627.json | `df4997e5883e7a1376a0bbc4076f7e39894a348cfd4db9a07f0efa5fd44a57a9` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
