# 日报交易计划和收盘预测反馈

早报、午报和晚报按实际发布时间登记对未来收盘的公开判断。晚报核对早、午两次判断，同时按原条件复盘买入触发、减仓、保护和失效。一次行情触价、日内高低价的先后和实际可成交性分别核对。没有分钟证据则保留未核验状态。

在 `reports/forecasts/YYYY/MM/DD/{early|noon|evening|manual}.json` 创建当期小文件。日期用实际北京时间。`issued_at` 是登记时间，`check_day` 是待验证交易日。只登记发布时间之后的收盘。每个代码、交易日和期次最多一条，三类角色重合时写进同一条。

```json
{
  "schema_version": 1,
  "issued_at": "2026-12-01T12:45:00+08:00",
  "calls": [{
    "code": "600970",
    "roles": ["vcp"],
    "check_day": "2026-12-01",
    "quote_asof": "2026-12-01T11:30:00+08:00",
    "reference_price": 7.9,
    "relation": "below",
    "price": 8.1,
    "etf_context": "mixed",
    "plan": {
      "action": "wait",
      "valid_until": "2026-12-02T15:00:00+08:00",
      "buy_low": 8.11,
      "buy_high": 8.21,
      "entry_rule": "放量收过枢纽，下一有效时段回踩承接",
      "reduce_low": 7.95,
      "reduce_high": 8.10,
      "reduce_fraction": 0.3333333333,
      "stop": 7.69,
      "exit_rule": "假设已有可卖持仓，反弹遇阻先减仓，结构失效退出"
    }
  }]
}
```

金额使用元。`relation` 可用 `above`、`below` 或 `between`。前两项使用严格不等式。`between` 增加 `high` 并包含上下限。`plan.action` 可用 `buy`、`wait`、`hold`、`reduce`、`exit` 或 `avoid`。参考价带、动作条件和分批比例允许留空，按可核事实填写。可补 `plan.profit_target`。`etf_context` 可用 `supportive`、`weak`、`mixed` 或 `unknown`。有同口径的 ETF 证据才填写前三项。角色为 `comprehensive`、`technical` 或 `vcp`。只登记公开行情与研究方案。

现有日报模型工作流验证公开分支的字节，在收盘前记录实际读取时间，收盘后读取经哈希核验的滚动日线库。汇总在 `output/research/latest/daily_model_report_feedback.json`，冻结记录在 `output/research/daily_model/report_forecasts.json`。公开读取时点晚于收盘的样本无法作为前向证据，缺最新日线的样本可在后续取得日线后补核。同一股票和结算日的早午修订均可复盘，模型每个股票和结算日仅计一次，并在组内对交易日等权。

新增校准仅学习原始收盘预测的命中结果，按判断形式及 ETF 环境比较。日内执行、T+1、涨跌停、跳空、分批退出及费用依靠相应成交证据单独复盘。原 LightGBM、Ridge 和正式训练门槛继续由日线模型维护。

## VCP 分钟复盘

晚报第 2 节可从 `output/research/latest/daily_model_report_feedback.json` 的
`vcp_minute_feedback` 读取 C 类计划的分钟复盘。现有工作流在收盘后核对分钟开高低收及股数与当日已核日线是否一致，
保留原始行情的哈希及实际读取时间。手动计划与各期预测分别按各自的公开可见时间、有效期计算。
报告可引用价带内有实际 OHLC 价格的分钟、仅和价带相交的区间、确认的 15 分钟收盘以及缺失交易日。
若触价与符合条件的收盘落在同一根记录，保留先后未核验。价位证据和实盘成交使用各自的记录。

新发布的 VCP 计划应在 `plan.vcp_checks` 同步写入与正文一致、已经给出确切数值的条款。
以下字段可按实际条件选填。

```json
{
  "daily_breakout": {"pivot": 8.1, "min_volume_shares": 24440000},
  "stop_below_15m": true,
  "reduce_after_band_below_15m": true
}
```

`daily_breakout` 核 `check_day` 日收盘严格高于枢纽且全天成交量达到股数门槛。
`stop_below_15m` 使用已登记的 `stop`，核完整 15 分钟收盘严格低于该价格。
`reduce_after_band_below_15m` 使用已登记的减仓价带，核有明确价带价格记录后的首根 15 分钟收盘是否严格低于价带下沿。
如果正文还要求回踩承接、价带内成交、前高空间或其他证据，按原计划继续核验。
旧报告沿用其冻结文件，分钟复盘可引用可核实的价格事件，其他条件按原文核验。
