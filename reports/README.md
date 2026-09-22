# 股票日报公开归档

- [最新报告索引](latest/manifest.json)
- [2026-09-21 午报](archive/2026/09/21/noon.md)

## 文件组织

正式报告按 `archive/YYYY/MM/DD/early.md`、`noon.md`、`evening.md` 保存。
每份报告包含行情截点、资讯截点、来源、数据质量、观点、反证与承接摘要。
`latest/manifest.json` 的 `latest_by_cycle` 指向各时段最新报告；`reports` 列出归档记录。

报告由 ChatGPT 日报任务形成并通过 GitHub 连接写入；GitHub Actions 负责公开行情采集。
写入后必须重新读取确认，才能宣布归档成功。归档失败不阻止对话内交付，但必须说明。
只归档公开研究内容，不归档账户信息、私人提示词或原始对话。报告上传不会触发行情采集循环。

历史报告反映原交付时点的信息，不用后来行情覆盖原判断。修订另存版本并说明原因。
本仓库不执行交易。
