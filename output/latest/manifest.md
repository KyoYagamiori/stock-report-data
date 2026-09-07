# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-07T17:18:21+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-07

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260907-0855-early-full-34086932057 | output/archive/2026/09/07/early/20260907-0855-early-full-34086932057.json |
| noon | ready_b | B | 20260907-1205-noon-full-34104820136 | output/archive/2026/09/07/noon/20260907-1205-noon-full-34104820136.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-07-early | 2026-09-04 | 2026-09-04T15:00:00+08:00 | output/archive/2026/09/07/early/20260907-0855-early-full-34086932057.json | `8b46bdf5884761e436e73c6ba8f772a81e6fe01418214a5145112b519c1f7be1` |
| noon | B | 2026-09-07-noon | 2026-09-07 | 2026-09-07T11:30:00+08:00 | output/archive/2026/09/07/noon/20260907-1205-noon-full-34104820136.json | `6eee5d43d1be1cbe9881e5590db255cbed9774ac2d32f61287e13a494bcecc78` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | B | 2026-09-06-evening | 2026-09-04 | 暂无 | output/archive/2026/09/06/evening/20260906-2035-evening-full-34043085557.json | `9237d955ab392d5c8c8cd824d02c82c0b8a82222d838dd2992e942c948fb0c54` |
| intraday | A | 2026-09-02-intraday | 2026-09-02 | 2026-09-02T15:00:04+08:00 | output/archive/2026/09/02/intraday/20260902-1005-intraday-light-33601639418.json | `9a7dba4c0af55df7ddc9a8ddf056d93a341387de2d01f4f8034fc671e47552f0` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
