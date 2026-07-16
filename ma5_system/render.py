from __future__ import annotations

from typing import Any


def render_screen_markdown(screen: dict[str, Any]) -> str:
    phase_label = "尾盘行动提示" if screen["phase"] == "preclose" else "MA5收盘确认"
    quality = screen["quality"]
    market = screen["market_environment"]
    parts = [
        f"# {screen['report_date']} {phase_label}",
        "",
        f"> 策略：`{screen['strategy_id']}`",
        f"> 扫描完成：中国时间 {screen['completed_at'][11:19]}",
        f"> 数据等级：{quality['grade']}；状态：{quality['report_readiness']}；可执行：{'是' if quality['actionable'] else '否'}",
        "> 说明：这是条件式交易观察，不构成确定性买卖指令；系统不会自动下单。",
        "",
        "## 1. 市场环境开关",
        "",
        f"- 市场评分：**{market['score']:.1f}/100**",
        f"- 环境：**{_regime_label(market['regime'])}**",
        f"- 最高允许总仓位：**{market['maximum_position_pct']}%**",
        f"- 分项：{_component_text(market['components'])}",
        "",
        "## 2. 方向选择",
        "",
    ]
    if market["maximum_position_pct"] < 40:
        parts.insert(24, "- 集中模式最小档位为40%；当前30%上限等价于不新开主交易仓位。")
    for item in screen["directions"][:5]:
        parts.append(
            f"- {item['rank']}. {item['name']}（{item['role']}）：强度 {item['strength']:.2f}，"
            f"上涨占比 {item['positive_ratio']:.1%}，成员 {item['members']} 只"
        )
    if not screen["directions"]:
        parts.append("- 数据不足，未形成可验证的前三方向与两个备选方向。")
    candidate_heading = "唯一A+主交易候选" if screen["phase"] == "preclose" else "15:20收盘确认候选"
    parts.extend(["", f"## 3. {candidate_heading}", ""])
    primary = screen.get("primary_candidate")
    if primary:
        parts.extend(
            [
                f"**{primary['name']} {primary['code']}**，评分 **{primary['score']}**，方向：{primary.get('industry') or '未知'}。",
                "",
                f"- 买入观察区：{_range(primary.get('buy_zone_low'), primary.get('buy_zone_high'))}",
                f"- 转强确认价：{_price(primary.get('confirmation_price'))}",
                f"- 分时均价/尾盘局部高点：{_price(primary.get('minute_vwap'))} / {_price(primary.get('local_tail_high'))}",
                f"- 40%：进入观察区并完成转强确认。",
                f"- 70%：后续回踩 MA5={_price(primary.get('ma5'))} 不破，方向与量价未削弱。",
                f"- 100%：突破箱体顶部 {_price(primary.get('box_top'))} 并确认，且无事件风险上限。",
                f"- 止盈观察区：{_range(primary.get('profit_zone_low'), primary.get('profit_zone_high'))}",
                f"- MA5预警位：{_price(primary.get('ma5_warning'))}",
                f"- 硬失效位：{_price(primary.get('hard_invalidation'))}",
                f"- 风险收益比：{_number(primary.get('reward_risk'))}",
                f"- 事件窗口：{'是，最高70%' if primary.get('event_risk') else '否'}{_risk_reasons(primary)}",
            ]
        )
    else:
        if screen["phase"] == "preclose":
            parts.append("**今日空仓。** 没有同时通过评分、风险收益比、方向、数据等级和时效门槛的 A+ 候选。")
        else:
            parts.append("收盘后没有通过全部门槛的A+确认候选；不得倒推14:45行动。")
        blocked = screen.get("blocked_a_plus_candidate")
        if blocked:
            parts.append(f"观察级A+为 {blocked.get('name')} {blocked.get('code')}，但被市场仓位上限或时效门槛阻断，不得执行。")
    parts.extend(["", "## 4. Top10 完整交易卡", ""])
    if not screen["top10"]:
        parts.append("没有股票达到70分硬门槛；系统未降低标准补足数量。")
    for index, card in enumerate(screen["top10"], start=1):
        parts.extend(_render_card(index, card))
    parts.extend(
        [
            "## 5. 数据质量与限制",
            "",
            f"- 全市场行情覆盖率：{quality['universe_coverage']:.2%}",
            f"- 70日历史覆盖率：{quality['history_coverage']:.2%}",
            f"- 行业映射覆盖率：{quality['industry_coverage']:.2%}",
            f"- 市场环境输入完整：{'是' if quality.get('market_complete') else '否'}",
            f"- Top30深度复权/公告/分时核验完整：{'是' if quality.get('deep_scan_complete') else '否'}",
            f"- 交易日历有效/报告日为交易日：{'是' if quality.get('calendar_valid') else '否'} / {'是' if quality.get('is_trading_day') else '否'}",
            f"- 最新行情年龄：{quality.get('quote_age_minutes')} 分钟",
            f"- 最可能判断错误的地方：{screen.get('most_likely_error') or '方向强度无法跨日延续，或MA5回踩被误判为有效承接。'}",
        ]
    )
    for reason in quality.get("reasons", []):
        parts.append(f"- 降级原因：{reason}")
    parts.extend(["", "## 6. 15:20必须确认的信号", ""])
    checks = screen.get("close_confirmation_checks", [])
    parts.extend(f"{index}. {item}" for index, item in enumerate(checks, start=1))
    if not checks:
        parts.append("1. 本篇已是15:20收盘确认，无额外盘中动作。")
    return "\n".join(parts).rstrip() + "\n"


