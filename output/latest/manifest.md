# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-09-11T16:55:00+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-09-11

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260911-0855-early-full-34565987399 | output/archive/2026/09/11/early/20260911-0855-early-full-34565987399.json |
| noon | ready_b | B | 20260911-1205-noon-full-34581099166 | output/archive/2026/09/11/noon/20260911-1205-noon-full-34581099166.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-09-11-early | 2026-09-10 | 2026-09-10T15:00:00+08:00 | output/archive/2026/09/11/early/20260911-0855-early-full-34565987399.json | `dce07b8a500b19af05f290d646317f61d5a0596df5e2f551baa2dbe455422d62` |
| noon | B | 2026-09-11-noon | 2026-09-11 | 2026-09-11T11:30:00+08:00 | output/archive/2026/09/11/noon/20260911-1205-noon-full-34581099166.json | `6b7e98632219f64c5bf7802a5bc2d0558b948d5a4e2e932378a5329fd78f4fc7` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | B | 2026-09-06-evening | 2026-09-04 | 暂无 | output/archive/2026/09/06/evening/20260906-2035-evening-full-34043085557.json | `9237d955ab392d5c8c8cd824d02c82c0b8a82222d838dd2992e942c948fb0c54` |
| intraday | A | 2026-09-02-intraday | 2026-09-02 | 2026-09-02T15:00:04+08:00 | output/archive/2026/09/02/intraday/20260902-1005-intraday-light-33601639418.json | `9a7dba4c0af55df7ddc9a8ddf056d93a341387de2d01f4f8034fc671e47552f0` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
