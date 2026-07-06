# 股票报告快照读取状态

生成时间：2026-06-30T00:44:05+08:00
快照类型：早报前快照
适合报告：早报盘前基线
生成日期：2026-06-30
生成时间：中国时间 00:44
使用限制：通常只能核验上一交易日收盘和观察池状态，不能代表今日盘中数据。

## 数据质量

- 股票数量：5
- 实时/准实时可用股票数：0
- 均线字段可用股票数：0
- 箱体字段可用股票数：0
- 最新交易日集合：2026-06-29
- 实时/准实时行情时间集合：暂无

## 观察池摘要

- 当前 active 股票数量：5
- high priority 股票：
- 长电科技 600584
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
- 通富微电 002156
- 华天科技 002185

## 读取规则

1. 这是 ChatGPT 报告生产线的首选入口，用于确认公开镜像是否已经更新。
2. 如果本文件生成时间早于当前报告应使用的快照时点，说明读取器拿到了旧缓存，必须改读 GitHub contents API 或 report_data_compact.md。
3. 不得把 Raw/CDN/Jina 返回的旧生成时间当作本次快照读取成功。
4. 若状态文件可用但完整快照不可用，优先读取 output/latest/report_data_compact.md，仍不足时再联网实时行情兜底。

## 数据更新提示

- 涨停股池获取失败：('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
- 东方财富主日线接口失败：('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')) 已使用新浪备用日线接口。
- 行业信息获取失败：Length mismatch: Expected axis has 3 elements, new values have 2 elements 已使用观察池 theme 作为行业/主题兜底。
- 最新交易日为 2026-06-29，当前自然日可能非 A 股交易日或数据未更新。
