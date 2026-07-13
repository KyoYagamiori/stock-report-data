# Stock Report Data

This public mirror only contains sanitized structured market snapshots for GPT report generation.

## Read Order For ChatGPT

Use GitHub file access first. Raw/CDN/Jina links can return stale cached content.

Preferred GitHub.fetch_file paths:

1. repository_full_name=KyoYagamiori/stock-report-data, path=output/latest/snapshot_status.md, ref=main
2. repository_full_name=KyoYagamiori/stock-report-data, path=output/latest/report_data_compact.md, ref=main
3. repository_full_name=KyoYagamiori/stock-report-data, path=output/latest/report_data.md, ref=main

If a fetched file has an old `生成时间`, treat it as stale cache and try the GitHub contents API or repository page. Do not use stale Raw/CDN/Jina content as the current snapshot.

Snapshot file links:

- https://github.com/KyoYagamiori/stock-report-data
- https://github.com/KyoYagamiori/stock-report-data/blob/main/output/latest/snapshot_status.md
- https://github.com/KyoYagamiori/stock-report-data/blob/main/output/latest/report_data_compact.md
- https://github.com/KyoYagamiori/stock-report-data/blob/main/output/latest/report_data.md
- https://api.github.com/repos/KyoYagamiori/stock-report-data/contents/output/latest/snapshot_status.md?ref=main
- https://api.github.com/repos/KyoYagamiori/stock-report-data/contents/output/latest/report_data_compact.md?ref=main
- https://api.github.com/repos/KyoYagamiori/stock-report-data/contents/output/latest/report_data.md?ref=main
- https://raw.githubusercontent.com/KyoYagamiori/stock-report-data/main/output/latest/snapshot_status.md
- https://raw.githubusercontent.com/KyoYagamiori/stock-report-data/main/output/latest/report_data_compact.md
- https://raw.githubusercontent.com/KyoYagamiori/stock-report-data/main/output/latest/report_data.md

Use this mirror only for structured market snapshot verification. Previous report context should come from the same ChatGPT task/report thread via the `供下一篇读取的生产线摘要` block, not from this public mirror.

The private research repository, historical report text, prompts, portfolio details, and execution records are not mirrored here.

---

<!-- SNAPSHOT_STATUS_START -->

# 股票报告快照读取状态

生成时间：2026-07-13T18:35:37+08:00
快照类型：晚报前快照
适合报告：21:30 晚报收盘与盘后核验
生成日期：2026-07-13
生成时间：中国时间 18:35
使用限制：优先读取实时/准实时口径，作为晚报量价核验主口径；若字段缺失，必须明确标注不可核验。

## 数据质量

- 股票数量：23
- 实时/准实时可用股票数：23
- 均线字段可用股票数：23
- 箱体字段可用股票数：23
- 最新交易日集合：2026-07-13
- 实时/准实时行情时间集合：15:34:59, 16:29:00, 16:29:15, 16:29:30, 16:29:45

## 观察池摘要

- 当前 active 股票数量：23
- high priority 股票：
- 长电科技 600584
- 紫光股份 000938
- 浪潮信息 000977
- 中电港 001287
- 英维克 002837
- 中际旭创 300308
- 胜宏科技 300476
- 新易盛 300502
- 江波龙 301308
- 中科曙光 603019
- 寒武纪 688256
- 盛合晶微 688820
- 中芯国际 688981
- 本次新增股票：
- 无
- 本次降级股票：
- 无

## 重点结论摘要

- 涨停池观察股：
- 无
- 明显放量上涨：
- 无
- 明显放量下跌：
- 华天科技 002185
- 下一份报告重点核验：
- 长电科技 600584
- 紫光股份 000938
- 浪潮信息 000977
- 中电港 001287
- 英维克 002837
- 中际旭创 300308
- 胜宏科技 300476
- 新易盛 300502
- 江波龙 301308
- 中科曙光 603019
- 寒武纪 688256
- 盛合晶微 688820
- 中芯国际 688981
- 通富微电 002156
- 华天科技 002185
- 斯达半导 603290

## 读取规则

1. 这是 ChatGPT 报告生产线的首选入口，用于确认公开镜像是否已经更新。
2. 如果本文件生成时间早于当前报告应使用的快照时点，说明读取器拿到了旧缓存，必须改读 GitHub contents API 或 report_data_compact.md。
3. 不得把 Raw/CDN/Jina 返回的旧生成时间当作本次快照读取成功。
4. 若状态文件可用但完整快照不可用，优先读取 output/latest/report_data_compact.md，仍不足时再联网实时行情兜底。

