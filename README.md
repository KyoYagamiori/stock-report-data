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

生成时间：2026-07-10T00:09:37+08:00
快照类型：早报前快照
适合报告：09:00 早报盘前基线
生成日期：2026-07-10
生成时间：中国时间 00:09
使用限制：优先读取实时/准实时口径；开盘前若实时接口仍返回上一交易日收盘状态，只能作为盘前基线。

## 数据质量

- 股票数量：22
- 实时/准实时可用股票数：22
- 均线字段可用股票数：22
- 箱体字段可用股票数：22
- 最新交易日集合：2026-07-09
- 实时/准实时行情时间集合：15:34:59, 15:35:00, 15:35:15, 15:35:30, 15:35:45, 15:36:00

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
- 长电科技 600584
- 浪潮信息 000977
- 通富微电 002156
- 华天科技 002185
- 明显放量上涨：
- 浪潮信息 000977
- 英维克 002837
- 胜宏科技 300476
- 寒武纪 688256
- 中芯国际 688981
- 通富微电 002156
- 明显放量下跌：
- 无
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

生成时间：2026-07-10T00:09:37+08:00
快照类型：早报前快照
适合报告：09:00 早报盘前基线
生成日期：2026-07-10
生成时间：中国时间 00:09

## 逐股紧凑字段

