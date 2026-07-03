# Stock Report Data

This public mirror only contains sanitized structured market snapshots for GPT report generation.

## Latest Snapshot For ChatGPT

If ChatGPT cannot fetch Raw/CDN/Jina file links, read this repository homepage. The latest public snapshot is embedded below as normal Markdown.

Snapshot file links:

- https://github.com/KyoYagamiori/stock-report-data
- https://cdn.jsdelivr.net/gh/KyoYagamiori/stock-report-data@main/output/latest/report_data.md
- https://cdn.statically.io/gh/KyoYagamiori/stock-report-data/main/output/latest/report_data.md
- https://raw.githubusercontent.com/KyoYagamiori/stock-report-data/refs/heads/main/output/latest/report_data.md

Use this mirror only for structured market snapshot verification. Previous report context should come from the same ChatGPT task/report thread via the `供下一篇读取的生产线摘要` block, not from this public mirror.

The private research repository, historical report text, prompts, portfolio details, and execution records are not mirrored here.

---

<!-- SNAPSHOT_START -->

# 股票报告结构化行情公开快照

生成时间：2026-07-03T15:26:52+08:00
数据用途：供 ChatGPT 股票早报、午报、晚报生产线匿名读取，用于核验观察池股票的结构化行情数据；优先使用实时/准实时行情口径。
数据源说明：A 股实时/准实时行情、日线、涨停股池和个股行业信息来自 AKShare 对公开行情数据接口的封装。
隐私说明：本公开快照仅包含行情字段，已移除个人化交易信息和内部观察原因字段。
风险说明：本快照只提供数据核验，不构成买卖建议；若字段缺失，报告生产线不得编造。

## 快照适用状态

- 快照类型：收盘后快照
- 适合报告：晚报收盘核验
- 生成日期：2026-07-03
- 生成时间：中国时间 15:26
- 行情口径优先级：实时/准实时行情优先；日线数据次之；上一份已存快照最后兜底。
- 使用限制：优先读取实时/准实时口径，通常可用于收盘量价核验；仍需联网核验新闻、公告和盘后事件。
- 使用规则：
- 先校验快照生成时间、快照类型、适合报告和生成日期，再读取逐股实时/准实时字段。
- 逐股字段读取顺序：行情主口径、实时/准实时行情可用、实时/准实时数据来源、实时/准实时行情时间、最新交易日/推定日期、最新价、涨跌幅、成交量、成交额、换手率、涨停池、封板资金、炸板次数，最后才看日线备份和已存快照备份。
- 实时/准实时行情可用=是，只说明本快照生成时使用了实时接口；若快照生成时间或类型不适合当前报告时点，不得把它当作当前实时数据。
- 早报可把上一交易日实时/收盘口径作为盘前基线；午报必须校验当天11:30后快照或逐股行情时间；晚报必须校验当天15:00后逐股行情时间或收盘后/晚报前快照。
- 快照不满足当前时点时，报告必须写结构化快照未通过实时性校验，并改用联网实时行情兜底或降低盘面确认分。
- 公开快照只用于结构化行情核验，不替代联网新闻、公告、政策和产业动态搜索。

## 数据更新提示

- 东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。
- 行业信息获取失败：Length mismatch: Expected axis has 3 elements, new values have 2 elements 已使用观察池 theme 作为行业/主题兜底。

## 一、观察池状态

- 当前 active 股票数量：16
- 当前 high priority 股票：
- 长电科技 600584
- 浪潮信息 000977
- 北方华创 002371
- 英维克 002837
- 中际旭创 300308
- 胜宏科技 300476
- 新易盛 300502
- 中科曙光 603019
- 寒武纪 688256
- 中芯国际 688981
- 本次新增股票：
- 无
- 本次降级股票：
- 无
- 本次 inactive 股票：
- 无
- 本次被跳过的固定观察删除请求：
- 无

## 二、重点结论摘要

