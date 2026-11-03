# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-11-03T14:42:45+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-11-02

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261103-0554-early-full-41532454029 | output/archive/2026/11/03/early/20261103-0554-early-full-41532454029.json |
| noon | ready_b | B | 20261103-1230-noon-full-41578489455 | output/archive/2026/11/03/noon/20261103-1230-noon-full-41578489455.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-11-03-early | 2026-11-02 | 2026-11-02T15:36:00+08:00 | output/archive/2026/11/03/early/20261103-0554-early-full-41532454029.json | `0e8c1e85494357fce6afc8c3cf7a10f88e9250c01137ed304bfaea39a1f1d058` |
| noon | B | 2026-11-03-noon | 2026-11-03 | 2026-11-03T11:30:00+08:00 | output/archive/2026/11/03/noon/20261103-1230-noon-full-41578489455.json | `85b386548ff3b81fbb4f0ded9f6db95322d33370c19c86b693ccd162aac2f3ff` |
| close | A | 2026-11-02-close | 2026-11-02 | 2026-11-02T15:36:00+08:00 | output/archive/2026/11/02/close/20261102-1937-close-full-41438184720.json | `9559fe42ab1600e27e9f778bd81729ee4867a64fe80fac559388c521e3cb807f` |
| evening | A | 2026-11-02-evening | 2026-11-02 | 2026-11-02T15:36:00+08:00 | output/archive/2026/11/02/evening/20261102-2038-evening-full-41446317584.json | `0fda7dfeb2913e18ddab42254373283ed554f82e3db824f36ee199c6587cfaf6` |
| intraday | B | 2026-11-03-intraday | 2026-11-03 | 2026-11-03T14:42:41+08:00 | output/archive/2026/11/03/intraday/20261103-1442-intraday-light-41591535088.json | `4b7666c2002f3a43f06849ead358389360f0723d6c030dd19eec553ab4ba2caf` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
