# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-08-31T18:49:43+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-08-31

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260831-0855-early-full-33364207904 | output/archive/2026/08/31/early/20260831-0855-early-full-33364207904.json |
| noon | ready_b | B | 20260831-1205-noon-full-33383831517 | output/archive/2026/08/31/noon/20260831-1205-noon-full-33383831517.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-08-31-early | 2026-08-28 | 2026-08-28T15:00:00+08:00 | output/archive/2026/08/31/early/20260831-0855-early-full-33364207904.json | `6de32ca91443e894b0dbabf002865fa964d8ab113d2576634916f520b2df4b6f` |
| noon | B | 2026-08-31-noon | 2026-08-31 | 2026-08-31T11:30:00+08:00 | output/archive/2026/08/31/noon/20260831-1205-noon-full-33383831517.json | `b9cb1ea5edbbb4ef9581e07f5de1c4eb57d1ba2c57998c9372321ce9bf3435b9` |
| close | A | 2026-08-26-close | 2026-08-26 | 2026-08-26T15:35:45+08:00 | output/archive/2026/08/26/close/20260826-1520-close-full-32975024998.json | `5587d9cdf78af2b988ce64c56cc5272e60b883c442b24471b9dac474fa998adb` |
| evening | A | 2026-08-30-evening | 2026-08-28 | 暂无 | output/archive/2026/08/30/evening/20260830-2035-evening-full-33264053821.json | `2784a42124a1b7b4e78d2193064ec21804003c214cb00efc558e96275eb622ac` |
| intraday | B | 2026-08-29-intraday | 2026-08-28 | 暂无 | output/archive/2026/08/29/intraday/20260829-1505-intraday-light-33203630193.json | `2583ba7a787f4ab93160f95a0f7099907bf0869be6d307853f52ebed8dabd6fe` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