- 今日进入涨停股池的观察股：
- 无
- 今日构成缩量涨停的观察股：
- 无
- 今日明显放量上涨的观察股：
- 无
- 今日明显放量下跌的观察股：
- 无
- 今日数据缺失或接口异常的股票：
- 无
- 下一份报告需要重点核验的股票：
- 长电科技 600584
- 浪潮信息 000977
- 北方华创 002371
- 英维克 002837
- 中际旭创 300308
- 胜宏科技 300476
- 新易盛 300502
- 中科曙光 603019
- 寒武纪 688256
- 中芯国际 688981
- 通富微电 002156
- 华天科技 002185
- 斯达半导 603290

## 三、逐只股票数据

### 长电科技 600584

- 主题：先进封装/半导体封测
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:02
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：90.88
- 最新涨跌幅：-5.31%
- 最新成交量：178.23万手
- 昨日交易日：2026-07-01
- 昨日成交量：245.98万手
- 较昨日缩量/放量比例：-27.54%（正常缩量）
- 最新成交额：164.08亿元
- 昨日成交额：263.27亿元
- 最新换手率：10.66%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 111.11
- box_lower / box bottom: 67.95
- box_mid: 89.53
- box_position: 53.13% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 111.11
- box_pullback_watch_price / pullback buy watch: 67.95
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 102.06; price_vs_ma5: -10.96% (below)
- ma10 / 10-day MA: 96.96; price_vs_ma10: -6.27% (below)
- ma20 / 20-day MA: 85.94; price_vs_ma20: 5.74% (above)
- ma60 / 60-day MA: 65.87; price_vs_ma60: 37.97% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_above_ma20_trend_repair
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：先进封装/半导体封测
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 浪潮信息 000977

- 主题：AI服务器/国产算力
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:00
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：66.35
- 最新涨跌幅：4.01%
- 最新成交量：98.84万手
- 昨日交易日：2026-07-01
- 昨日成交量：96.60万手
- 较昨日缩量/放量比例：2.32%（未缩量）
- 最新成交额：66.06亿元
- 昨日成交额：66.61亿元
- 最新换手率：4.94%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 71.87
- box_lower / box bottom: 57.15
- box_mid: 64.51
- box_position: 62.50% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 71.87
- box_pullback_watch_price / pullback buy watch: 57.15
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 66.15; price_vs_ma5: 0.30% (above)
- ma10 / 10-day MA: 66.00; price_vs_ma10: 0.53% (above)
- ma20 / 20-day MA: 63.39; price_vs_ma20: 4.67% (above)
- ma60 / 60-day MA: 67.33; price_vs_ma60: -1.46% (below)
- ma_alignment: mixed_or_converging
- ma_trend_signal: price_above_ma5_ma10_ma20_short_term_strong
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：AI服务器/国产算力
- 自动量价判定：暂无显著自动量价信号
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 北方华创 002371

- 主题：半导体设备
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:00
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：816.00
- 最新涨跌幅：-2.98%
- 最新成交量：16.59万手
- 昨日交易日：2026-07-01
- 昨日成交量：14.61万手
- 较昨日缩量/放量比例：13.51%（未缩量）
- 最新成交额：134.59亿元
- 昨日成交额：136.02亿元
- 最新换手率：1.67%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 968.00
- box_lower / box bottom: 568.22
- box_mid: 768.11
- box_position: 61.98% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 968.00
- box_pullback_watch_price / pullback buy watch: 568.22
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 867.06; price_vs_ma5: -5.89% (below)
- ma10 / 10-day MA: 811.69; price_vs_ma10: 0.53% (above)
- ma20 / 20-day MA: 726.63; price_vs_ma20: 12.30% (above)
- ma60 / 60-day MA: 607.56; price_vs_ma60: 34.31% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_above_ma20_trend_repair
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：半导体设备
- 自动量价判定：暂无显著自动量价信号
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 英维克 002837

