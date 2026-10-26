# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-26T13:17:39+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-23

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261026-0046-early-full-40213241466 | output/archive/2026/10/26/early/20261026-0046-early-full-40213241466.json |
| noon | ready_b | B | 20261026-1240-noon-full-40270275253 | output/archive/2026/10/26/noon/20261026-1240-noon-full-40270275253.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-26-early | 2026-10-23 | 2026-10-23T15:36:00+08:00 | output/archive/2026/10/26/early/20261026-0046-early-full-40213241466.json | `18cb5d29fd93687711f55be0fa3a44852ba9204b5ac0a0bd9b83dc27e31353c9` |
| noon | B | 2026-10-26-noon | 2026-10-26 | 2026-10-26T11:30:00+08:00 | output/archive/2026/10/26/noon/20261026-1240-noon-full-40270275253.json | `38bc5a0eea8c33bb24ff7fdecb2432a19f65ecc38e62b8a48fcd86677ecf1f13` |
| close | A | 2026-10-23-close | 2026-10-23 | 2026-10-23T15:36:00+08:00 | output/archive/2026/10/23/close/20261023-1957-close-full-39949686876.json | `f7551853c2ca08d8500c37078cca8f86bb2cf5e2a3815506745718475fc6c437` |
| evening | A | 2026-10-24-evening | 2026-10-23 | 2026-10-23T15:36:00+08:00 | output/archive/2026/10/24/evening/20261024-2359-evening-full-40109464384.json | `f12f0c66bd324fbfcd16309e572369e18d2c1993fdd631743ad53bfd684348d4` |
| intraday | B | 2026-10-26-intraday | 2026-10-26 | 2026-10-26T13:17:37+08:00 | output/archive/2026/10/26/intraday/20261026-1317-intraday-light-40273386292.json | `25a6ca2a8152764b427052975a80e1fd9efc24bcdadfd814f9cc9ac46fc79ccd` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
