# 龙波

龙波是一个零订阅费用的 BTC 周期监控网页。它展示 BTC 价格、NUPL、已实现价格、MVRV、MVRV Z-Score、杠杆代理和龙波指数，并通过 Gmail 发送每日报告与高风险状态预警。

## 数据与模型

- Coin Metrics Community：BTC 日线价格、市值、MVRV、流通量、交易所储备、每日区块数。
- Mempool.space / Blockchain.com：最新区块高度。
- Binance、Bybit、OKX：公开 BTC 永续合约未平仓量。
- `NUPL = 1 - 1 / MVRV`。
- `已实现价格 = (市值 / MVRV) / 流通量`。
- `MVRV Z-Score = (市值 - 已实现市值) / 市值的扩展标准差`。
- 杠杆代理为主流交易所公开未平仓量除以 Coin Metrics 跟踪的交易所 BTC 储备，与付费平台的专有指标可能存在差异。
- 龙波指数仅由区块高度决定，沿用 Wolfy Wave Index 的公开方法。

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

`monitor.yml` 每小时第 7 分钟运行。北京时间 `22:00–23:59` 的首次成功任务会发送当日日报；进入高风险顶部或底部区间时会额外发送一次状态变化预警。

## 隐私

邮箱地址与应用专用密码仅存储在 GitHub Actions Secrets 中。网页、数据文件和代码均不包含邮件凭证。