| code | name | theme | priority | source | quote_time | trade_date | price | pct | amount | turnover | ma5 | ma10 | ma20 | ma60 | box_lower | box_upper | box_position | breakout | pullback | signals |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| 600584 | 长电科技 | 先进封装/半导体封测 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 103.52 | 10.00% | 204.97亿 | 11.53% | 96.92 | 99.49 | 91.40 | 70.55 | 67.95 | 111.11 | 接近箱体上沿 | 111.11 | 67.95 | 缩量涨停，缩量强度：轻微缩量；缩量上涨 |
| 000938 | 紫光股份 | 算力网络/服务器 | high | 新浪实时行情接口 | 15:35:45 | 2026-07-09 | 35.68 | 6.13% | 149.96亿 | 15.23% | 32.87 | 30.41 | 28.67 | 29.43 | 25.03 | 35.75 | 接近箱体上沿 | 35.75 | 25.03 | 缩量上涨 |
| 000977 | 浪潮信息 | AI服务器/国产算力 | high | 新浪实时行情接口 | 15:35:30 | 2026-07-09 | 85.99 | 10.00% | 185.34亿 | 14.87% | 74.26 | 70.20 | 66.84 | 68.33 | 57.15 | 85.99 | 箱体上沿上方/突破区 | 85.99 | 57.15 | 放量上涨 |
| 001287 | 中电港 | 中报预增/AI硬件/数据中心/先进计算/存储涨价/电子元器件分销 | high | 新浪实时行情接口 | 15:35:45 | 2026-07-09 | 30.76 | 6.03% | 20.16亿 | 8.83% | 29.81 | 29.86 | 29.07 | 28.05 | 24.39 | 32.64 | 箱体中部 | 32.64 | 24.39 | 暂无显著自动量价信号 |
| 002837 | 英维克 | 液冷散热/机柜级液冷 | high | 新浪实时行情接口 | 15:36:00 | 2026-07-09 | 75.87 | 5.20% | 54.18亿 | 6.59% | 72.95 | 74.97 | 75.21 | 88.44 | 66.08 | 89.69 | 箱体中部 | 89.69 | 66.08 | 放量上涨 |
| 300308 | 中际旭创 | AI运力/光模块 | high | 新浪实时行情接口 | 15:35:30 | 2026-07-09 | 1194.90 | 5.90% | 416.09亿 | 3.23% | 1132.01 | 1177.01 | 1225.41 | 1072.23 | 1060.34 | 1416.88 | 箱体中部 | 1416.88 | 1060.34 | 暂无显著自动量价信号 |
| 300476 | 胜宏科技 | AI运力/高速PCB | high | 新浪实时行情接口 | 15:35:45 | 2026-07-09 | 296.70 | 6.09% | 109.41亿 | 4.41% | 292.42 | 307.64 | 327.85 | 337.80 | 277.01 | 375.80 | 接近箱体下沿 | 375.80 | 277.01 | 放量上涨 |
| 300502 | 新易盛 | AI运力/光模块 | high | 新浪实时行情接口 | 15:35:00 | 2026-07-09 | 545.50 | 6.79% | 261.01亿 | 3.92% | 519.87 | 541.38 | 548.65 | 596.24 | 490.10 | 618.87 | 箱体中部 | 618.87 | 490.10 | 暂无显著自动量价信号 |
| 301308 | 江波龙 | 存储芯片/端侧AI存储/中报业绩兑现 | high | 新浪实时行情接口 | 15:35:45 | 2026-07-09 | 620.00 | 4.60% | 123.47亿 | 7.16% | 628.09 | 651.40 | 613.60 | 527.76 | 498.00 | 749.88 | 箱体中部 | 749.88 | 498.00 | 暂无显著自动量价信号 |
| 603019 | 中科曙光 | 国产算力/AI服务器 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 103.99 | 5.95% | 125.53亿 | 8.52% | 96.58 | 98.34 | 92.74 | 92.03 | 80.51 | 109.60 | 接近箱体上沿 | 109.60 | 80.51 | 暂无显著自动量价信号 |
| 688256 | 寒武纪 | AI芯片 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 1535.01 | 8.59% | 245.79亿 | 2.63% | 1411.86 | 1445.22 | 1410.46 | 1365.90 | 1199.00 | 1620.00 | 箱体中部 | 1620.00 | 1199.00 | 放量上涨 |
| 688981 | 中芯国际 | 半导体制造 | high | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 173.00 | 13.74% | 236.46亿 | 7.23% | 150.96 | 151.20 | 144.80 | 129.92 | 123.01 | 174.51 | 接近箱体上沿 | 174.51 | 123.01 | 放量上涨 |
| 002156 | 通富微电 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 15:35:15 | 2026-07-09 | 72.17 | 10.00% | 113.39亿 | 10.76% | 67.39 | 69.83 | 68.38 | 61.56 | 56.68 | 79.38 | 箱体中部 | 79.38 | 56.68 | 放量上涨 |
| 002185 | 华天科技 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 15:35:30 | 2026-07-09 | 23.73 | 10.01% | 105.08亿 | 13.91% | 21.34 | 21.56 | 20.27 | 16.90 | 16.01 | 23.86 | 接近箱体上沿 | 23.86 | 16.01 | 缩量涨停，缩量强度：明显缩量；缩量上涨 |
| 603290 | 斯达半导 | 功率半导体/IGBT模块/AI电力运力上游 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 133.40 | 3.19% | 16.14亿 | 5.16% | 129.44 | 136.18 | 131.86 | 120.54 | 108.30 | 159.69 | 箱体中部 | 159.69 | 108.30 | 缩量上涨 |
| 000301 | 东方盛虹 | 石化化工/中报预增 | medium | 新浪实时行情接口 | 15:35:30 | 2026-07-09 | 12.48 | -2.65% | 7.24亿 | 0.90% | 12.82 | 12.24 | 12.13 | 12.30 | 10.80 | 13.89 | 箱体中部 | 13.89 | 10.80 | 缩量回调 |
| 002371 | 北方华创 | 半导体设备 | medium | 新浪实时行情接口 | 15:35:15 | 2026-07-09 | 878.43 | 9.49% | 133.39亿 | 2.19% | 821.35 | 844.20 | 779.35 | 638.27 | 620.00 | 968.00 | 箱体中部 | 968.00 | 620.00 | 暂无显著自动量价信号 |
| 300821 | 东岳硅材 | 有机硅/周期化工/中报预增 | medium | 新浪实时行情接口 | 15:35:45 | 2026-07-09 | 30.33 | 14.71% | 59.26亿 | 17.80% | 24.32 | 22.56 | 20.72 | 17.13 | 16.40 | 31.00 | 接近箱体上沿 | 31.00 | 16.40 | 暂无显著自动量价信号 |
| 601872 | 招商轮船 | 航运/中报预增 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 16.10 | 3.54% | 19.13亿 | 1.48% | 16.51 | 17.13 | 17.57 | 17.33 | 14.00 | 22.16 | 箱体中部 | 22.16 | 14.00 | 缩量上涨 |
| 603618 | 杭电股份 | 光纤光缆/光通信/中报预增 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 36.61 | 0.30% | 32.17亿 | 12.94% | 41.18 | 45.45 | 47.38 | 38.94 | 34.30 | 57.21 | 接近箱体下沿 | 57.21 | 34.30 | 暂无显著自动量价信号 |
| 688361 | 中科飞测 | 半导体设备/检测 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 446.50 | 9.44% | 58.76亿 | 3.99% | 379.22 | 383.53 | 322.16 | 241.25 | 204.62 | 458.98 | 接近箱体上沿 | 458.98 | 204.62 | 缩量上涨 |
| 688596 | 正帆科技 | 半导体设备/材料 | medium | 新浪实时行情接口 | 15:34:59 | 2026-07-09 | 80.33 | 6.14% | 29.47亿 | 13.10% | 76.58 | 74.78 | 60.45 | 45.75 | 43.00 | 88.66 | 接近箱体上沿 | 88.66 | 43.00 | 暂无显著自动量价信号 |

## 使用要求

1. 本文件是完整快照的紧凑版，优先用于 ChatGPT 快速确认均线、箱体、价格、涨跌幅、成交额、换手率等核心字段。
2. 如果需要封板资金、炸板次数、连板数、逐股异常提示等完整字段，再读取 report_data.md 或 report_data.json。
3. 若本文件生成时间不符合当前报告时点，视为旧缓存，不得采用。


<!-- COMPACT_SNAPSHOT_END -->
