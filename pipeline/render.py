from __future__ import annotations

from typing import Any


def render_snapshot(snapshot: dict[str, Any]) -> str:
    lines = [
        f"# 股票行情快照 | {snapshot['report_date']} {snapshot['snapshot_type']}",
        "",
        f"- Schema：{snapshot['schema_version']}",
        f"- Snapshot ID：`{snapshot['snapshot_id']}`",
        f"- 报告周期：`{snapshot['report_cycle']}`",
        f"- 质量等级：**{snapshot['quality_grade']}**",
        f"- 质量 Profile：`{snapshot['quality_profile']}`",
        f"- 行情日期：{snapshot['market_date']}",
        f"- 行情时间范围：{_value(snapshot.get('quote_time_min'))} 至 {_value(snapshot.get('quote_time_max'))}",
        f"- 采集模式：{snapshot.get('collection_mode', 'unknown')}",
        f"- 调度延迟：{_number(snapshot.get('schedule_delay_minutes'))} 分钟",
        f"- 生成时间：{snapshot['published_at']}",
        f"- 适用报告：{', '.join(snapshot.get('suitable_reports', [])) or '无'}",
        "",
        "## 读取结论",
        "",
        f"- 核心字段缺失：{_joined(snapshot.get('missing_core_fields'))}",
        f"- 可选字段缺失：{_joined(snapshot.get('missing_optional_fields'))}",
        f"- 阻断原因：{_joined(snapshot.get('blocking_reasons'))}",
        f"- 降级动作：{_joined(snapshot.get('degradation_actions'))}",
        f"- 风险提示：{snapshot.get('risk_notice', '本快照只提供公开行情数据核验，不构成投资建议。')}",
        "",
        "## 市场概览",
        "",
    ]
    market = snapshot.get("market", {})
    indices = market.get("indices", [])
    if indices:
        lines.extend(
            [
                "| 指数 | 点位 | 涨跌幅 | 行情时间 |",
                "|---|---:|---:|---|",
            ]
        )
        for item in indices:
            lines.append(
                "| {name} | {latest} | {pct} | {time} |".format(
                    name=_cell(item.get("name") or item.get("code")),
                    latest=_number(item.get("latest") or item.get("latest_price")),
                    pct=_percent(item.get("pct_change") or item.get("change_pct")),
                    time=_cell(item.get("quote_time") or item.get("time")),
                )
            )
    else:
        lines.append("暂无可核验指数数据。")
    breadth = market.get("breadth", {})
    lines.extend(
        [
            "",
            f"- 两市成交额：{_number(market.get('total_turnover'))}",
            "- 市场宽度：上涨 {up} / 下跌 {down} / 平盘 {flat} / 涨停 {limit_up} / 跌停 {limit_down}".format(
                up=_number(breadth.get("up")),
                down=_number(breadth.get("down")),
                flat=_number(breadth.get("flat")),
                limit_up=_number(breadth.get("limit_up")),
                limit_down=_number(breadth.get("limit_down")),
            ),
            f"- 强势方向：{_sector_list(market.get('sectors_top'))}",
            f"- 弱势方向：{_sector_list(market.get('sectors_bottom'))}",
            "",
            "## 观察池行情",
            "",
            "| 代码 | 名称 | 池 | 有效 | 最新价 | 涨跌幅 | 成交额 | 换手率 | MA5 | MA10 | MA20 | MA60 | 箱底 | 箱顶 | 行情时间 |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for stock in snapshot.get("stocks", []):
        lines.append(
            "| {code} | {name} | {pool} | {valid} | {price} | {pct} | {amount} | {turnover} | {ma5} | {ma10} | {ma20} | {ma60} | {lower} | {upper} | {time} |".format(
                code=_cell(stock.get("code")),
                name=_cell(stock.get("name")),
                pool=_cell(stock.get("pool")),
                valid="是" if stock.get("valid_quote") else "否",
                price=_number(stock.get("latest_price")),
                pct=_percent(stock.get("pct_change")),
                amount=_number(stock.get("amount")),
                turnover=_percent(stock.get("turnover_rate")),
                ma5=_number(stock.get("ma5")),
                ma10=_number(stock.get("ma10")),
                ma20=_number(stock.get("ma20")),
                ma60=_number(stock.get("ma60")),
                lower=_number(stock.get("box_lower")),
                upper=_number(stock.get("box_upper")),
                time=_cell(stock.get("quote_time")),
            )
        )
    lines.extend(["", "## 数据源状态", ""])
    source_status = snapshot.get("source_status", {})
    if not source_status:
        lines.append("暂无来源状态。")
    for name, status in source_status.items():
        errors = _joined(status.get("errors")) if isinstance(status, dict) else "无"
        state = status.get("status", "unknown") if isinstance(status, dict) else "unknown"
        source = status.get("source", "unknown") if isinstance(status, dict) else "unknown"
        lines.append(f"- `{name}`：{state}；来源={source}；错误={errors}")
    return "\n".join(lines).rstrip() + "\n"


def render_manifest(manifest: dict[str, Any]) -> str:
    lines = [
        "# 股票行情快照 Manifest",
        "",
        f"- Schema：{manifest['schema_version']}",
        f"- 更新时间：{manifest['generated_at']}",
        f"- 交易日状态：{'交易日' if manifest['calendar'].get('is_trading_day') else '非交易日'}",
        f"- 最近已完成交易日：{manifest['calendar'].get('latest_completed_trading_day') or '暂无'}",
        "",
        "## 报告就绪状态",
        "",
        "| 报告 | 状态 | 等级 | Snapshot ID | 权威文件 |",
        "|---|---|---|---|---|",
    ]
    for report_type in ("early", "noon", "evening"):
        readiness = manifest["report_readiness"][report_type]
        lines.append(
            f"| {report_type} | {readiness['status']} | {_value(readiness.get('quality_grade'))} | "
            f"{_cell(readiness.get('selected_snapshot_id'))} | {_cell(readiness.get('selected_file'))} |"
        )
    lines.extend(
        [
            "",
            "## 权威快照指针",
            "",
            "| 类型 | 等级 | 报告周期 | 行情日期 | 最新行情时间 | 不可变文件 | SHA-256 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for snapshot_type in ("early", "noon", "close", "evening", "intraday"):
        pointer = manifest["snapshots"].get(snapshot_type)
        if pointer is None:
            lines.append(f"| {snapshot_type} | - | - | - | - | - | - |")
            continue
        lines.append(
            f"| {snapshot_type} | {pointer['quality_grade']} | {pointer['report_cycle']} | "
            f"{pointer['market_date']} | {_value(pointer.get('quote_time_max'))} | "
            f"{_cell(pointer['selected_file'])} | `{pointer['sha256']}` |"
        )
    lines.extend(
        [
            "",
            "> 机器读取应以 Manifest 中的不可变 JSON 文件和 SHA-256 为准；`latest` 仅供人工查看与旧入口兼容。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_health(health: dict[str, Any]) -> str:
    lines = [
        "# 股票行情快照运行状态",
        "",
        f"- 状态：{health.get('status', 'unknown')}",
        f"- 快照类型：{health.get('snapshot_type', 'unknown')}",
        f"- 质量等级：{health.get('quality_grade', 'unknown')}",
        f"- 采集模式：{health.get('collection_mode', 'unknown')}",
        f"- 是否历史时点恢复：{'是' if health.get('point_in_time_recovered') else '否'}",
        f"- 调度延迟：{_number(health.get('schedule_delay_minutes'))} 分钟",
        f"- 是否发布：{'是' if health.get('published') else '否'}",
        f"- 计划时间：{health.get('planned_at', 'unknown')}",
        f"- 开始时间：{health.get('started_at', 'unknown')}",
        f"- 完成时间：{health.get('finished_at', 'unknown')}",
        f"- 原因：{health.get('reason', '无')}",
        f"- 阻断原因：{_joined(health.get('blocking_reasons'))}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _sector_list(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "暂无"
    values = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("sector") or item.get("板块名称") or "未知"
        pct = item.get("pct_change")
        if pct is None:
            pct = item.get("change_pct")
        values.append(f"{name}({_percent(pct)})")
    return "、".join(values) or "暂无"


def _number(value: Any) -> str:
    if value is None or value == "":
        return "暂无"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _cell(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _percent(value: Any) -> str:
    if value is None or value == "":
        return "暂无"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return _cell(value)


def _joined(values: Any) -> str:
    if not values:
        return "无"
    if isinstance(values, (list, tuple, set)):
        return "；".join(str(value) for value in values) or "无"
    return str(values)


def _value(value: Any) -> str:
    return "暂无" if value is None or value == "" else str(value)


def _cell(value: Any) -> str:
    return _value(value).replace("|", "\\|").replace("\n", " ")
