# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-17T17:26:54+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-17

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260917-0855-early-full-35186411534 | output/archive/2026/09/17/early/20260917-0855-early-full-35186411534.json |
| noon | ready_b | B | 20260917-1205-noon-full-35204678198 | output/archive/2026/09/17/noon/20260917-1205-noon-full-35204678198.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-17-early | 2026-09-16 | 2026-09-16T15:00:00+08:00 | output/archive/2026/09/17/early/20260917-0855-early-full-35186411534.json | `25027c5a580015d7036af43b301d6516b12415992d0f7ae7cf0eba851af52d37` |
| noon | B | 2026-09-17-noon | 2026-09-17 | 2026-09-17T11:30:00+08:00 | output/archive/2026/09/17/noon/20260917-1205-noon-full-35204678198.json | `d2e51da59b9f678bbfb10b89cb1a230837f2ea840ebc06d62d99688cc1bb87da` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-12-evening | 2026-09-11 | 暂无 | output/archive/2026/09/12/evening/20260912-2050-evening-full-34623942689.json | `0694fc7ab2d62b5009b2a494416a03e7787e51fd8687f09937dfadaca038b83a` |
| intraday | A | 2026-09-16-intraday | 2026-09-16 | 2026-09-16T15:35:45+08:00 | output/archive/2026/09/16/intraday/20260916-1005-intraday-light-35069343260.json | `226c5c7b7a87a702b27f4cacd08ff691499fa9298af0cd9d21c109187e3193e7` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
