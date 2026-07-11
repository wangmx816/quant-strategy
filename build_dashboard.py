#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成双均线策略回测 HTML 看板。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.backtest import BacktestConfig, run_backtest, run_multi_experiments
from src.data_fetch import DATA_DIR, STOCKS, fetch_all
from src.diagnostics import diagnose, format_diagnostic_text

ROOT = Path(__file__).resolve().parent
OUT_HTML = ROOT / "index.html"
REPO_URL = "https://github.com/wangmx816/quant-strategy"
PAGES_URL = "https://wangmx816.github.io/quant-strategy/"


def load_or_fetch() -> dict[str, pd.DataFrame]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, pd.DataFrame] = {}
    need_fetch = False
    for symbol in STOCKS:
        path = DATA_DIR / f"{symbol}_daily.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=["trade_date"])
            data[symbol] = df.sort_values("trade_date").reset_index(drop=True)
        else:
            need_fetch = True
            break
    if need_fetch or not data:
        data = fetch_all("qfq")
    return data


def serialize_backtest(symbol: str, df: pd.DataFrame, cfg: BacktestConfig) -> dict:
    res = run_backtest(df, cfg)
    d = res["data"]
    eq = res["equity"]
    dates = d["trade_date"].dt.strftime("%Y-%m-%d").tolist()

    buy_idx = d.index[d["buy_signal"] == 1].tolist()
    sell_idx = d.index[d["sell_signal"] == 1].tolist()

    return {
        "symbol": symbol,
        "name": STOCKS[symbol]["name"],
        "ts_code": STOCKS[symbol]["ts_code"],
        "config": {
            "short": cfg.short_window,
            "long": cfg.long_window,
            "initial_capital": cfg.initial_capital,
            "commission": cfg.commission,
            "slippage": cfg.slippage,
            "position_ratio": cfg.position_ratio,
        },
        "metrics": res["metrics"],
        "diagnostic_text": format_diagnostic_text(diagnose(df, symbol)),
        "charts": {
            "dates": dates,
            "close": [round(float(x), 2) for x in d["close"]],
            "sma_short": [round(float(x), 2) if pd.notna(x) else None for x in d["sma_short"]],
            "sma_long": [round(float(x), 2) if pd.notna(x) else None for x in d["sma_long"]],
            "strategy_nv": [round(float(x), 4) for x in eq["net_value"]],
            "benchmark_nv": [round(float(x), 4) for x in d["benchmark_nv"]],
            "drawdown_pct": [round(float(x) * 100, 2) for x in eq["drawdown"]],
            "buy_dates": [dates[i] for i in buy_idx if i < len(dates)],
            "buy_prices": [round(float(d.iloc[i]["close"]), 2) for i in buy_idx if i < len(d)],
            "sell_dates": [dates[i] for i in sell_idx if i < len(dates)],
            "sell_prices": [round(float(d.iloc[i]["close"]), 2) for i in sell_idx if i < len(d)],
        },
        "trades": [
            {
                **t,
                "trade_date": t["trade_date"].strftime("%Y-%m-%d")
                if hasattr(t.get("trade_date"), "strftime")
                else t.get("trade_date"),
            }
            for t in (res["trades"].to_dict(orient="records") if not res["trades"].empty else [])
        ],
    }


def build_comparison(stock_data: dict[str, pd.DataFrame]) -> list[dict]:
    exp = run_multi_experiments(stock_data, [(5, 15), (5, 20), (5, 35), (10, 30)])
    rows = []
    for _, r in exp.iterrows():
        rows.append(
            {
                "symbol": r["symbol"],
                "name": STOCKS[r["symbol"]]["name"],
                "label": f"{STOCKS[r['symbol']]['name']}\nSMA{r['short_ma']}/{r['long_ma']}",
                "short_ma": int(r["short_ma"]),
                "long_ma": int(r["long_ma"]),
                "annualized_return": float(r["annualized_return"]),
                "sharpe_ratio": float(r["sharpe_ratio"]),
                "max_drawdown": float(r["max_drawdown"]),
                "excess_return": float(r["excess_return"]),
            }
        )
    return rows


