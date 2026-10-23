# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-10-23T17:17:40+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-10-23

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261023-0134-early-full-39823832800 | output/archive/2026/10/23/early/20261023-0134-early-full-39823832800.json |
| noon | ready_b | B | 20261023-1244-noon-full-39901859680 | output/archive/2026/10/23/noon/20261023-1244-noon-full-39901859680.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-10-23-early | 2026-10-22 | 2026-10-22T15:36:30+08:00 | output/archive/2026/10/23/early/20261023-0134-early-full-39823832800.json | `eb0605a86840625ad998dc9f644d34489aa06da1baad581e6de1f0690ac1e638` |
| noon | B | 2026-10-23-noon | 2026-10-23 | 2026-10-23T11:30:00+08:00 | output/archive/2026/10/23/noon/20261023-1244-noon-full-39901859680.json | `18e2d40c1e582b701bfc45caf8f122fd8b86160389f3ddcec6fa8f0045c277e7` |
| close | A | 2026-10-23-close | 2026-10-23 | 2026-10-23T15:36:00+08:00 | output/archive/2026/10/23/close/20261023-1717-close-full-39930670404.json | `6997ecba501ff68b2b2ebdb6ccd0ae281910d1db53535c43a517e51446e8d05a` |
| evening | A | 2026-10-22-evening | 2026-10-22 | 2026-10-22T15:36:30+08:00 | output/archive/2026/10/22/evening/20261022-2102-evening-full-39783268945.json | `686bd5812a72d8c8ac0c35aa6f0f33b29cf0c79405f753b99cd9c29ef420411b` |
| intraday | B | 2026-10-23-intraday | 2026-10-23 | 2026-10-23T13:21:41+08:00 | output/archive/2026/10/23/intraday/20261023-1321-intraday-light-39905279338.json | `a5e1ef53ca2a56ce648e00b5a7ca8a6f83c85aafe13f413570d2d937f941aea0` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
