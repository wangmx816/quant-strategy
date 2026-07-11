# quant-strategy

双均线策略回测看板（TASK3）。

## 功能

- 加载 A 股日线数据（前复权）并进行基础诊断
- 计算 SMA 短/长均线，识别金叉/死叉买卖信号
- 模拟交易回测（含手续费万三、滑点万一）
- 计算累计回报、年化收益、最大回撤、夏普比率等指标
- 生成交互式 HTML 看板与 Word 报告

## 标的

| 代码 | 名称 |
|------|------|
| 002202.SZ | 金风科技 |
| 600031.SH | 三一重工 |
| 000425.SZ | 徐工机械 |
| 600207.SH | 安彩高科 |
| 000816.SZ | 智慧农业 |

## 快速开始

```bash
pip install -r requirements.txt
python build_dashboard.py
python generate_task3_report.py
```

## 在线看板

- GitHub: https://github.com/wangmx816/quant-strategy
- Pages: https://wangmx816.github.io/quant-strategy/

## 目录结构

```
quant-strategy/
├── src/
│   ├── data_fetch.py      # 数据获取
│   ├── diagnostics.py     # 数据诊断
│   └── backtest.py        # 双均线回测
├── data/                  # CSV 日线数据
├── output/                # 图表与 JSON 输出
├── build_dashboard.py     # 生成 index.html
├── generate_task3_report.py
└── index.html
```
