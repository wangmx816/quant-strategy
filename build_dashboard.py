#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成双均线策略回测 HTML 看板（浏览器端实时回测）。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from src.data_fetch import DATA_DIR, STOCKS, fetch_all
from src.diagnostics import diagnose, format_diagnostic_text

ROOT = Path(__file__).resolve().parent
OUT_HTML = ROOT / "index.html"
OUT_ASSETS = ROOT / "assets"
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


def build_payload(stock_data: dict[str, pd.DataFrame]) -> dict:
    quotes = {}
    for symbol, df in stock_data.items():
        rows = [
            {"d": r["trade_date"].strftime("%Y-%m-%d"), "c": round(float(r["close"]), 4)}
            for _, r in df.iterrows()
        ]
        quotes[symbol] = {
            "name": STOCKS[symbol]["name"],
            "ts_code": STOCKS[symbol]["ts_code"],
            "diagnostic_text": format_diagnostic_text(diagnose(df, symbol)),
            "rows": rows,
        }
    return {
        "stock_list": [
            {"symbol": s, "name": STOCKS[s]["name"], "ts_code": STOCKS[s]["ts_code"]}
            for s in STOCKS
        ],
        "quotes": quotes,
    }


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
    .badge {{ font-size: .75rem; background: #dcfce7; color: #166534; padding: 3px 8px; border-radius: 999px; }}
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
    <div class="sub">TASK3 · Quant Strategy <span class="badge">实时回测</span></div>
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
      <div class="cap">参数变更后浏览器即时重算，无需重新运行 Python。</div>
      <div class="chart-h"><canvas id="equityChart"></canvas></div>
    </section>
    <section class="row2">
      <div class="panel">
        <h2>图2 回撤（%）</h2>
        <div class="cap">相对历史最高净值的回撤幅度。</div>
        <div class="chart-m"><canvas id="ddChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>图3 价格 + 均线 + 买卖点</h2>
        <div class="cap">金叉买入，死叉卖出。</div>
        <div class="chart-m"><canvas id="priceChart"></canvas></div>
      </div>
    </section>
    <section class="panel">
      <h2>图4 多股票对比（当前参数）</h2>
      <div class="cap">五只股票在相同均线参数下的指标对比，随参数调整同步更新。</div>
      <div class="compare-grid">
        <div class="chart-m"><canvas id="cmpAnn"></canvas></div>
        <div class="chart-m"><canvas id="cmpSharpe"></canvas></div>
        <div class="chart-m"><canvas id="cmpMdd"></canvas></div>
      </div>
      <div class="chart-m" style="margin-top:14px"><canvas id="cmpExcess"></canvas></div>
    </section>
  </main>
</div>
<script>const PAYLOAD = {data_json};</script>
<script src="assets/backtest.js"></script>
</body>
</html>"""


def main() -> None:
    stock_data = load_or_fetch()
    payload = build_payload(stock_data)
    OUT_HTML.write_text(render_html(payload), encoding="utf-8")
    OUT_ASSETS.mkdir(parents=True, exist_ok=True)
    src_js = ROOT / "assets" / "backtest.js"
    if src_js.exists():
        shutil.copy2(src_js, OUT_ASSETS / "backtest.js")
    print(f"html={OUT_HTML}")
    print(f"pages={PAGES_URL}")
    print("模式: 浏览器端实时回测")


if __name__ == "__main__":
    main()
