# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-01T15:43:06+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-01

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260901-0840-early-full-33474209345 | output/archive/2026/09/01/early/20260901-0840-early-full-33474209345.json |
| noon | ready_b | B | 20260901-1135-noon-full-33474209345 | output/archive/2026/09/01/noon/20260901-1135-noon-full-33474209345.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-01-early | 2026-08-31 | 2026-08-31T15:00:00+08:00 | output/archive/2026/09/01/early/20260901-0840-early-full-33474209345.json | `dc31ef88ca731a30e88071c65c591a92d9610befdf05bdae20c851f67471f583` |
| noon | B | 2026-09-01-noon | 2026-09-01 | 2026-09-01T11:30:00+08:00 | output/archive/2026/09/01/noon/20260901-1135-noon-full-33474209345.json | `084461eb48d367f8af3c16579109f47515a3afebad95ecf2a93f8a4a8093af0c` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-08-30-evening | 2026-08-28 | 暂无 | output/archive/2026/08/30/evening/20260830-2035-evening-full-33264053821.json | `2784a42124a1b7b4e78d2193064ec21804003c214cb00efc558e96275eb622ac` |
| intraday | A | 2026-09-01-intraday | 2026-09-01 | 2026-09-01T15:35:45+08:00 | output/archive/2026/09/01/intraday/20260901-1005-intraday-light-33483335389.json | `5a73958330975bebe063502bacbed8332f6301d8e6a60701d26a4e54897f7a19` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
