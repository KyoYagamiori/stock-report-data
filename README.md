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

生成时间：2026-07-07T23:59:11+08:00
快照类型：晚间补充快照
适合报告：晚报补充和下一交易日早报基线
生成日期：2026-07-07
生成时间：中国时间 23:59
使用限制：若逐股最新交易日为当天且实时/准实时行情时间在15:00后，可用于当日晚报补充核验；下一交易日开盘前只能作为上一交易日基线，不代表下一交易日实时行情。

## 数据质量

- 股票数量：22
- 实时/准实时可用股票数：22
- 均线字段可用股票数：22
- 箱体字段可用股票数：22
- 最新交易日集合：2026-07-07
- 实时/准实时行情时间集合：15:34:59, 16:29:00, 16:29:15, 16:29:30, 16:29:45

## 观察池摘要

- 当前 active 股票数量：22
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
- 中芯国际 688981
- 本次新增股票：
- 无
- 本次降级股票：
- 无

## 重点结论摘要

- 涨停池观察股：
- 华天科技 002185
- 明显放量上涨：
- 华天科技 002185
- 正帆科技 688596
- 明显放量下跌：
- 中电港 001287
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
- 中芯国际 688981
- 通富微电 002156
- 华天科技 002185
- 斯达半导 603290
- 正帆科技 688596

## 读取规则

1. 这是 ChatGPT 报告生产线的首选入口，用于确认公开镜像是否已经更新。
2. 如果本文件生成时间早于当前报告应使用的快照时点，说明读取器拿到了旧缓存，必须改读 GitHub contents API 或 report_data_compact.md。
3. 不得把 Raw/CDN/Jina 返回的旧生成时间当作本次快照读取成功。
4. 若状态文件可用但完整快照不可用，优先读取 output/latest/report_data_compact.md，仍不足时再联网实时行情兜底。

## 数据更新提示

- 东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。


<!-- SNAPSHOT_STATUS_END -->

---

<!-- COMPACT_SNAPSHOT_START -->

# 股票报告结构化行情紧凑快照

生成时间：2026-07-07T23:59:11+08:00
快照类型：晚间补充快照
适合报告：晚报补充和下一交易日早报基线
生成日期：2026-07-07
生成时间：中国时间 23:59

## 逐股紧凑字段

