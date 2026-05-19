# 🇺🇸 美Gu恐慌指数 VIX 监控

> VIX × 标普500 × 纳斯达克100 — 巴菲特式恐慌投资仪表盘

![](https://img.shields.io/badge/data-FRED%20%2B%20yfinance-blue)
![](https://img.shields.io/badge/python-3.9%2B-green)
![](https://img.shields.io/badge/deploy-one--click-orange)

## 功能

| 模块 | 说明 |
|------|------|
| 📊 **实时行情** | VIX 当前值 + SPX/NDX 涨跌幅 |
| 🎯 **投资信号** | 基于 VIX 分位数的 7 档买卖建议（强烈买入→减仓） |
| 📈 **VIX 走势** | 近一年日线 + MA20/50/200 均线 |
| 📉 **散点图+回归** | VIX vs SPX/NDX 散点图，叠加回归线 + R² |
| 📊 **远期收益** | 不同 VIX 区间买入后的 1/3/6/12 月平均收益 + 95% 置信区间 |
| 🧪 **信号回测** | 6 档阈值（12/15/20/25/30/35）的历史胜率 + 最大回撤 |
| 🔺 **历史峰值** | 35 年单日 VIX Top 30 |
| ⚠️ **危机事件** | 16 次重大危机（黑色星期一→中美贸易战 2.0） |

## 一键部署

```bash
git clone https://github.com/chengbenchao/meigu-vix-monitor.git
cd meigu-vix-monitor

# 设置 FRED API Key（免费获取: https://fred.stlouisfed.org/docs/api/api_key.html）
export FRED_API_KEY=your_key_here

# 一键部署
sudo bash deploy.sh
```

部署后访问 `http://你的服务器IP/meigu/`

## 数据源

| 来源 | 用途 | 更新频率 |
|------|------|:------:|
| **yfinance** | 每日最新数据（T-1） | 工作日 18:00 CST |
| **FRED API** | 历史底仓 + 补缺 | 同上 |
| 数据库 | SQLite，35 年 × 8,800+ 行 | 自动增量 |

## 技术栈

- **后端**: FastAPI + uvicorn
- **前端**: 原生 HTML/CSS/JS + Chart.js
- **数据库**: SQLite
- **部署**: systemd + nginx + cron

## 项目结构

```
.
├── app.py              # FastAPI 后端
├── fetch_daily.py      # 双源数据抓取（yfinance + FRED）
├── static/
│   └── index.html      # 前端页面
├── deploy.sh           # 一键部署脚本
└── requirements.txt    # Python 依赖
```

## 数据不构成投资建议

本工具仅展示历史数据与统计规律，不构成任何投资建议。过去表现不代表未来收益。
