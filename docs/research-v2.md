# 日报研究与并行评测 v2

实验boll_multisetup_v2_20261103保留BOLL v1作生产对照。v2处于shadow模式，不预先宣称收益改善。

## 已接入生产的数据流

- 已完成160根日线追加ATR20（20根TR简单均值）、自身过去120根带宽分位、5日中轨/ATR斜率、5/20日收益、前20日高点、5日结构低点和中轨收复特征。原BOLL/KDJ/MACD及v1分数不变。
- 全量逐码评价后分别构建收缩突破、趋势回踩、趋势修复三池，各最多20只，合并去重给15只队列。突破不统一要求下轨上行。初始阈值是登记假设，并非最优参数。
- 当前排序是透明的字段先后比较，不是预期收益或上涨概率。市场相对强弱使用有特征股票的收益中位数代理，不能称官方指数；行业适用映射不足时留空。
- 结构资格、入场资格、证据完备性分开。公司/权益/真实入场结构仍需核验，自动入场合格数为0。市场状态只作研究标签，不改变生产推荐。
- 午价叠加在完成日线之上。上午成交量只比已保存的前一完整上午，缺基线留空。旧档案没有v2字段时明示缺失，不伪造历史预测。
- screen.json的research_shadow指向不可变结果、原始字节SHA-256及逐码分片。日报只读小型队列。

## 四层验收与研究账本

分别验收数据覆盖、指标计算、候选业务结果、聊天全文交付。午间setup理由与拒绝原因已拆开；验收核对合格数、排序、候选身份和截断额度，正向测试要求合格样本确实入选。真实零候选须有依据。

Research shadow evaluation在既有日线、午间、报告索引工作流结束后运行，无新增ChatGPT任务。读取哈希绑定的来源和交易日历，写出：

- output/research/latest/summary.json：日报读取的简明成绩、数据缺口及升级状态。
- output/research/state/episodes.json：公开研究机会，禁止保存个人持仓、成本或账户。
- output/research/tape/：不可变逐日价格证据。
- output/research/noon/：时间合规的上午价量基线。

同一代码、方法、策略和原窗口只产生一个episode；重复报告合并角色与来源，不重置窗口、不重复计样本。旧报告只有文字条件时进入观察账本，不推断触发、成交或失效日期，不计收益胜率。

新报告有预算时，可在既有*-handoff.json增加available_at与research_signals，必须绑定正文body_sha256。每个信号允许字段：code、roles（comprehensive/technical）、method_version、strategy、first_issued_at、valid_until、entry_rule、reference_price、reference_asof、invalidation_price。时间必须带时区，first_issued_at不得在换期时重置。

默认entry_rule=observation_only。只有明确登记next_daily_open才按公开后下一次日线开盘做研究成交假设；不能按发布前的价格买入。自动收盘shadow仅采用该明确假设。涨停、无成交、开盘已失效不假定买到。

T+1/T+3/T+5按交易日计算。往返成本20bp是实验假设，不是用户真实费用。缺交易日、权益口径冲突保留缺口。固定期限收益标签与首次结构/两日中轨失效分别记录，不能称完整动态止损策略净值。没有分钟证据就不对午间触发假定13:00成交；不报告组合最大回撤或统计上涨概率。

## 历史模型入口与升级门槛

运行：python -m research_system.model --dataset verified_dataset.json --output experiment_result.json。

固定8特征、alpha=10正则化线性回归。至少720个特征日期，最后120个日期锁定；滚动378日训练、63日验证、63日测试，边界至少隔离5日，再按实际标签结束日清除跨界样本。标准化只用训练集。

输入metadata需要asof、universe_basis=historical_point_in_time、benchmark_basis=verified_official、corporate_actions_basis=asof_adjusted_and_execution_prices_retained、primary_horizon_sessions=3、costs_in_target=true。rows逐行需要date、code、features、target_t3_net_excess_pct、signal_available_at、features_known_at、label_known_at、label_end_date、source_sha256及v1对照字段。特征名见research_system/model.py的FEATURES。

校验格式、时间与哈希引用不能代替原始证据审计。研究结果按日期均衡与v1比较，不把同日个股、重叠标签当独立样本。仍需日期分块不确定性、多次试验偏差、可执行退出和组合回撤检查及人工复核。历史结果为正也不自动切换生产模型。

当前没有合格3—5年历史时点名录、完整官方基准及权益调整数据集，必须标未训练。至少20个完整特征交易日的前向观察只验证运行，不证明收益优势。不继承旧MA5回测结论。

## 日报

七节、双首选和原时点保留。早报给计划，午报验证变化，晚报登记结果和次日预案。首页区分待触发、已触发、失效/到期；结构优先不能写成已有入场资格。中长期重点更新变化，周五晚报汇总阶段成绩。新实验缺数不阻塞全文交付，不改既有原窗口或已发布历史正文。