- 主题：液冷散热/机柜级液冷
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:00
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：71.43
- 最新涨跌幅：0.04%
- 最新成交量：43.28万手
- 昨日交易日：2026-07-01
- 昨日成交量：63.33万手
- 较昨日缩量/放量比例：-31.65%（明显缩量）
- 最新成交额：31.41亿元
- 昨日成交额：48.55亿元
- 最新换手率：4.64%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 89.69
- box_lower / box bottom: 62.20
- box_mid: 75.94
- box_position: 33.58% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 89.69
- box_pullback_watch_price / pullback buy watch: 62.20
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 76.99; price_vs_ma5: -7.22% (below)
- ma10 / 10-day MA: 78.80; price_vs_ma10: -9.35% (below)
- ma20 / 20-day MA: 73.83; price_vs_ma20: -3.25% (below)
- ma60 / 60-day MA: 89.90; price_vs_ma60: -20.54% (below)
- ma_alignment: mixed_or_converging
- ma_trend_signal: price_below_ma20_trend_pressure
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：液冷散热/机柜级液冷
- 自动量价判定：缩量上涨
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 中际旭创 300308

- 主题：AI运力/光模块
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:27:15
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：1116.00
- 最新涨跌幅：-2.36%
- 最新成交量：32.86万手
- 昨日交易日：2026-07-01
- 昨日成交量：27.16万手
- 较昨日缩量/放量比例：21.01%（未缩量）
- 最新成交额：377.02亿元
- 昨日成交额：342.56亿元
- 最新换手率：2.86%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 1416.88
- box_lower / box bottom: 1093.00
- box_mid: 1254.94
- box_position: 7.10% (接近箱体下沿)
- box_breakout_watch_price / breakout buy watch: 1416.88
- box_pullback_watch_price / pullback buy watch: 1093.00
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 1222.01; price_vs_ma5: -8.68% (below)
- ma10 / 10-day MA: 1280.59; price_vs_ma10: -12.85% (below)
- ma20 / 20-day MA: 1239.50; price_vs_ma20: -9.96% (below)
- ma60 / 60-day MA: 1033.60; price_vs_ma60: 7.97% (above)
- ma_alignment: mixed_or_converging
- ma_trend_signal: price_below_ma20_trend_pressure
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：AI运力/光模块
- 自动量价判定：暂无显著自动量价信号
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 胜宏科技 300476

- 主题：AI运力/高速PCB
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:27:15
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：308.07
- 最新涨跌幅：0.65%
- 最新成交量：33.06万手
- 昨日交易日：2026-07-01
- 昨日成交量：43.79万手
- 较昨日缩量/放量比例：-24.49%（正常缩量）
- 最新成交额：101.97亿元
- 昨日成交额：148.38亿元
- 最新换手率：4.49%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 375.80
- box_lower / box bottom: 303.75
- box_mid: 339.77
- box_position: 6.00% (接近箱体下沿)
- box_breakout_watch_price / breakout buy watch: 375.80
- box_pullback_watch_price / pullback buy watch: 303.75
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 322.86; price_vs_ma5: -4.58% (below)
- ma10 / 10-day MA: 338.05; price_vs_ma10: -8.87% (below)
- ma20 / 20-day MA: 339.40; price_vs_ma20: -9.23% (below)
- ma60 / 60-day MA: 336.47; price_vs_ma60: -8.44% (below)
- ma_alignment: mixed_or_converging
- ma_trend_signal: price_below_ma20_trend_pressure
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：AI运力/高速PCB
- 自动量价判定：缩量上涨
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Length mismatch: Expected axis has 3 elements, new values have 2 elements 已使用观察池 theme 作为行业/主题兜底。

### 新易盛 300502

- 主题：AI运力/光模块
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:27:00
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：526.00
- 最新涨跌幅：3.34%
- 最新成交量：53.45万手
- 昨日交易日：2026-07-01
- 昨日成交量：47.62万手
- 较昨日缩量/放量比例：12.24%（未缩量）
- 最新成交额：284.33亿元
- 昨日成交额：282.57亿元
- 最新换手率：5.55%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 818.38
- box_lower / box bottom: 490.13
- box_mid: 654.25
- box_position: 10.93% (接近箱体下沿)
- box_breakout_watch_price / breakout buy watch: 818.38
- box_pullback_watch_price / pullback buy watch: 490.13
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 562.90; price_vs_ma5: -6.56% (below)
- ma10 / 10-day MA: 569.38; price_vs_ma10: -7.62% (below)
- ma20 / 20-day MA: 609.04; price_vs_ma20: -13.63% (below)
- ma60 / 60-day MA: 593.38; price_vs_ma60: -11.36% (below)
- ma_alignment: mixed_or_converging
- ma_trend_signal: price_below_ma20_trend_pressure
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：AI运力/光模块
- 自动量价判定：暂无显著自动量价信号
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 中科曙光 603019