def render_html(payload: dict) -> str:
    data_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>双均线策略回测看板 | Quant Strategy</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #f4f6fb; --sidebar: #fff; --panel: #fff; --text: #1e293b;
      --muted: #64748b; --accent: #2563eb; --green: #16a34a; --red: #dc2626;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; background: var(--bg); color: var(--text); }}
    .layout {{ display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }}
    .sidebar {{ background: var(--sidebar); border-right: 1px solid var(--border); padding: 20px 16px; }}
    .sidebar h1 {{ font-size: 1.1rem; margin-bottom: 4px; }}
    .sidebar .sub {{ color: var(--muted); font-size: .82rem; margin-bottom: 18px; }}
    .field {{ margin-bottom: 14px; }}
    .field label {{ display: block; font-size: .82rem; color: var(--muted); margin-bottom: 4px; }}
    .field select, .field input {{ width: 100%; padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px; font-size: .9rem; }}
    .field input[type=range] {{ padding: 0; }}
    .range-val {{ float: right; color: var(--accent); font-weight: 600; }}
    .toggle-row {{ display: flex; justify-content: space-between; align-items: center; font-size: .85rem; margin-bottom: 8px; }}
    .btn {{ width: 100%; padding: 9px; border: none; border-radius: 8px; background: var(--accent); color: #fff; cursor: pointer; font-size: .9rem; margin-top: 8px; }}
    .btn.secondary {{ background: #e2e8f0; color: var(--text); }}
    .main {{ padding: 20px 24px 40px; overflow-x: hidden; }}
    .links {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }}
    .links a {{ font-size: .82rem; color: var(--accent); text-decoration: none; border: 1px solid #bfdbfe; padding: 4px 10px; border-radius: 999px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 18px; }}
    .kpi {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }}
    .kpi .label {{ font-size: .78rem; color: var(--muted); }}
    .kpi .value {{ font-size: 1.5rem; font-weight: 700; margin: 4px 0; }}
    .kpi .hint {{ font-size: .75rem; color: var(--muted); }}
    .pos {{ color: var(--red); }} .neg {{ color: var(--green); }}
    .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin-bottom: 16px; }}
    .panel h2 {{ font-size: .95rem; margin-bottom: 4px; }}
    .panel .cap {{ font-size: .8rem; color: var(--muted); margin-bottom: 12px; }}
    .chart-h {{ height: 320px; position: relative; }}
    .chart-m {{ height: 240px; position: relative; }}
    .row2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .diag {{ font-size: .85rem; line-height: 1.7; text-align: justify; color: #334155; }}
    .compare-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; }}
    @media (max-width: 1100px) {{ .layout {{ grid-template-columns: 1fr; }} .kpi-grid {{ grid-template-columns: repeat(2,1fr); }} .row2,.compare-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <h1>双均线策略回测看板</h1>
    <div class="sub">TASK3 · Quant Strategy</div>
    <div class="field"><label>股票选择</label><select id="stockSel"></select></div>
    <div class="field"><label>起始日期</label><input type="date" id="startDate" /></div>
    <div class="field"><label>结束日期</label><input type="date" id="endDate" /></div>
    <div class="field"><label>短期 SMA <span class="range-val" id="shortVal">5</span></label><input type="range" id="shortMa" min="3" max="20" value="5" /></div>
    <div class="field"><label>长期 SMA <span class="range-val" id="longVal">15</span></label><input type="range" id="longMa" min="10" max="60" value="15" /></div>
    <div class="field"><label>初始资金（元）</label><input type="number" id="capital" value="100000" step="1000" /></div>
    <div class="toggle-row"><span>手续费（万三）</span><input type="checkbox" id="useComm" checked /></div>
    <div class="toggle-row"><span>滑点（万一）</span><input type="checkbox" id="useSlip" checked /></div>
    <button class="btn" id="applyBtn">应用参数并重算</button>
    <button class="btn secondary" id="resetBtn">重置默认参数</button>
    <div class="field" style="margin-top:16px"><label>数据诊断摘要</label><div class="diag" id="diagText"></div></div>
  </aside>
  <main class="main">
    <div class="links">
      <a href="{REPO_URL}" target="_blank">GitHub 仓库</a>
      <a href="{PAGES_URL}" target="_blank">在线看板</a>
    </div>
    <section class="kpi-grid" id="kpiGrid"></section>
    <section class="panel">
      <h2>图1 策略净值 vs 买入持有基准</h2>
      <div class="cap">红色为双均线策略净值，灰色为买入持有基准，观察策略是否跑赢标的。</div>
      <div class="chart-h"><canvas id="equityChart"></canvas></div>
    </section>
    <section class="row2">
      <div class="panel">
        <h2>图2 回撤（%）</h2>
        <div class="cap">相对历史最高净值的回撤幅度，衡量策略风险。</div>
        <div class="chart-m"><canvas id="ddChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>图3 价格 + 均线 + 买卖点</h2>
        <div class="cap">金叉（短期均线上穿长期）买入，死叉卖出。</div>
        <div class="chart-m"><canvas id="priceChart"></canvas></div>
      </div>
    </section>
    <section class="panel">
      <h2>图4 多股票 × 多均线参数对比</h2>
      <div class="cap">5 只股票在 SMA(5/15)、(5/20)、(5/35)、(10/30) 下的年化收益、夏普、最大回撤与超额收益。</div>
      <div class="compare-grid">
        <div class="chart-m"><canvas id="cmpAnn"></canvas></div>
        <div class="chart-m"><canvas id="cmpSharpe"></canvas></div>
        <div class="chart-m"><canvas id="cmpMdd"></canvas></div>
      </div>
      <div class="chart-m" style="margin-top:14px"><canvas id="cmpExcess"></canvas></div>
    </section>
  </main>
</div>
<script>
const PAYLOAD = {data_json};
let charts = {{}};

function defaultCfg() {{
  return {{ short: 5, long: 15, capital: 100000, comm: 0.0003, slip: 0.0001 }};
}}

function getState() {{
  const sym = document.getElementById('stockSel').value;
  return {{
    symbol: sym,
    item: PAYLOAD.backtests[sym],
    comparison: PAYLOAD.comparison.filter(r => r.symbol === sym || true),
  }};
}}

function fmtPct(v, signed=true) {{
  const s = signed && v > 0 ? '+' : '';
  return s + v.toFixed(2) + '%';
}}

function renderKPI(m) {{
  const el = document.getElementById('kpiGrid');
  el.innerHTML = '';
  const cards = [
    ['年化收益率', fmtPct(m.annualized_return), '回测基准 ' + fmtPct(m.benchmark_annualized), m.annualized_return >= 0 ? 'pos' : 'neg'],
    ['夏普比率', m.sharpe_ratio.toFixed(3), m.sharpe_ratio >= 1 ? '较好' : '中等', ''],
    ['最大回撤', m.max_drawdown.toFixed(2) + '%', m.max_dd_start + ' ~ ' + m.max_dd_end, 'neg'],
    ['胜率', m.win_rate.toFixed(1) + '%', m.trade_count + ' 笔交易，盈亏比 ' + m.profit_loss_ratio, ''],
  ];
  cards.forEach(([label, value, hint, cls]) => {{
    el.insertAdjacentHTML('beforeend',
      `<div class="kpi"><div class="label">${{label}}</div><div class="value ${{cls}}">${{value}}</div><div class="hint">${{hint}}</div></div>`);
  }});
}}

function destroyChart(key) {{ if (charts[key]) {{ charts[key].destroy(); charts[key] = null; }} }}

function renderCharts(item) {{
  const c = item.charts, m = item.metrics;
  renderKPI(m);
  document.getElementById('diagText').textContent = item.diagnostic_text;

  const common = {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 8, font: {{ size: 10 }} }}, grid: {{ display: false }} }},
      y: {{ ticks: {{ font: {{ size: 10 }} }}, grid: {{ color: '#f1f5f9' }} }}
    }}
  }};

  destroyChart('equity');
  charts.equity = new Chart(document.getElementById('equityChart'), {{
    type: 'line',
    data: {{
      labels: c.dates,
      datasets: [
        {{ label: '策略净值', data: c.strategy_nv, borderColor: '#dc2626', backgroundColor: 'rgba(220,38,38,.08)', fill: true, pointRadius: 0, borderWidth: 2 }},
        {{ label: '买入持有', data: c.benchmark_nv, borderColor: '#94a3b8', pointRadius: 0, borderWidth: 1.5 }},
      ]
    }},
    options: common
  }});

  destroyChart('dd');
  charts.dd = new Chart(document.getElementById('ddChart'), {{
    type: 'line',
    data: {{
      labels: c.dates,
      datasets: [{{ label: '回撤%', data: c.drawdown_pct, borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,.15)', fill: true, pointRadius: 0 }}]
    }},
    options: common
  }});

  destroyChart('price');
  const buyMap = Object.fromEntries(c.buy_dates.map((d,i)=>[d,c.buy_prices[i]]));
  const sellMap = Object.fromEntries(c.sell_dates.map((d,i)=>[d,c.sell_prices[i]]));
  charts.price = new Chart(document.getElementById('priceChart'), {{
    type: 'line',
    data: {{
      labels: c.dates,
      datasets: [
        {{ label: '收盘价', data: c.close, borderColor: '#f97316', pointRadius: 0, borderWidth: 1.5 }},
        {{ label: 'SMA短', data: c.sma_short, borderColor: '#38bdf8', pointRadius: 0, borderWidth: 1 }},
        {{ label: 'SMA长', data: c.sma_long, borderColor: '#1d4ed8', pointRadius: 0, borderWidth: 1 }},
        {{ label: '买入', data: c.dates.map(d => buyMap[d] ?? null), pointStyle: 'triangle', pointRadius: 6, pointBackgroundColor: '#dc2626', showLine: false }},
        {{ label: '卖出', data: c.dates.map(d => sellMap[d] ?? null), pointStyle: 'triangle', rotation: 180, pointRadius: 6, pointBackgroundColor: '#16a34a', showLine: false }},
      ]
    }},
    options: common
  }});
}}

