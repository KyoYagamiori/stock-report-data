# 早期布林机会发现与统计模型比较 v3

用户授权：2026-11-05。目标是缩短首次提示的滞后，研究未来1—3个交易日的机会。
采用“四类早期入口＋按形态比较＋小型统计模型竞争＋严格时点核验”。
这是结合需求、可得数据和维护成本作出的工程选择，尚不能称为实证收益最优解。

## 已启用的机会发现

1. 刚收复中轨：信号年龄0—1交易日，距中轨不超过0.5 ATR。
2. 首次回踩中轨：先有明显向上推进，再第一次回到中轨附近并收复；重复回踩不重标首次。
3. 收口预备：连续收缩，带宽进入自身历史较低分位；方向尚未确认。
4. 首次向上扩张：近期收缩后第一次宽度和上轨扩张、价格越过前上轨；不强求下轨上涨。

阈值是登记的研究假设，不是历史最优参数。详见config/early_signals.json。
中轨轻微下降允许观察，明显下降的反弹不混入正常早期机会。
成熟沿上轨走势继续可用于持有观察，不靠近期涨幅挤占新介入队列。
每池20只，轮流抽取、按代码去重到15只；同池优先信号年龄和介入距离，再比较相对强弱。
候选队列已用于研究入口；预测模型尚未获得上线资格。

## 盘中计算和真实性

technicals.calculate保留最近160根完成日线，额外生成early_state。
盘中精确使用最近19个完成日收盘价和当下累计OHLC试算20日布林带、ATR和信号阶段。
完成日线及v1/v2排序不被盘中暂态覆盖，KDJ/MACD也不伪装已收盘。
当天新增形态可以从全市场进入，入口不受昨日前20名限制。
已知权益口径冲突直接拒绝；未知权益窗口、行业映射、公告和分钟确认仍须核验。

提供两个代数条件：今天收盘超过20个交易日前的收盘价，中轨将高于昨天；
今天收盘超过此前19个完成日收盘价的均值，收盘价才会站上今日动态中轨。
这些是条件推演，不是未来价格预测或统计上涨概率。

旧记录只有在本地原始历史哈希通过，重算的末日OHLC、160根数量、布林三轨与原记录一致时，
才补充早期字段。缺历史就保留缺口，不从旧分数猜新形态。

## 更新链路

新增Early BOLL discovery数据工作流，交易时段目标每5分钟检查，独立于日报生成。
它复用已验收日线、当日官方名录和已有报价源，不每次下载5000只历史行情。
午休、休市和交易时段以外不做计划盘中采集；显式代码发布可做一次完成日线诊断。
每条盘中报价单独核验实际时点，超过120秒的报价不进入当前候选。
输出output/early/latest/manifest.json指向不可变队列，带覆盖、来源、真实报价年龄和完成时间。
部分覆盖仍可产生有边界研究队列，不能把它称全市场扫描完成。

GitHub Actions为尽力调度，官方明确可能延迟；本实现没有承诺5分钟准点，
也没有声称接入付费实时行情或启用候选每分钟/完成5分钟、15分钟线确认。
真正的固定延迟需要已有常驻运行环境和具有相应权限的行情源，当前未接入。
任何较新盘中快照都不能覆盖午报11:30冻结数据的身份。

## 去重和统计

机会身份绑定方法、代码、形态和原始事件日期；first_seen_at保留实际首次公开时间，
不回填为图形首次形成日。换期不改原到期，过期的同一事件不重开。
自动条目是observation_only，不将预备、未触发或缺成交证据的观察计为交易胜率。
保留首次提示价、首次距中轨ATR和信号阶段，便于后续核对滞后。
动态退出仍沿用原中轨两日纪律和更早结构失效规则。

## 公开模型参考与取舍

| 参考 | 实际复用 | 不能继承的结果 |
|---|---|---|
| Microsoft Qlib | 按时间切分的研究流程、LightGBM量价排序基线、独立信号和交易评价 | CSI300多股票组合成绩不能当沪深全市场单只1—3日成绩 |
| WorldQuant公开Alpha101论文 | #101的实体与振幅关系，作为一个待检验特征 | 机构实盘权重、当前有效性及A股胜率均未获得 |
| 原研究系统 | 布林核心、ATR、带宽分位、相对强弱、跨期账本、purge和锁定留出期 | 原规则作为对照，不以修改代码证明收益改善 |

没有宣称完整复现Alpha158，当前使用现有8项特征加信号年龄、Alpha101 #101和形态标识。
没有使用或声称访问机构私有模型库。

官方原始来源：

- https://github.com/microsoft/qlib
- https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md
- https://github.com/microsoft/qlib/blob/main/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
- https://arxiv.org/abs/1601.00991
- https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.train.html
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## 训练和验收

research_system.early_model在同一早期形态队列内比较Ridge与小型LightGBM：
至少720个特征日期，最后120日锁定；滚动378日训练、63日验证、63日测试，
边界隔离5日且按实际标签结束日清除跨界样本。
标准化只用训练集，LightGBM早停只用验证集；模型选择只看开发验证。
收益接近时保留简单模型，不根据最后留出结果改选或调参。
成本后T+3超额收益是主标签；以日期均衡、5交易日分块不确定性报告结果，
同日重复股票去重。固定期限标签不冒充组合净值或动态止损收益。

数据须有当时可知的历史名录、官方基准、权益口径和真实成交限制审计。
当前160根原始价格或现存几日的特征库不满足训练条件。
配置config/early_model_dataset.json时，使用file和sha256绑定
output/research/datasets/下的已核验JSON。实际执行：

    python -m pip install -r requirements-research.txt
    python -m research_system.early_model --dataset verified_dataset.json --output experiment_result.json

沿用v2行字段，额外要求setup、execution_audit_sha256和完整的新增特征；
metadata.entry_policy=next_eligible_open_after_publication，
metadata.execution_limits_basis=dated_limits_halts_unfilled_audited。
原始文件和审计哈希引用仍需独立检查，声明字段不能代替原始证据。
已有research-evaluation自动写early_model_status.json；缺合格数据时明确未训练，
不阻止日报交付，也不输出模型概率或自动切换推荐模型。

需要分别验收：数据覆盖、指标数值、候选业务结果、七节全文交付。
测试包括今天新收复、老信号、第一次/第二次回踩、首次扩张、报价时点、
动态布林与直接计算一致、原窗口不重置、原始历史缺口及样本外隔离。