- 主题：国产算力/AI服务器
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:02
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：92.68
- 最新涨跌幅：-1.99%
- 最新成交量：79.01万手
- 昨日交易日：2026-07-01
- 昨日成交量：142.47万手
- 较昨日缩量/放量比例：-44.54%（明显缩量）
- 最新成交额：74.60亿元
- 昨日成交额：149.85亿元
- 最新换手率：6.43%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 109.60
- box_lower / box bottom: 77.77
- box_mid: 93.69
- box_position: 46.84% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 109.60
- box_pullback_watch_price / pullback buy watch: 77.77
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 100.10; price_vs_ma5: -7.41% (below)
- ma10 / 10-day MA: 95.20; price_vs_ma10: -2.65% (below)
- ma20 / 20-day MA: 89.02; price_vs_ma20: 4.12% (above)
- ma60 / 60-day MA: 90.77; price_vs_ma60: 2.10% (above)
- ma_alignment: mixed_or_converging
- ma_trend_signal: price_above_ma20_trend_repair
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：国产算力/AI服务器
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 寒武纪 688256

- 主题：AI芯片
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:27:06
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：1353.00
- 最新涨跌幅：-1.39%
- 最新成交量：10.19万手
- 昨日交易日：2026-07-01
- 昨日成交量：12.58万手
- 较昨日缩量/放量比例：-18.98%（正常缩量）
- 最新成交额：140.22亿元
- 昨日成交额：191.80亿元
- 最新换手率：2.24%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 1620.00
- box_lower / box bottom: 1199.00
- box_mid: 1409.50
- box_position: 36.58% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 1620.00
- box_pullback_watch_price / pullback buy watch: 1199.00
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 1478.58; price_vs_ma5: -8.49% (below)
- ma10 / 10-day MA: 1472.83; price_vs_ma10: -8.14% (below)
- ma20 / 20-day MA: 1377.96; price_vs_ma20: -1.81% (below)
- ma60 / 60-day MA: 1343.54; price_vs_ma60: 0.70% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_below_ma20_trend_pressure
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：AI芯片
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 中芯国际 688981

- 主题：半导体制造
- 优先级：high
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:27:06
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：140.31
- 最新涨跌幅：-2.63%
- 最新成交量：77.04万手
- 昨日交易日：2026-07-01
- 昨日成交量：114.68万手
- 较昨日缩量/放量比例：-32.82%（明显缩量）
- 最新成交额：110.12亿元
- 昨日成交额：183.28亿元
- 最新换手率：4.75%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 166.88
- box_lower / box bottom: 120.00
- box_mid: 143.44
- box_position: 43.32% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 166.88
- box_pullback_watch_price / pullback buy watch: 120.00
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 151.43; price_vs_ma5: -7.34% (below)
- ma10 / 10-day MA: 149.35; price_vs_ma10: -6.06% (below)
- ma20 / 20-day MA: 138.90; price_vs_ma20: 1.01% (above)
- ma60 / 60-day MA: 125.49; price_vs_ma60: 11.81% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_above_ma20_trend_repair
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：半导体制造
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 通富微电 002156

- 主题：先进封装/半导体封测
- 优先级：medium
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:00
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：64.80
- 最新涨跌幅：-3.81%
- 最新成交量：104.18万手
- 昨日交易日：2026-07-01
- 昨日成交量：158.05万手
- 较昨日缩量/放量比例：-34.08%（明显缩量）
- 最新成交额：68.63亿元
- 昨日成交额：119.42亿元
- 最新换手率：8.99%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 79.38
- box_lower / box bottom: 56.68
- box_mid: 68.03
- box_position: 35.77% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 79.38
- box_pullback_watch_price / pullback buy watch: 56.68
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 72.27; price_vs_ma5: -10.33% (below)
- ma10 / 10-day MA: 72.17; price_vs_ma10: -10.21% (below)
- ma20 / 20-day MA: 67.84; price_vs_ma20: -4.48% (below)
- ma60 / 60-day MA: 59.54; price_vs_ma60: 8.83% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_below_ma20_trend_pressure
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：先进封装/半导体封测
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 华天科技 002185

