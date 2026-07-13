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

生成时间：2026-07-13T12:23:13+08:00
快照类型：午报前快照
适合报告：11:45 午报上午盘核验
生成日期：2026-07-13
生成时间：中国时间 12:23
使用限制：优先读取实时/准实时口径；若实时口径不可用，回落到日线或已存快照并明确标注。

## 数据质量

- 股票数量：23
- 实时/准实时可用股票数：23
- 均线字段可用股票数：23
- 箱体字段可用股票数：23
- 最新交易日集合：2026-07-13
- 实时/准实时行情时间集合：11:30:00

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

- 东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。


<!-- SNAPSHOT_STATUS_END -->

---

<!-- COMPACT_SNAPSHOT_START -->

# 股票报告结构化行情紧凑快照

生成时间：2026-07-13T12:23:13+08:00
快照类型：午报前快照
适合报告：11:45 午报上午盘核验
生成日期：2026-07-13
生成时间：中国时间 12:23

## 逐股紧凑字段

| code | name | theme | priority | source | quote_time | trade_date | price | pct | amount | turnover | ma5 | ma10 | ma20 | ma60 | box_lower | box_upper | box_position | breakout | pullback | signals |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| 600584 | 长电科技 | 先进封装/半导体封测 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 102.03 | 0.91% | 162.92亿 | 17.09% | 98.96 | 99.51 | 92.86 | 71.52 | 67.95 | 113.87 | 箱体中部 | 113.87 | 67.95 | 缩量上涨 |
| 000938 | 紫光股份 | 算力网络/服务器 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 38.21 | -0.52% | 125.21亿 | 16.88% | 34.50 | 31.68 | 29.32 | 29.60 | 25.12 | 39.25 | 接近箱体上沿 | 39.25 | 25.12 | 缩量回调 |
| 000977 | 浪潮信息 | AI服务器/国产算力 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 85.32 | -4.69% | 105.66亿 | 19.37% | 78.89 | 72.77 | 68.43 | 68.68 | 57.73 | 94.38 | 箱体中部 | 94.38 | 57.73 | 缩量回调 |
| 001287 | 中电港 | 中报预增/AI硬件/数据中心/先进计算/存储涨价/电子元器件分销 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 29.07 | -6.32% | 10.79亿 | 10.05% | 30.29 | 29.96 | 29.35 | 28.11 | 24.39 | 32.64 | 箱体中部 | 32.64 | 24.39 | 缩量回调 |
| 002837 | 英维克 | 液冷散热/机柜级液冷 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 68.56 | -6.77% | 26.65亿 | 6.37% | 73.38 | 74.07 | 75.53 | 87.95 | 66.08 | 89.69 | 接近箱体下沿 | 89.69 | 66.08 | 缩量回调 |
| 300308 | 中际旭创 | AI运力/光模块 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 1101.27 | 0.67% | 247.49亿 | 3.81% | 1127.61 | 1161.02 | 1223.91 | 1078.17 | 1060.34 | 1416.88 | 接近箱体下沿 | 1416.88 | 1060.34 | 缩量上涨 |
| 300476 | 胜宏科技 | AI运力/高速PCB | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 275.06 | 1.12% | 68.47亿 | 5.70% | 285.21 | 302.89 | 325.17 | 337.37 | 271.72 | 375.80 | 接近箱体下沿 | 375.80 | 271.72 | 缩量上涨 |
| 300502 | 新易盛 | AI运力/光模块 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 511.47 | -2.21% | 130.95亿 | 4.07% | 519.28 | 537.09 | 548.50 | 596.41 | 490.10 | 618.87 | 接近箱体下沿 | 618.87 | 490.10 | 缩量回调 |
| 301308 | 江波龙 | 存储芯片/端侧AI存储/中报业绩兑现 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 539.58 | -8.17% | 55.24亿 | 6.83% | 622.00 | 642.20 | 617.24 | 531.64 | 501.28 | 749.88 | 接近箱体下沿 | 749.88 | 501.28 | 缩量回调 |
| 603019 | 中科曙光 | 国产算力/AI服务器 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 106.46 | -0.97% | 90.37亿 | 10.93% | 99.54 | 99.21 | 94.05 | 92.34 | 82.00 | 113.00 | 箱体中部 | 113.00 | 82.00 | 缩量回调 |
| 688256 | 寒武纪 | AI芯片 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 1411.80 | 0.84% | 147.40亿 | 2.10% | 1421.26 | 1439.42 | 1419.48 | 1368.91 | 1202.00 | 1620.00 | 箱体中部 | 1620.00 | 1202.00 | 缩量上涨 |
| 688820 | 盛合晶微 | 先进封装/Chiplet/2.5D/3DIC | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 194.57 | 1.36% | 32.53亿 | 21.97% | 195.33 | 190.27 | 189.38 | 暂无 | 155.00 | 222.22 | 箱体中部 | 222.22 | 155.00 | 缩量上涨 |
| 688981 | 中芯国际 | 半导体制造 | high | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 165.30 | 1.40% | 120.57亿 | 5.64% | 155.51 | 152.62 | 146.58 | 130.96 | 124.37 | 176.34 | 箱体中部 | 176.34 | 124.37 | 缩量上涨 |
| 002156 | 通富微电 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 74.30 | 4.72% | 110.84亿 | 13.35% | 68.62 | 69.77 | 68.93 | 61.98 | 56.68 | 79.38 | 箱体中部 | 79.38 | 56.68 | 缩量上涨 |
| 002185 | 华天科技 | 先进封装/半导体封测 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 25.21 | -0.40% | 144.01亿 | 14.89% | 22.50 | 21.84 | 20.70 | 17.12 | 16.01 | 26.10 | 接近箱体上沿 | 26.10 | 16.01 | 暂无显著自动量价信号 |
| 603290 | 斯达半导 | 功率半导体/IGBT模块/AI电力运力上游 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 120.00 | -3.08% | 7.77亿 | 6.79% | 128.33 | 135.18 | 132.48 | 120.93 | 108.33 | 159.69 | 箱体中部 | 159.69 | 108.33 | 缩量回调 |
| 000301 | 东方盛虹 | 石化化工/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 11.64 | -7.25% | 3.19亿 | 0.69% | 12.82 | 12.35 | 12.17 | 12.32 | 10.80 | 13.89 | 箱体中部 | 13.89 | 10.80 | 缩量回调 |
| 002371 | 北方华创 | 半导体设备 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 780.40 | -2.57% | 70.34亿 | 2.67% | 818.35 | 842.97 | 787.52 | 643.74 | 640.00 | 968.00 | 箱体中部 | 968.00 | 640.00 | 缩量回调 |
| 300821 | 东岳硅材 | 有机硅/周期化工/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 22.56 | -16.32% | 31.02亿 | 18.39% | 25.81 | 23.24 | 21.18 | 17.34 | 16.40 | 31.00 | 箱体中部 | 31.00 | 16.40 | 缩量回调 |
| 601872 | 招商轮船 | 航运/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 14.99 | -3.10% | 8.96亿 | 1.18% | 16.20 | 16.72 | 17.62 | 17.29 | 14.77 | 22.16 | 接近箱体下沿 | 22.16 | 14.77 | 缩量回调 |
| 603618 | 杭电股份 | 光纤光缆/光通信/中报预增 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 31.69 | -10.00% | 16.85亿 | 7.39% | 35.94 | 42.01 | 46.71 | 39.30 | 31.69 | 57.21 | 箱体下沿下方/破位区 | 57.21 | 31.69 | 缩量回调 |
| 688361 | 中科飞测 | 半导体设备/检测 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 396.74 | -6.15% | 32.29亿 | 2.24% | 406.12 | 392.36 | 341.18 | 249.19 | 220.31 | 458.98 | 箱体中部 | 458.98 | 220.31 | 缩量回调 |
| 688596 | 正帆科技 | 半导体设备/材料 | medium | 新浪实时行情接口 | 11:30:00 | 2026-07-13 | 65.79 | -3.29% | 14.54亿 | 14.38% | 74.71 | 75.96 | 61.48 | 46.38 | 43.00 | 88.66 | 箱体中部 | 88.66 | 43.00 | 缩量回调 |

## 使用要求

1. 本文件是完整快照的紧凑版，优先用于 ChatGPT 快速确认均线、箱体、价格、涨跌幅、成交额、换手率等核心字段。
2. 如果需要封板资金、炸板次数、连板数、逐股异常提示等完整字段，再读取 report_data.md 或 report_data.json。
3. 若本文件生成时间不符合当前报告时点，视为旧缓存，不得采用。


<!-- COMPACT_SNAPSHOT_END -->
