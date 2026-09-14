# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-14T13:33:10+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-11

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260914-0840-early-full-34809462747 | output/archive/2026/09/14/early/20260914-0840-early-full-34809462747.json |
| noon | ready_b | B | 20260914-1135-noon-full-34809462747 | output/archive/2026/09/14/noon/20260914-1135-noon-full-34809462747.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-14-early | 2026-09-11 | 2026-09-11T15:00:00+08:00 | output/archive/2026/09/14/early/20260914-0840-early-full-34809462747.json | `3362e3352944afd062406298a94eed2c9725f1b76a191c9cd76483cc671cdba9` |
| noon | B | 2026-09-14-noon | 2026-09-14 | 2026-09-14T11:30:00+08:00 | output/archive/2026/09/14/noon/20260914-1135-noon-full-34809462747.json | `79c318a0e4ba47092bb0f89f78b48d1473a0d98d2764414fa01493a27d5016c8` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-09-12-evening | 2026-09-11 | 暂无 | output/archive/2026/09/12/evening/20260912-2050-evening-full-34623942689.json | `0694fc7ab2d62b5009b2a494416a03e7787e51fd8687f09937dfadaca038b83a` |
| intraday | A | 2026-09-02-intraday | 2026-09-02 | 2026-09-02T15:00:04+08:00 | output/archive/2026/09/02/intraday/20260902-1005-intraday-light-33601639418.json | `9a7dba4c0af55df7ddc9a8ddf056d93a341387de2d01f4f8034fc671e47552f0` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
