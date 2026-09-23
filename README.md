# Stock Report Data

这是公开行情与股票日报归档仓库，保存公开市场快照、质量状态及已发布的公开研究报告。不得存放个人持仓、成本、账户、交易记录、私人提示词、凭据或未公开资料。

## 直接读取入口

- [行情 Manifest](output/latest/manifest.json)：按时段找到不可变行情快照。
- [日报归档](reports/README.md)：查阅公开早报、午报、晚报。
- [日报 Manifest](reports/latest/manifest.json)：下一期报告读取此前已归档报告的入口。
- [采集健康状态](output/health/latest_run.md)：检查数据异常。

公开文件可以通过 GitHub 页面或 raw.githubusercontent.com 直接读取。仓库公开不代表采集接口永远可用；必须独立检查数据时间与缺口。

## 机器读取顺序

1. 读取 `output/latest/manifest.json`。
2. 按报告类型读取 `report_readiness.early`、`report_readiness.noon` 或 `report_readiness.evening`。
3. 只读取其中 `selected_file` 指向的不可变归档 JSON。
4. 核对归档文件内 `snapshot_id` 与 `selected_snapshot_id` 一致；支持哈希校验时，再核对 `sha256`。
5. `ready_a` 生成完整报告；`ready_b` 生成明确标注缺失字段的降级正式报告；`not_ready` 或 `invalid` 才启用联网行情兜底。
6. `not_applicable` 表示非交易日，报告应切换为全球资讯、公告、人物发言和下一交易日推演，不得伪造 A 股盘中数据。

便于人工查看的入口：

- `output/latest/manifest.md`
- `output/latest/<snapshot_type>/report_data_compact.md`
- `output/health/latest_run.md`

`output/latest/report_data.json` 和 `output/latest/report_data.md` 只用于兼容旧入口，不是机器读取权威来源。

## 快照类型

| 类型 | 用途 | 发布规则 |
|---|---|---|
| `early` | 09:00 早报盘前基线 | 同一报告周期质量优先 |
| `noon` | 12:40 午报上午盘核验 | 同一报告周期质量优先 |
| `close` | 当日收盘核验 | 同一报告周期质量优先 |
| `evening` | 21:00 晚报 | 必须继承同日有效 `close`；缺失时自动补采 |
| `intraday` | 盘中滚动观察 | 行情时间新鲜度优先，允许较新 B 替换较旧 A |

## 中国时间调度

- 完整快照：交易日 08:17、08:43（早报）；11:37、12:07（午报）；15:20（收盘）；每日 20:17、20:41（晚报）。
- 14:35 保留盘中轻量快照和独立 MA5 盘前扫描；其他盘中时点可手动触发。
- 周末只执行 20:17、20:41；工作日若遇休市，早午采集会自动切换 `non_trading` Profile，报告任务仍只在晚间交付。

GitHub 定时任务可能延迟；同一发布组保留排队任务，但过期任务直接退出并记录健康状态，不占用行情采集。盘前优先复用经哈希核验的上一交易日收盘快照；其行情日期保持上一交易日。发布比较器依据 `report_cycle`、行情时间、质量等级和 Core 覆盖率选择权威快照，不使用文件生成时间冒充行情时间。

## 数据与风险

- 行情源通过 AKShare 封装的公开接口采集，并记录逐层来源与异常。
- 数据采集覆盖 Core 11 只（含东威科技 688700，唯一 locked）、Watch 14 只；胜宏科技（300476）保留 Watch，locked=false。日报实际展示的活跃观察池按[逐期复盘规则](reports/LOOP.md)动态选择。
- 均线包含 MA5、MA10、MA20、MA60；箱体包含最近 20 个交易日上沿、下沿和位置。
- BOLL(20,2)、KDJ(9,3,3)、MACD(12,26,9)提供实际计算参数、初始化方式、复权口径及指标日期。当前日线来自未复权接口，不能标成前复权，也不宣称与同花顺完全一致；修复前标成前复权的旧指标不在盘前复用。
- 午间成交额只在上一交易日同一午间快照经核验、股票和时点均匹配时计算同段变化；不同时段、不同单位的成交量不作比例比较。
- 午间成交量不与上一交易日全天比较；指数成分成交额不当作全市场成交额。
- 缺失字段保持为空并进入质量说明，不推测、不补写。
- 本仓库只用于信息核验，不构成投资建议或确定性买卖指令。

## MA5 集中进攻系统

MA5 系统与早中晚快照使用独立命名空间，不修改 v1.6.1 的 Manifest：

1. 14:35 生成 `preclose` 全A扫描，供14:45尾盘任务读取。
2. 15:20 生成 `close` 正式收盘确认，供21:00晚报验证。
3. 机器先读 `output/ma5/latest/manifest.json`，再读 `scans.<phase>.selected_file` 指向的不可变归档；Manifest指针同时带扫描时点、行情日期、市场评分、Top10摘要、分片指针和SHA256。
4. 只有交易日历已验证、市场环境输入完整、`quality.grade=A`、`actionable=true` 且14:52前完成的 `preclose` 扫描可输出行动等级。
5. Top10 全部有交易卡，但只有唯一 A+ 可成为主候选；没有 A+ 时保持空仓。
6. `output/ma5` 只含公开市场数据和策略信号，不含用户持仓、成本、数量或私人交易日志。
7. Top30会进一步读取5分钟行情和公告事件；Top10任一深度字段缺失时不得获得A级可执行状态。

首次启用需手动运行 `MA5 all-A bootstrap`，生成滚动70日历史与行业映射；之后初筛Top30会逐日刷新前复权数据，15:20写回滚动状态，每周六18:00（中国时间）自动分片重建全A复权基线。
