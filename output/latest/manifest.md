# 股票行情快照 Manifest

- Schema：1.6.1
- 更新时间：2026-08-18T15:50:17+08:00
- 交易日状态：交易日
- 最近已完成交易日：2026-08-18

## 报告就绪状态

| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |
|---|---|---|---|---|
| early | ready_a | A | 20260818-0855-early-full-32090862708 | output/archive/2026/08/18/early/20260818-0855-early-full-32090862708.json |
| noon | ready_b | B | 20260818-1225-noon-full-32101026145 | output/archive/2026/08/18/noon/20260818-1225-noon-full-32101026145.json |
| evening | not_ready | 暂无 | 暂无 | 暂无 |

## 权威快照指针

| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |
|---|---|---|---|---|---|---|
| early | A | 2026-08-18-early | 2026-08-17 | 2026-08-17T15:00:00+08:00 | output/archive/2026/08/18/early/20260818-0855-early-full-32090862708.json | `8088c68848101675e20ecaa9faf2b569f1c7cae153699e53474c316f97148c84` |
| noon | B | 2026-08-18-noon | 2026-08-18 | 2026-08-18T11:30:00+08:00 | output/archive/2026/08/18/noon/20260818-1225-noon-full-32101026145.json | `1d4a1fbbe0aeaddb9da0f72c375c7dae16214f303f734aa92229b96b09e855b6` |
| close | A | 2026-08-17-close | 2026-08-17 | 2026-08-17T15:35:45+08:00 | output/archive/2026/08/17/close/20260817-1520-close-full-32034729057.json | `4a2c1643f2dfa327e5351618e74d1b3d7576e20905e30f0c3bd8173f1b9a3250` |
| evening | A | 2026-08-17-evening | 2026-08-17 | 2026-08-17T15:35:45+08:00 | output/archive/2026/08/17/evening/20260817-2050-evening-full-32035300263.json | `4f1c9c460e2e22fd876e3eb4e4535678521064669d6cee8bef9145cbb6b3b201` |
| intraday | A | 2026-08-18-intraday | 2026-08-18 | 2026-08-18T15:35:45+08:00 | output/archive/2026/08/18/intraday/20260818-1505-intraday-light-32113181637.json | `89315668b5776f6a1e25a4a6778d5284449bf6cca9659fa17033f6a8fef0e599` |

> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。