def _render_card(index: int, card: dict[str, Any]) -> list[str]:
    status = "A+" if card.get("a_plus") else "候选"
    components = card.get("score_components", {})
    return [
        f"### {index}. {card.get('name')} {card.get('code')}｜{card.get('score')}分｜{status}",
        "",
        f"- 方向：{card.get('industry') or '未知'}（方向排名 {card.get('direction_rank') or 'N/A'}）",
        f"- 最新价：{_price(card.get('latest'))}；MA5/MA10/MA20/MA60：{_price(card.get('ma5'))} / {_price(card.get('ma10'))} / {_price(card.get('ma20'))} / {_price(card.get('ma60'))}",
        f"- 箱体底部/顶部：{_price(card.get('box_bottom'))} / {_price(card.get('box_top'))}",
        f"- 买入区/确认价：{_range(card.get('buy_zone_low'), card.get('buy_zone_high'))} / {_price(card.get('confirmation_price'))}",
        f"- 分时均价/尾盘局部高点：{_price(card.get('minute_vwap'))} / {_price(card.get('local_tail_high'))}；转强确认：{'是' if card.get('confirmation_met') else '否'}",
        f"- 止盈区：{_range(card.get('profit_zone_low'), card.get('profit_zone_high'))}",
        f"- MA5预警/硬失效：{_price(card.get('ma5_warning'))} / {_price(card.get('hard_invalidation'))}",
        f"- 计划风险/风险收益比：{_number(card.get('planned_risk_pct'))}% / {_number(card.get('reward_risk'))}",
        f"- 事件窗口：{'是，最高70%' if card.get('event_risk') else '否'}{_risk_reasons(card)}",
        f"- 评分拆分：方向{components.get('direction', 0)}、趋势{components.get('trend', 0)}、回踩转强{components.get('pullback_reclaim', 0)}、量价{components.get('volume_price', 0)}、流动性风险{components.get('liquidity_risk', 0)}",
        f"- 失效条件：收盘跌破 {_price(card.get('hard_invalidation'))}，或方向退潮且14:45仍未收回MA5。",
        "",
    ]


def _component_text(components: dict[str, Any]) -> str:
    labels = {"index_trend": "指数趋势", "breadth": "市场宽度", "turnover": "成交额", "sector_persistence": "板块持续性", "limit_down_risk": "跌停与波动"}
    return "；".join(f"{labels.get(key, key)} {value}" for key, value in components.items())


def _regime_label(value: str) -> str:
    return {"strong": "强势", "neutral": "震荡", "weak": "弱势"}.get(value, value)


def _number(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _price(value: Any) -> str:
    return _number(value)


def _range(low: Any, high: Any) -> str:
    return f"{_price(low)} - {_price(high)}"


def _risk_reasons(card: dict[str, Any]) -> str:
    reasons = [str(item) for item in card.get("event_risk_reasons", []) if item]
    return f"（{'；'.join(reasons[:3])}）" if reasons else ""