- 主题：先进封装/半导体封测
- 优先级：medium
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:00
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：19.51
- 最新涨跌幅：-3.75%
- 最新成交量：323.59万手
- 昨日交易日：2026-07-01
- 昨日成交量：526.78万手
- 较昨日缩量/放量比例：-38.57%（明显缩量）
- 最新成交额：64.44亿元
- 昨日成交额：118.65亿元
- 最新换手率：12.90%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 23.86
- box_lower / box bottom: 16.01
- box_mid: 19.94
- box_position: 44.59% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 23.86
- box_pullback_watch_price / pullback buy watch: 16.01
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 21.78; price_vs_ma5: -10.44% (below)
- ma10 / 10-day MA: 21.19; price_vs_ma10: -7.92% (below)
- ma20 / 20-day MA: 19.38; price_vs_ma20: 0.67% (above)
- ma60 / 60-day MA: 16.11; price_vs_ma60: 21.07% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_above_ma20_trend_repair
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：先进封装/半导体封测
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 斯达半导 603290

- 主题：功率半导体/IGBT模块/AI电力运力上游
- 优先级：medium
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:02
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：129.35
- 最新涨跌幅：-5.51%
- 最新成交量：12.55万手
- 昨日交易日：2026-07-01
- 昨日成交量：22.21万手
- 较昨日缩量/放量比例：-43.48%（明显缩量）
- 最新成交额：16.62亿元
- 昨日成交额：34.44亿元
- 最新换手率：7.51%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 159.69
- box_lower / box bottom: 105.97
- box_mid: 132.83
- box_position: 43.52% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 159.69
- box_pullback_watch_price / pullback buy watch: 105.97
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 142.92; price_vs_ma5: -9.50% (below)
- ma10 / 10-day MA: 139.73; price_vs_ma10: -7.43% (below)
- ma20 / 20-day MA: 127.64; price_vs_ma20: 1.34% (above)
- ma60 / 60-day MA: 118.04; price_vs_ma60: 9.59% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_above_ma20_trend_repair
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：功率半导体/IGBT模块/AI电力运力上游
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 紫光股份 000938

- 主题：算力网络/服务器
- 优先级：medium
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:00:00
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：30.28
- 最新涨跌幅：4.31%
- 最新成交量：246.18万手
- 昨日交易日：2026-07-01
- 昨日成交量：339.21万手
- 较昨日缩量/放量比例：-27.42%（正常缩量）
- 最新成交额：75.84亿元
- 昨日成交额：103.12亿元
- 最新换手率：7.60%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 31.29
- box_lower / box bottom: 25.03
- box_mid: 28.16
- box_position: 83.87% (接近箱体上沿)
- box_breakout_watch_price / breakout buy watch: 31.29
- box_pullback_watch_price / pullback buy watch: 25.03
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 27.94; price_vs_ma5: 8.39% (above)
- ma10 / 10-day MA: 27.80; price_vs_ma10: 8.93% (above)
- ma20 / 20-day MA: 27.14; price_vs_ma20: 11.58% (above)
- ma60 / 60-day MA: 28.88; price_vs_ma60: 4.85% (above)
- ma_alignment: mixed_or_converging
- ma_trend_signal: price_above_ma5_ma10_ma20_short_term_strong
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：算力网络/服务器
- 自动量价判定：缩量上涨
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 中科飞测 688361

- 主题：半导体设备/检测
- 优先级：medium
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:27:06
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：342.00
- 最新涨跌幅：-3.93%
- 最新成交量：15.85万手
- 昨日交易日：2026-07-01
- 昨日成交量：13.67万手
- 较昨日缩量/放量比例：15.92%（未缩量）
- 最新成交额：54.42亿元
- 昨日成交额：59.40亿元
- 最新换手率：5.70%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 458.98
- box_lower / box bottom: 188.00
- box_mid: 323.49
- box_position: 56.83% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 458.98
- box_pullback_watch_price / pullback buy watch: 188.00
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 387.85; price_vs_ma5: -11.82% (below)
- ma10 / 10-day MA: 338.03; price_vs_ma10: 1.18% (above)
- ma20 / 20-day MA: 277.82; price_vs_ma20: 23.10% (above)
- ma60 / 60-day MA: 223.15; price_vs_ma60: 53.26% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_above_ma20_trend_repair
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：半导体设备/检测
- 自动量价判定：暂无显著自动量价信号
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

