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

生成时间：2026-07-09T12:40:37+08:00
快照类型：收盘后快照
适合报告：晚报收盘核验
生成日期：2026-07-09
生成时间：中国时间 12:40
使用限制：优先读取实时/准实时口径，通常可用于收盘量价核验；仍需联网核验新闻、公告和盘后事件。

## 数据质量

- 股票数量：22
- 实时/准实时可用股票数：22
- 均线字段可用股票数：22
- 箱体字段可用股票数：22
- 最新交易日集合：2026-07-09
- 实时/准实时行情时间集合：11:30:00

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
- 浪潮信息 000977
- 华天科技 002185
- 明显放量上涨：
- 浪潮信息 000977
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

- 东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。


<!-- SNAPSHOT_STATUS_END -->

---

<!-- COMPACT_SNAPSHOT_START -->

# 股票报告结构化行情紧凑快照

生成时间：2026-07-09T12:40:37+08:00
快照类型：收盘后快照
适合报告：晚报收盘核验
生成日期：2026-07-09
生成时间：中国时间 12:40

## 逐股紧凑字段

| code | name | theme | priority | source | quote_time | trade_date | price | pct | amount | turnover | ma5 | ma10 | ma20 | ma60 | box_lower | box_upper | box_position | breakout | pullback | signals |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| 600584 | 长电科技 | 先进封装/半导体封测 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 101.66 | 8.02% | 160.86亿 | 11.58% | 95.41 | 99.56 | 89.93 | 69.54 | 67.95 | 111.11 | 箱体中部 | 111.11 | 67.95 | 缩量上涨 |
| 000938 | 紫光股份 | 算力网络/服务器 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 35.14 | 4.52% | 109.69亿 | 16.78% | 31.54 | 29.68 | 28.18 | 29.29 | 25.03 | 34.63 | 箱体上沿上方/突破区 | 34.63 | 25.03 | 暂无显著自动量价信号 |
| 000977 | 浪潮信息 | AI服务器/国产算力 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 85.99 | 10.00% | 181.90亿 | 2.78% | 69.82 | 68.46 | 65.51 | 68.02 | 57.15 | 78.17 | 箱体上沿上方/突破区 | 78.17 | 57.15 | 放量上涨 |
| 001287 | 中电港 | 中报预增/AI硬件/数据中心/先进计算/存储涨价/电子元器件分销 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 29.82 | 2.79% | 10.86亿 | 6.97% | 29.38 | 29.89 | 28.84 | 27.97 | 24.39 | 32.64 | 箱体中部 | 32.64 | 24.39 | 缩量上涨 |
| 002837 | 英维克 | 液冷散热/机柜级液冷 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 71.03 | -1.51% | 28.63亿 | 4.81% | 72.06 | 76.09 | 74.87 | 88.83 | 66.08 | 89.69 | 箱体中部 | 89.69 | 66.08 | 缩量回调 |
| 300308 | 中际旭创 | AI运力/光模块 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 1146.00 | 1.56% | 200.29亿 | 2.86% | 1121.63 | 1189.86 | 1223.01 | 1064.56 | 1060.34 | 1416.88 | 箱体中部 | 1416.88 | 1060.34 | 缩量上涨 |
| 300476 | 胜宏科技 | AI运力/高速PCB | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 280.00 | 0.12% | 52.77亿 | 2.80% | 294.30 | 312.99 | 329.53 | 337.69 | 277.01 | 375.80 | 接近箱体下沿 | 375.80 | 277.01 | 缩量上涨 |
| 300502 | 新易盛 | AI运力/光模块 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 520.96 | 1.98% | 111.22亿 | 3.55% | 512.57 | 547.88 | 560.00 | 595.85 | 490.10 | 799.75 | 接近箱体下沿 | 799.75 | 490.10 | 缩量上涨 |
| 301308 | 江波龙 | 存储芯片/端侧AI存储/中报业绩兑现 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 600.99 | 1.40% | 65.40亿 | 5.93% | 623.93 | 657.13 | 607.95 | 523.11 | 498.00 | 749.88 | 箱体中部 | 749.88 | 498.00 | 缩量上涨 |
| 603019 | 中科曙光 | 国产算力/AI服务器 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 101.09 | 3.00% | 74.44亿 | 8.24% | 94.69 | 97.72 | 91.68 | 91.72 | 80.51 | 109.60 | 箱体中部 | 109.60 | 80.51 | 暂无显著自动量价信号 |
| 688256 | 寒武纪 | AI芯片 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 1498.65 | 6.02% | 172.20亿 | 1.87% | 1379.26 | 1442.22 | 1395.26 | 1360.50 | 1199.00 | 1620.00 | 箱体中部 | 1620.00 | 1199.00 | 缩量上涨 |
| 688981 | 中芯国际 | 半导体制造 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 161.99 | 6.50% | 121.69亿 | 5.00% | 145.18 | 149.58 | 142.42 | 128.72 | 123.01 | 166.88 | 接近箱体上沿 | 166.88 | 123.01 | 暂无显著自动量价信号 |
| 002156 | 通富微电 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 69.00 | 5.17% | 61.46亿 | 7.54% | 66.43 | 70.39 | 67.85 | 61.11 | 56.68 | 79.38 | 箱体中部 | 79.38 | 56.68 | 缩量上涨 |
| 002185 | 华天科技 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 23.73 | 10.01% | 101.87亿 | 20.21% | 20.64 | 21.43 | 19.94 | 16.71 | 16.01 | 23.86 | 接近箱体上沿 | 23.86 | 16.01 | 缩量涨停，缩量强度：正常缩量；缩量上涨 |
| 603290 | 斯达半导 | 功率半导体/IGBT模块/AI电力运力上游 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 128.71 | -0.44% | 7.87亿 | 5.82% | 130.14 | 136.66 | 130.69 | 119.99 | 107.60 | 159.69 | 箱体中部 | 159.69 | 107.60 | 缩量回调 |
| 000301 | 东方盛虹 | 石化化工/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 11.89 | -7.25% | 4.93亿 | 0.99% | 12.75 | 12.14 | 12.09 | 12.28 | 10.80 | 13.89 | 箱体中部 | 13.89 | 10.80 | 缩量回调 |
| 002371 | 北方华创 | 半导体设备 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 826.19 | 2.98% | 65.59亿 | 2.04% | 814.03 | 836.16 | 766.39 | 631.57 | 610.00 | 968.00 | 箱体中部 | 968.00 | 610.00 | 缩量上涨 |
| 300821 | 东岳硅材 | 有机硅/周期化工/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 28.94 | 9.46% | 44.13亿 | 15.88% | 22.54 | 21.38 | 20.11 | 16.85 | 16.40 | 27.30 | 箱体上沿上方/突破区 | 27.30 | 16.40 | 缩量上涨 |
| 601872 | 招商轮船 | 航运/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 15.71 | 1.03% | 12.76亿 | 1.71% | 16.59 | 17.68 | 17.50 | 17.38 | 14.00 | 22.16 | 箱体中部 | 22.16 | 14.00 | 缩量上涨 |
| 603618 | 杭电股份 | 光纤光缆/光通信/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 34.74 | -4.82% | 19.81亿 | 12.29% | 43.38 | 47.51 | 47.55 | 38.74 | 36.50 | 57.21 | 箱体下沿下方/破位区 | 57.21 | 36.50 | 缩量回调 |
| 688361 | 中科飞测 | 半导体设备/检测 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 407.90 | -0.03% | 31.63亿 | 4.09% | 361.12 | 372.08 | 310.00 | 236.65 | 200.26 | 458.98 | 接近箱体上沿 | 458.98 | 200.26 | 缩量回调 |
| 688596 | 正帆科技 | 半导体设备/材料 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-09 | 76.04 | 0.48% | 16.59亿 | 10.78% | 76.51 | 71.43 | 58.73 | 44.92 | 43.00 | 88.66 | 箱体中部 | 88.66 | 43.00 | 缩量上涨 |

## 使用要求

1. 本文件是完整快照的紧凑版，优先用于 ChatGPT 快速确认均线、箱体、价格、涨跌幅、成交额、换手率等核心字段。
2. 如果需要封板资金、炸板次数、连板数、逐股异常提示等完整字段，再读取 report_data.md 或 report_data.json。
3. 若本文件生成时间不符合当前报告时点，视为旧缓存，不得采用。


<!-- COMPACT_SNAPSHOT_END -->