## 数据更新提示

- 行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。
- 东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。


<!-- SNAPSHOT_STATUS_END -->

---

<!-- COMPACT_SNAPSHOT_START -->

# 股票报告结构化行情紧凑快照

生成时间：2026-07-13T18:35:37+08:00
快照类型：晚报前快照
适合报告：21:30 晚报收盘与盘后核验
生成日期：2026-07-13
生成时间：中国时间 18:35

## 逐股紧凑字段

| code | name | theme | priority | source | quote_time | trade_date | price | pct | amount | turnover | ma5 | ma10 | ma20 | ma60 | box_lower | box_upper | box_position | breakout | pullback | signals |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| 600584 | 长电科技 | 先进封装/半导体封测 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 99.05 | -2.04% | 250.12亿 | 13.59% | 99.76 | 99.09 | 94.37 | 72.43 | 67.95 | 113.87 | 箱体中部 | 113.87 | 67.95 | 缩量回调 |
| 000938 | 紫光股份 | 算力网络/服务器 | high | 新浪实时行情接口 | 16:29:45 | 2026-07-13 | 38.40 | -0.03% | 190.57亿 | 17.27% | 35.52 | 32.90 | 29.98 | 29.78 | 25.34 | 40.28 | 接近箱体上沿 | 40.28 | 25.34 | 暂无显著自动量价信号 |
| 000977 | 浪潮信息 | AI服务器/国产算力 | high | 新浪实时行情接口 | 16:29:30 | 2026-07-13 | 85.49 | -4.50% | 147.56亿 | 11.49% | 82.05 | 74.73 | 69.81 | 68.97 | 58.49 | 94.38 | 箱体中部 | 94.38 | 58.49 | 缩量回调 |
| 001287 | 中电港 | 中报预增/AI硬件/数据中心/先进计算/存储涨价/电子元器件分销 | high | 新浪实时行情接口 | 16:29:45 | 2026-07-13 | 28.07 | -9.54% | 16.90亿 | 7.55% | 29.61 | 29.86 | 29.51 | 28.14 | 24.39 | 32.64 | 箱体中部 | 32.64 | 24.39 | 缩量回调 |
| 002837 | 英维克 | 液冷散热/机柜级液冷 | high | 新浪实时行情接口 | 16:29:00 | 2026-07-13 | 66.98 | -8.92% | 40.61亿 | 5.15% | 71.96 | 73.10 | 75.58 | 87.24 | 66.27 | 89.69 | 接近箱体下沿 | 89.69 | 66.27 | 缩量回调 |
| 300308 | 中际旭创 | AI运力/光模块 | high | 新浪实时行情接口 | 16:29:30 | 2026-07-13 | 1108.00 | 1.28% | 383.91亿 | 3.10% | 1129.43 | 1149.82 | 1221.86 | 1083.75 | 1060.34 | 1416.88 | 接近箱体下沿 | 1416.88 | 1060.34 | 缩量上涨 |
| 300476 | 胜宏科技 | AI运力/高速PCB | high | 新浪实时行情接口 | 16:29:45 | 2026-07-13 | 273.01 | 0.37% | 97.61亿 | 4.11% | 281.26 | 298.65 | 322.47 | 336.75 | 268.00 | 375.80 | 接近箱体下沿 | 375.80 | 268.00 | 缩量上涨 |
| 300502 | 新易盛 | AI运力/光模块 | high | 新浪实时行情接口 | 16:29:00 | 2026-07-13 | 512.50 | -2.02% | 213.87亿 | 3.28% | 520.40 | 532.64 | 548.80 | 596.28 | 490.10 | 618.87 | 接近箱体下沿 | 618.87 | 490.10 | 缩量回调 |
| 301308 | 江波龙 | 存储芯片/端侧AI存储/中报业绩兑现 | high | 新浪实时行情接口 | 16:29:45 | 2026-07-13 | 522.04 | -11.16% | 97.70亿 | 6.39% | 590.05 | 622.09 | 617.60 | 533.99 | 501.28 | 749.88 | 接近箱体下沿 | 749.88 | 501.28 | 缩量回调 |
| 603019 | 中科曙光 | 国产算力/AI服务器 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 106.13 | -1.27% | 133.74亿 | 8.46% | 101.85 | 100.08 | 95.25 | 92.63 | 82.58 | 113.00 | 箱体中部 | 113.00 | 82.58 | 缩量回调 |
| 688256 | 寒武纪 | AI芯片 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 1390.00 | -0.71% | 236.02亿 | 2.62% | 1425.31 | 1430.22 | 1426.98 | 1371.38 | 1238.88 | 1620.00 | 箱体中部 | 1620.00 | 1238.88 | 暂无显著自动量价信号 |
| 688820 | 盛合晶微 | 先进封装/Chiplet/2.5D/3DIC | high | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 188.50 | -1.80% | 48.76亿 | 14.61% | 195.46 | 189.86 | 191.00 | 暂无 | 157.00 | 222.22 | 箱体中部 | 222.22 | 157.00 | 缩量回调 |
| 688981 | 中芯国际 | 半导体制造 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 163.58 | 0.34% | 179.54亿 | 5.41% | 159.42 | 153.88 | 148.52 | 131.99 | 124.89 | 176.34 | 箱体中部 | 176.34 | 124.89 | 缩量上涨 |
| 002156 | 通富微电 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 16:29:15 | 2026-07-13 | 73.57 | 3.69% | 159.50亿 | 14.09% | 70.10 | 69.86 | 69.74 | 62.42 | 56.68 | 79.38 | 箱体中部 | 79.38 | 56.68 | 暂无显著自动量价信号 |
| 002185 | 华天科技 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 16:29:30 | 2026-07-13 | 24.13 | -4.66% | 207.71亿 | 24.55% | 23.33 | 22.06 | 21.10 | 17.31 | 16.07 | 26.81 | 箱体中部 | 26.81 | 16.07 | 放量下跌 |
| 603290 | 斯达半导 | 功率半导体/IGBT模块/AI电力运力上游 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 116.99 | -5.51% | 12.03亿 | 4.17% | 126.39 | 132.97 | 132.88 | 121.18 | 108.33 | 159.69 | 接近箱体下沿 | 159.69 | 108.33 | 缩量回调 |
| 000301 | 东方盛虹 | 石化化工/中报预增 | medium | 新浪实时行情接口 | 16:29:30 | 2026-07-13 | 11.40 | -9.16% | 4.74亿 | 0.61% | 12.34 | 12.36 | 12.15 | 12.32 | 10.80 | 13.89 | 接近箱体下沿 | 13.89 | 10.80 | 缩量回调 |
| 002371 | 北方华创 | 半导体设备 | medium | 新浪实时行情接口 | 16:29:15 | 2026-07-13 | 764.30 | -4.58% | 127.85亿 | 2.25% | 810.49 | 833.38 | 792.38 | 648.45 | 640.00 | 968.00 | 箱体中部 | 968.00 | 640.00 | 缩量回调 |
| 300821 | 东岳硅材 | 有机硅/周期化工/中报预增 | medium | 新浪实时行情接口 | 16:29:45 | 2026-07-13 | 21.92 | -18.69% | 43.13亿 | 15.37% | 25.79 | 23.46 | 21.45 | 17.48 | 16.44 | 31.00 | 箱体中部 | 31.00 | 16.44 | 缩量回调 |
| 601872 | 招商轮船 | 航运/中报预增 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 14.83 | -4.14% | 16.18亿 | 1.34% | 15.63 | 16.38 | 17.58 | 17.23 | 14.67 | 22.16 | 接近箱体下沿 | 22.16 | 14.67 | 暂无显著自动量价信号 |
| 603618 | 杭电股份 | 光纤光缆/光通信/中报预增 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 31.69 | -10.00% | 18.29亿 | 8.04% | 35.94 | 42.01 | 46.71 | 39.30 | 31.69 | 57.21 | 箱体下沿下方/破位区 | 57.21 | 31.69 | 缩量回调 |
| 688361 | 中科飞测 | 半导体设备/检测 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 389.99 | -7.75% | 52.96亿 | 3.75% | 404.77 | 391.68 | 340.84 | 249.08 | 220.31 | 458.98 | 箱体中部 | 458.98 | 220.31 | 暂无显著自动量价信号 |
| 688596 | 正帆科技 | 半导体设备/材料 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-13 | 63.98 | -5.95% | 20.78亿 | 10.52% | 73.30 | 75.76 | 62.37 | 46.93 | 43.00 | 88.66 | 箱体中部 | 88.66 | 43.00 | 缩量回调 |

## 使用要求

1. 本文件是完整快照的紧凑版，优先用于 ChatGPT 快速确认均线、箱体、价格、涨跌幅、成交额、换手率等核心字段。
2. 如果需要封板资金、炸板次数、连板数、逐股异常提示等完整字段，再读取 report_data.md 或 report_data.json。
3. 若本文件生成时间不符合当前报告时点，视为旧缓存，不得采用。


<!-- COMPACT_SNAPSHOT_END -->