function renderComparison(all) {{
  // 默认展示 SMA(5/15) 各股票对比
  const base = all.filter(r => r.short_ma === 5 && r.long_ma === 15);
  const labels = base.map(r => r.name);
  const barCommon = {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ ticks: {{ font: {{ size: 10 }} }} }}, y: {{ grid: {{ color: '#f1f5f9' }} }} }}
  }};
  const color = (vals) => vals.map(v => v >= 0 ? '#dc2626' : '#16a34a');

  destroyChart('cmpAnn');
  charts.cmpAnn = new Chart(document.getElementById('cmpAnn'), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label: '年化收益%', data: base.map(r=>r.annualized_return), backgroundColor: color(base.map(r=>r.annualized_return)) }}] }},
    options: {{ ...barCommon, plugins: {{ ...barCommon.plugins, title: {{ display: true, text: '年化收益率 (%)' }} }} }}
  }});
  destroyChart('cmpSharpe');
  charts.cmpSharpe = new Chart(document.getElementById('cmpSharpe'), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label: '夏普', data: base.map(r=>r.sharpe_ratio), backgroundColor: '#2563eb' }}] }},
    options: {{ ...barCommon, plugins: {{ ...barCommon.plugins, title: {{ display: true, text: '夏普比率' }} }} }}
  }});
  destroyChart('cmpMdd');
  charts.cmpMdd = new Chart(document.getElementById('cmpMdd'), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label: 'MDD%', data: base.map(r=>Math.abs(r.max_drawdown)), backgroundColor: '#16a34a' }}] }},
    options: {{ ...barCommon, plugins: {{ ...barCommon.plugins, title: {{ display: true, text: '最大回撤 (%)' }} }} }}
  }});
  destroyChart('cmpExcess');
  const all515 = all.filter(r => r.short_ma === 5 && r.long_ma === 15);
  charts.cmpExcess = new Chart(document.getElementById('cmpExcess'), {{
    type: 'bar',
    data: {{
      labels: all515.map(r => r.name),
      datasets: [{{ label: '超额收益%', data: all515.map(r=>r.excess_return), backgroundColor: color(all515.map(r=>r.excess_return)) }}]
    }},
    options: {{ ...barCommon, plugins: {{ ...barCommon.plugins, title: {{ display: true, text: '相对买入持有的超额收益 (%) — SMA(5/15)' }} }} }}
  }});
}}

