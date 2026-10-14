# 逐股研究证据与恢复

本工具保存全量资料、恢复下载进度，并核验分析记录的代码、时点、来源和版本；它不代写投资结论，也不把抓取数据当成完成研究。研究执行者必须实际阅读、形成逐公司判断并保存review。

## 数据与完成的区别

- `dossier_count`：在当期官方沪深普通A股名单中建立了多少份资料档案。
- `evidence_counts`：业务、财务、报价、日线、公告标题等不同资料的实际取得数量。标题为空不等于没有公告；过期日线、未完成日线和不同复权口径分别保留。
- `individual_review_count`：实际存在本期独立审阅记录且绑定了当前证据版本的公司数；缺关键资料仍可能不合格。
- `complete_count/reviewed_count`：六项分析齐备、原文来源及时点合格、关键缺口清零、代码和证据哈希一致的记录数。机械结构校验不证明研究质量，不能用批量生成文字、自填reviewed=true或抽样验收替代实际逐股阅读。

六项为业务竞争、财务质量及负债、合适估值和经济可比同业、公告催化及风险、BOLL优先的技术量价、含反证及后续验证的综合判断。不关注也可以是完整结论。只有官方代码集合完全相等且所有股票真实完成，才允许全市场首选。

## 恢复入口

读取`reports/research/state/manifest.json`，再读其中的coverage、next_batch和dossier分片；已有人工审阅单独保存在reviews中。按未完成代码顺序继续，不能只深查Top30。新周期须逐股核对财报、公告、权益和上市状态及行情变化，写本期复核；旧review不自动转成新周期完成。

公开目录只包含公开公司资料、分析、来源和技术执行状态，不保存账户、持仓、私人提示词或原始对话。

## 可执行组件

- `python -m research_pipeline.financials --asof YYYY-MM-DD --output PATH`：分页获取结构化财务资料，保留响应哈希及日期；核对接口总页数、成功页集合和实际行数。页面全到而总条数变化仍属于不一致，不标完整。历史聚合资料不能代替公司原文。
- `python -m research_pipeline.daily --universe FILE --market-date YYYY-MM-DD --out PATH --max-seconds 300`：全名单按代码获取日线，每只立即保存。截止预算后保留进度，下次运行读取缓存继续；排除市场截点后的未完成日线，保留实际口径。失败和新股历史不足均不计完成。
- `python -m research_pipeline.ledger --seed SOURCE_DIR --universe FILE --out DEST --cycle CYCLE --cutoff ISO_TIME --overlays SOURCE_RECONCILIATIONS --reviews ANALYST_REVIEWS`：将明确有日期的证据整理为逐码档案，校验独立分析与版本，产生coverage及下一批清单。overlays是经过原文阅读后实际撰写的来源核对，不能自动清空缺口。

公开档案的财务原始页来源集中放在`financial_page_sources.json`。逐码资料保留该页的名称、行位置和响应哈希。资料基线日期与本期审阅时间分别记录，不能把今天重新下载的聚合数据伪称历史时点已知。

本次恢复保留原早报和原覆盖数字；后续新增逐股审阅及报告修订另存，形成可核查增量，不改写历史。
