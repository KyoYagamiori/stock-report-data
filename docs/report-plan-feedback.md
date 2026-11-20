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