function initSelectors() {{
  const sel = document.getElementById('stockSel');
  PAYLOAD.stock_list.forEach(s => {{
    sel.insertAdjacentHTML('beforeend', `<option value="${{s.symbol}}">${{s.name}} (${{s.ts_code}})</option>`);
  }});
  sel.value = '002202';
  const item = PAYLOAD.backtests['002202'];
  document.getElementById('startDate').value = item.charts.dates[0];
  document.getElementById('endDate').value = item.charts.dates[item.charts.dates.length-1];
}}

function bindEvents() {{
  document.getElementById('shortMa').oninput = e => document.getElementById('shortVal').textContent = e.target.value;
  document.getElementById('longMa').oninput = e => document.getElementById('longVal').textContent = e.target.value;
  document.getElementById('stockSel').onchange = () => renderCharts(PAYLOAD.backtests[document.getElementById('stockSel').value]);
  document.getElementById('resetBtn').onclick = () => {{
    document.getElementById('shortMa').value = 5; document.getElementById('longMa').value = 15;
    document.getElementById('shortVal').textContent = '5'; document.getElementById('longVal').textContent = '15';
    document.getElementById('capital').value = 100000;
    document.getElementById('useComm').checked = true; document.getElementById('useSlip').checked = true;
  }};
  document.getElementById('applyBtn').onclick = () => {{
    alert('参数变更需重新运行 build_dashboard.py 生成数据。当前看板展示服务端预计算结果，切换股票即可查看。');
  }};
}}

initSelectors();
renderCharts(PAYLOAD.backtests['002202']);
renderComparison(PAYLOAD.comparison);
bindEvents();
</script>
</body>
</html>"""


def main() -> None:
    stock_data = load_or_fetch()
    default_cfg = BacktestConfig(short_window=5, long_window=15)

    backtests = {}
    for symbol, df in stock_data.items():
        backtests[symbol] = serialize_backtest(symbol, df, default_cfg)
        print(f"回测完成: {STOCKS[symbol]['name']} 年化={backtests[symbol]['metrics']['annualized_return']}%")

    comparison = build_comparison(stock_data)
    payload = {
        "stock_list": [{"symbol": s, "name": STOCKS[s]["name"], "ts_code": STOCKS[s]["ts_code"]} for s in STOCKS],
        "backtests": backtests,
        "comparison": comparison,
    }
    OUT_HTML.write_text(render_html(payload), encoding="utf-8")
    (ROOT / "output" / "comparison.json").parent.mkdir(exist_ok=True)
    (ROOT / "output" / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"html={OUT_HTML}")
    print(f"pages={PAGES_URL}")


if __name__ == "__main__":
    main()