| code | name | theme | priority | source | quote_time | trade_date | price | pct | amount | turnover | ma5 | ma10 | ma20 | ma60 | box_lower | box_upper | box_position | breakout | pullback | signals |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| 600584 | 长电科技 | 先进封装/半导体封测 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 100.99 | 6.21% | 225.79亿 | 12.70% | 97.92 | 99.61 | 88.99 | 68.67 | 67.95 | 111.11 | 箱体中部 | 111.11 | 67.95 | 暂无显著自动量价信号 |
| 000938 | 紫光股份 | 算力网络/服务器 | high | 新浪实时行情接口 | 16:29:45 | 2026-07-07 | 31.48 | -5.49% | 89.18亿 | 9.80% | 30.81 | 29.08 | 27.82 | 29.18 | 25.03 | 33.31 | 箱体中部 | 33.31 | 25.03 | 缩量回调 |
| 000977 | 浪潮信息 | AI服务器/国产算力 | high | 新浪实时行情接口 | 16:29:30 | 2026-07-07 | 71.06 | 1.94% | 73.59亿 | 7.03% | 67.63 | 67.12 | 64.58 | 67.80 | 57.15 | 73.23 | 接近箱体上沿 | 73.23 | 57.15 | 缩量上涨 |
| 001287 | 中电港 | 中报预增/AI硬件/数据中心/先进计算/存储涨价/电子元器件分销 | high | 新浪实时行情接口 | 16:29:45 | 2026-07-07 | 29.20 | -7.21% | 22.93亿 | 10.21% | 29.71 | 30.10 | 28.72 | 27.92 | 24.39 | 32.64 | 箱体中部 | 32.64 | 24.39 | 放量下跌 |
| 002837 | 英维克 | 液冷散热/机柜级液冷 | high | 新浪实时行情接口 | 16:29:00 | 2026-07-07 | 71.29 | -3.74% | 37.05亿 | 4.47% | 72.58 | 77.16 | 74.75 | 89.18 | 63.55 | 89.69 | 箱体中部 | 89.69 | 63.55 | 缩量回调 |
| 300308 | 中际旭创 | AI运力/光模块 | high | 新浪实时行情接口 | 16:29:30 | 2026-07-07 | 1121.90 | 2.09% | 327.09亿 | 2.64% | 1140.60 | 1208.25 | 1225.59 | 1057.31 | 1060.34 | 1416.88 | 接近箱体下沿 | 1416.88 | 1060.34 | 缩量上涨 |
| 300476 | 胜宏科技 | AI运力/高速PCB | high | 新浪实时行情接口 | 16:29:45 | 2026-07-07 | 284.92 | -2.68% | 80.14亿 | 3.25% | 303.74 | 319.37 | 332.67 | 337.66 | 277.01 | 375.80 | 接近箱体下沿 | 375.80 | 277.01 | 缩量回调 |
| 300502 | 新易盛 | AI运力/光模块 | high | 新浪实时行情接口 | 16:29:00 | 2026-07-07 | 510.10 | 0.63% | 229.35亿 | 3.62% | 525.51 | 552.33 | 573.74 | 595.50 | 490.10 | 799.75 | 接近箱体下沿 | 799.75 | 490.10 | 暂无显著自动量价信号 |
| 301308 | 江波龙 | 存储芯片/端侧AI存储/中报业绩兑现 | high | 新浪实时行情接口 | 16:29:45 | 2026-07-07 | 627.90 | -7.91% | 117.71亿 | 6.60% | 638.96 | 659.86 | 604.05 | 518.66 | 497.00 | 749.88 | 箱体中部 | 749.88 | 497.00 | 缩量回调 |
| 603019 | 中科曙光 | 国产算力/AI服务器 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 93.50 | -1.12% | 56.80亿 | 4.10% | 95.55 | 96.80 | 90.79 | 91.47 | 78.90 | 109.60 | 箱体中部 | 109.60 | 78.90 | 缩量回调 |
| 688256 | 寒武纪 | AI芯片 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 1388.00 | 1.33% | 166.42亿 | 1.89% | 1393.62 | 1446.16 | 1388.08 | 1356.90 | 1199.00 | 1620.00 | 箱体中部 | 1620.00 | 1199.00 | 暂无显著自动量价信号 |
| 688981 | 中芯国际 | 半导体制造 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 145.42 | 0.99% | 100.87亿 | 3.45% | 145.66 | 149.53 | 141.18 | 127.85 | 120.89 | 166.88 | 箱体中部 | 166.88 | 120.89 | 缩量上涨 |
| 002156 | 通富微电 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 16:29:15 | 2026-07-07 | 68.21 | 3.07% | 85.76亿 | 8.31% | 68.09 | 71.30 | 67.79 | 60.76 | 56.68 | 79.38 | 箱体中部 | 79.38 | 56.68 | 暂无显著自动量价信号 |
| 002185 | 华天科技 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 16:29:30 | 2026-07-07 | 21.93 | 9.98% | 119.99亿 | 16.93% | 20.70 | 21.37 | 19.74 | 16.55 | 16.01 | 23.86 | 箱体中部 | 23.86 | 16.01 | 放量上涨 |
| 603290 | 斯达半导 | 功率半导体/IGBT模块/AI电力运力上游 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 128.45 | 1.37% | 14.38亿 | 4.64% | 134.66 | 137.66 | 129.82 | 119.50 | 105.97 | 159.69 | 箱体中部 | 159.69 | 105.97 | 缩量上涨 |
| 000301 | 东方盛虹 | 石化化工/中报预增 | medium | 新浪实时行情接口 | 16:29:30 | 2026-07-07 | 12.43 | -9.99% | 11.34亿 | 1.34% | 12.59 | 12.06 | 12.03 | 12.26 | 10.80 | 13.89 | 箱体中部 | 13.89 | 10.80 | 缩量回调 |
| 002371 | 北方华创 | 半导体设备 | medium | 新浪实时行情接口 | 16:29:15 | 2026-07-07 | 806.39 | 0.35% | 105.62亿 | 1.81% | 840.63 | 832.94 | 757.13 | 626.08 | 594.59 | 968.00 | 箱体中部 | 968.00 | 594.59 | 缩量上涨 |
| 300821 | 东岳硅材 | 有机硅/周期化工/中报预增 | medium | 新浪实时行情接口 | 16:29:45 | 2026-07-07 | 23.30 | 5.81% | 42.22亿 | 15.10% | 21.68 | 20.68 | 19.67 | 16.63 | 15.61 | 24.95 | 接近箱体上沿 | 24.95 | 15.61 | 暂无显著自动量价信号 |
| 601872 | 招商轮船 | 航运/中报预增 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 16.20 | -8.37% | 26.39亿 | 1.96% | 16.86 | 18.32 | 17.44 | 17.45 | 13.91 | 22.16 | 箱体中部 | 22.16 | 13.91 | 缩量回调 |
| 603618 | 杭电股份 | 光纤光缆/光通信/中报预增 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 39.69 | -10.00% | 23.19亿 | 8.33% | 46.04 | 49.31 | 47.78 | 38.57 | 37.98 | 57.21 | 接近箱体下沿 | 57.21 | 37.98 | 缩量回调 |
| 688361 | 中科飞测 | 半导体设备/检测 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 356.60 | 3.96% | 40.30亿 | 3.27% | 363.92 | 362.52 | 299.75 | 232.70 | 194.50 | 458.98 | 箱体中部 | 458.98 | 194.50 | 缩量上涨 |
| 688596 | 正帆科技 | 半导体设备/材料 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-07 | 78.50 | 10.56% | 31.31亿 | 13.78% | 78.11 | 68.62 | 57.22 | 44.16 | 38.55 | 88.66 | 箱体中部 | 88.66 | 38.55 | 放量上涨 |

## 使用要求

1. 本文件是完整快照的紧凑版，优先用于 ChatGPT 快速确认均线、箱体、价格、涨跌幅、成交额、换手率等核心字段。
2. 如果需要封板资金、炸板次数、连板数、逐股异常提示等完整字段，再读取 report_data.md 或 report_data.json。
3. 若本文件生成时间不符合当前报告时点，视为旧缓存，不得采用。


<!-- COMPACT_SNAPSHOT_END -->
