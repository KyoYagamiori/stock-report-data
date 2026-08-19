# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-08-19T21:36:34+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-08-19

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260819-0855-early-full-32207738043 | output/archive/2026/08/19/early/20260819-0855-early-full-32207738043.json |
| noon | ready_b | B | 20260819-1225-noon-full-32217603173 | output/archive/2026/08/19/noon/20260819-1225-noon-full-32217603173.json |
| evening | ready_a | A | 20260819-2050-evening-full-32258732224 | output/archive/2026/08/19/evening/20260819-2050-evening-full-32258732224.json |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-08-19-early | 2026-08-18 | 2026-08-18T15:00:00+08:00 | output/archive/2026/08/19/early/20260819-0855-early-full-32207738043.json | `43dcd13187ad08a5c279a77adcbfa2818d18865aff22015f565185bb79a5f75e` |
| noon | B | 2026-08-19-noon | 2026-08-19 | 2026-08-19T11:30:00+08:00 | output/archive/2026/08/19/noon/20260819-1225-noon-full-32217603173.json | `5086b40522595ed379086700ea0bbec623ba1b4d740f59f107cdb016cdb90ca5` |
| close | A | 2026-08-19-close | 2026-08-19 | 2026-08-19T15:35:45+08:00 | output/archive/2026/08/19/close/20260819-1520-close-full-32258732224.json | `02e3027a479a21f3e3542ed8688fc185470d25763fe21a6e10554f9add8ed298` |
| evening | A | 2026-08-19-evening | 2026-08-19 | 2026-08-19T15:35:45+08:00 | output/archive/2026/08/19/evening/20260819-2050-evening-full-32258732224.json | `b1016d33a83bf43344d3fd91a3314f1608733e3e8138024cdd2a8221a9740264` |
| intraday | A | 2026-08-18-intraday | 2026-08-18 | 2026-08-18T15:35:45+08:00 | output/archive/2026/08/18/intraday/20260818-1505-intraday-light-32113181637.json | `89315668b5776f6a1e25a4a6778d5284449bf6cca9659fa17033f6a8fef0e599` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
