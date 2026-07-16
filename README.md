# Stock Report Data

这是“股票报告生产线 v1.6.1”的公开行情数据仓库，只保存公开市场快照、质量状态和机器读取契约，不保存完整研报、持仓、成本、交易记录或私人提示词。

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

- 完整快照：08:40、08:55、11:35、12:05、12:25、15:20、20:35、20:50。
- 盘中轻量快照：09:35、10:05、10:35、11:05、13:05、13:35、14:05、14:35、15:05。
- 非交易日：08:40、12:05、20:35，自动切换 `non_trading` Profile。

GitHub 定时任务可能延迟，但发布比较器会依据 `report_cycle`、行情时间、质量等级和 Core 覆盖率选择权威快照，不使用文件生成时间冒充行情时间。

## 数据与风险

- 行情源通过 AKShare 封装的公开接口采集，并记录逐层来源与异常。
- 观察池固定为 Core 10 只、Watch 14 只，另保留公开专项补充股。
- 均线包含 MA5、MA10、MA20、MA60；箱体包含最近 20 个交易日上沿、下沿和位置。
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