### 正帆科技 688596

- 主题：半导体设备/材料
- 优先级：medium
- 状态：active
- 行情主口径：新浪实时行情接口
- 实时/准实时行情可用：是
- 实时/准实时数据来源：新浪实时行情接口
- 实时/准实时行情时间：15:27:03
- 已存快照备份：未使用
- 日线备份来源：新浪备用日线接口
- 日线最新交易日：2026-07-02
- 最新交易日/推定日期：2026-07-03
- 最新价/收盘价：77.41
- 最新涨跌幅：-3.20%
- 最新成交量：37.67万手
- 昨日交易日：2026-07-01
- 昨日成交量：56.51万手
- 较昨日缩量/放量比例：-33.35%（明显缩量）
- 最新成交额：28.12亿元
- 昨日成交额：47.17亿元
- 最新换手率：13.05%
- box_data_source / box range: 新浪备用日线接口; lookback=20 trading days (2026-06-04 to 2026-07-02)
- box_upper / box top: 88.66
- box_lower / box bottom: 37.38
- box_mid: 63.02
- box_position: 78.06% (箱体中部)
- box_breakout_watch_price / breakout buy watch: 88.66
- box_pullback_watch_price / pullback buy watch: 37.38
- ma_data_source: 新浪备用日线接口
- ma5 / 5-day MA: 72.97; price_vs_ma5: 6.08% (above)
- ma10 / 10-day MA: 59.58; price_vs_ma10: 29.92% (above)
- ma20 / 20-day MA: 51.81; price_vs_ma20: 49.40% (above)
- ma60 / 60-day MA: 41.82; price_vs_ma60: 85.11% (above)
- ma_alignment: bullish_alignment
- ma_trend_signal: price_above_ma5_ma10_ma20_short_term_strong
- 是否进入涨停股池：否
- 是否构成缩量涨停：否
- 封板资金：未进入涨停池，不适用
- 首次封板时间：未进入涨停池，不适用
- 最后封板时间：未进入涨停池，不适用
- 炸板次数：未进入涨停池，不适用
- 连板数：未进入涨停池，不适用
- 所属行业：半导体设备/材料
- 自动量价判定：缩量回调
- 给报告生产线的提示：已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径
- 数据更新提示：东方财富主日线接口失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) 已使用新浪备用日线接口。
- 数据更新提示：行业信息获取失败：Expecting value: line 1 column 1 (char 0) 已使用观察池 theme 作为行业/主题兜底。

## 四、给 ChatGPT 报告生产线的使用要求

1. 先做当前报告时点有效性校验：快照生成时间、快照类型、适合报告、生成日期、逐股实时/准实时行情时间和最新交易日/推定日期必须与当前早报/午报/晚报时点匹配。
2. 逐股字段读取顺序：行情主口径、实时/准实时行情可用、实时/准实时数据来源、实时/准实时行情时间、最新交易日/推定日期、最新价、成交量、成交额、涨跌幅、换手率、涨停池、封板资金、炸板次数、连板数、自动量价判定，最后才看日线备份和已存快照备份。
3. 实时/准实时行情可用=是，只说明本快照生成时使用了实时接口；若快照生成时间或快照类型不适合当前报告时点，不得把它当作当前实时数据。
4. 对“缩量涨停、放量突破、封板质量、主升浪候选”等判断，必须优先使用通过时点校验的实时/准实时字段；字段缺失时写明不可核验，不得编造。
5. 若结构化快照未通过实时性校验，报告必须写“结构化快照未通过当前时点有效性校验”，并改用联网实时行情兜底；若兜底也失败，应降低盘面确认分或停止生成盘面结论。
6. 本快照只提供数据核验，不构成买卖建议；报告仍然必须联网搜索新闻、公告、政策、产业动态，不能只看行情快照。


<!-- SNAPSHOT_END -->
