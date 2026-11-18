# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-11-18T15:23:09+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-11-18

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20261118-0518-early-full-44178081298 | output/archive/2026/11/18/early/20261118-0518-early-full-44178081298.json |
| noon | ready_b | B | 20261118-1135-noon-full-44258040981 | output/archive/2026/11/18/noon/20261118-1135-noon-full-44258040981.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-11-18-early | 2026-11-17 | 2026-11-17T15:36:00+08:00 | output/archive/2026/11/18/early/20261118-0518-early-full-44178081298.json | `f0a4175af6efd828ac4fdaf18ca74a83b2c68c69fa9fa33dab5bc56998f5d33e` |
| noon | B | 2026-11-18-noon | 2026-11-18 | 2026-11-18T11:30:00+08:00 | output/archive/2026/11/18/noon/20261118-1135-noon-full-44258040981.json | `2af6ebaec30abb61aec8a77ab714161351cb3748f336fc84c4eeddd59b658a35` |
| close | B | 2026-11-18-close | 2026-11-18 | 2026-11-18T15:21:28+08:00 | output/archive/2026/11/18/close/20261118-1521-close-full-44258040981.json | `48bfaa256b1589da5cab279868f76216ff9350b6d7dcffa00d2ae18bb7f7119f` |
| evening | A | 2026-11-17-evening | 2026-11-17 | 2026-11-17T15:36:00+08:00 | output/archive/2026/11/17/evening/20261117-2139-evening-full-44094658863.json | `c004d9e17cfb010d58704cb3b22bc46387a9eafb529cce4b320156528f848377` |
| intraday | B | 2026-11-17-intraday | 2026-11-17 | 2026-11-17T10:52:21+08:00 | output/archive/2026/11/17/intraday/20261117-1052-intraday-light-44005948000.json | `7ab59c51b70a6bf539bcf52c4571ffb330af55fc0453dd74217493caf65e723b` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
