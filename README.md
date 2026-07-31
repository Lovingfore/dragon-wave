# LFCX EPOCH

LFCX EPOCH 是由 Lovingfore × Codex 打造的零订阅费用 BTC 周期情报产品。它展示 BTC 价格、NUPL、已实现价格、MVRV、MVRV Z-Score 和狼波周期指数，并通过 Gmail 发送每日报告与高风险状态预警。

网页采用最低 `1024px` 宽度的 PC 布局，不提供手机端适配。

页面会自动找出 `2011`、`2015`、`2018`、`2022` 四轮周期内的 BTC 日线最低点，并将当日全部可用指标与当前数据并排展示。对照表同时提供本次熊市低点预期：每次打开或刷新页面时，使用最新已实现价格趋势、距下一理论周期底部的区块距离和历次底部估值水平动态重算，并保持价格、MVRV、已实现价格和 NUPL 的数学关系一致。

历史走势图支持多选指标，并为每个已选指标生成独立图表，避免不同量纲的曲线互相压缩。每张图都会显示当前值、四轮历史底部参考区间、中位值、距区间的差值，以及各周期底部样本；底部区间同时以参考带或方向标记绘制在图内。狼波模块采用源站式双图，上方为按指数色谱着色的 BTC 对数价格线，下方为 0–1 周期指数。

全历史走势图中，BTC 价格与已实现价格使用对数纵轴；MVRV 与 MVRV Z-Score 从 `2011-01-01` 开始展示，避免 2010 年早期低流动性异常值压缩后续周期走势。狼波周期指数按官方 Wolfy Wave Index 的公开方法计算，并使用从蓝（0）到红（1）的周期色谱绘制。官方方法参考：[wolfyxbt.github.io/wolfy-wave-index](https://wolfyxbt.github.io/wolfy-wave-index/)。原始历史数据完整保留在 `data/metrics.json` 中。

## 数据与模型

- Coin Metrics Community：BTC 日线价格、市值、MVRV、流通量、每日区块数。
- Mempool.space / Blockchain.com：最新区块高度。
- Coinbase、CoinGecko、Binance：尽量实时的 BTC 现货价格。
- `NUPL = 1 - 1 / MVRV`。
- `已实现价格 = (市值 / MVRV) / 流通量`。
- `MVRV Z-Score = (市值 - 已实现市值) / 市值的扩展标准差`。
- 狼波周期指数仅由区块高度决定，沿用 Wolfy Wave Index 的公开方法。

综合风险分将各信号映射到 `0–100`。`0–15` 为接近熊市底部，`85–100` 为接近牛市顶部。七日判断使用近期风险斜率与七日后的区块周期位置，不预测具体价格。

## 本地运行

```powershell
python scripts\update_data.py --full --daily-only
python -m http.server 4173
```

打开 `http://127.0.0.1:4173/`。`--daily-only` 只用于交易所域名无法访问的本地网络；GitHub Actions 会正常尝试实时接口。

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## GitHub 免费部署

1. 创建公开仓库并把本目录推送到 `main` 分支。
2. 在仓库 `Settings > Pages` 中将 Source 设为 `GitHub Actions`。
3. Google 账号开启两步验证后生成 Gmail 应用专用密码。
4. 在仓库 `Settings > Secrets and variables > Actions` 中添加：
   - `GMAIL_ADDRESS`：发送和接收邮件的 Gmail 地址。
   - `GMAIL_APP_PASSWORD`：16 位 Gmail 应用专用密码。
5. 在 Actions 中手动运行 `Update data and notify`，选择 `test` 验证邮件。

`monitor.yml` 每小时第 7 分钟刷新数据并检查风险状态；每天 `UTC 14:00`（北京时间 `22:00`）单独发送日报。GitHub Actions 的定时任务偶尔可能因平台排队延迟数分钟，但无需保持电脑开机。进入高风险顶部或底部区间时会额外发送一次状态变化预警。

## 隐私

邮箱地址与应用专用密码仅存储在 GitHub Actions Secrets 中。网页、数据文件和代码均不包含邮件凭证，邮件任务的公开日志不会输出收件地址，发送失败时也只记录不含敏感上下文的通用错误。

仓库会忽略常见的环境变量、凭证、私钥文件。GitHub Pages 每次部署前都会运行隐私回归测试，阻止包含邮箱地址的公开网页或数据文件上线。不要把真实凭证写入代码、数据文件、提交信息或 Actions 的普通变量；如发生误提交，应立即撤销 Gmail 应用专用密码并清理 Git 历史。
