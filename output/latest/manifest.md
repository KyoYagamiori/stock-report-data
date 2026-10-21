# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-21T12:41:58+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-20

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261021-0129-early-full-39466403190 | output/archive/2026/10/21/early/20261021-0129-early-full-39466403190.json |
| noon | ready_b | B | 20261021-1240-noon-full-39545330030 | output/archive/2026/10/21/noon/20261021-1240-noon-full-39545330030.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-21-early | 2026-10-20 | 2026-10-20T15:36:00+08:00 | output/archive/2026/10/21/early/20261021-0129-early-full-39466403190.json | `350403d00a4a12bb756c43d4e09c7aac4a025c750df59c4c7322c3d63af2b1bb` |
| noon | B | 2026-10-21-noon | 2026-10-21 | 2026-10-21T11:30:00+08:00 | output/archive/2026/10/21/noon/20261021-1240-noon-full-39545330030.json | `0879415166ab482cc47aa53441e25fa5052f9b9568eac08a4f79431f07197a42` |
| close | A | 2026-10-20-close | 2026-10-20 | 2026-10-20T15:36:00+08:00 | output/archive/2026/10/20/close/20261020-1957-close-full-39418664879.json | `2438930a3cbc7e971a215022a0846ab39648f3fe4691362e9b8505c46511dc0e` |
| evening | A | 2026-10-20-evening | 2026-10-20 | 2026-10-20T15:36:00+08:00 | output/archive/2026/10/20/evening/20261020-2047-evening-full-39424985686.json | `adf88ffbc7bc3eebc7e9d42c9d364f4c94a0f140aa4e19395de8f64bb841ea14` |
| intraday | B | 2026-10-20-intraday | 2026-10-20 | 2026-10-20T13:17:25+08:00 | output/archive/2026/10/20/intraday/20261020-1317-intraday-light-39374053601.json | `5d0810c58c2796a7458a8a10c41332412573b363a89a405cf182c9d23611e94c` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
