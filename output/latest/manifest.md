# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-18T17:01:45+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-18

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260918-0855-early-full-35310664097 | output/archive/2026/09/18/early/20260918-0855-early-full-35310664097.json |
| noon | ready_b | B | 20260918-1205-noon-full-35326923819 | output/archive/2026/09/18/noon/20260918-1205-noon-full-35326923819.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-18-early | 2026-09-17 | 2026-09-17T15:00:00+08:00 | output/archive/2026/09/18/early/20260918-0855-early-full-35310664097.json | `0a0a9d49aebf4f1621e54e86f1f37ff0e17ccdda1a296c54843b41b57373c708` |
| noon | B | 2026-09-18-noon | 2026-09-18 | 2026-09-18T11:30:00+08:00 | output/archive/2026/09/18/noon/20260918-1205-noon-full-35326923819.json | `7d703db28818902b542d423e772637e3e05246cc1d88411489e8aedacb003643` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-12-evening | 2026-09-11 | 暂无 | output/archive/2026/09/12/evening/20260912-2050-evening-full-34623942689.json | `0694fc7ab2d62b5009b2a494416a03e7787e51fd8687f09937dfadaca038b83a` |
| intraday | A | 2026-09-16-intraday | 2026-09-16 | 2026-09-16T15:35:45+08:00 | output/archive/2026/09/16/intraday/20260916-1005-intraday-light-35069343260.json | `226c5c7b7a87a702b27f4cacd08ff691499fa9298af0cd9d21c109187e3193e7` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
