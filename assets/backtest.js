/* 浏览器端双均线回测引擎 — 与 src/backtest.py 逻辑一致 */

function rollingMean(arr, window) {
  const out = new Array(arr.length).fill(null);
  for (let i = window - 1; i < arr.length; i++) {
    let s = 0;
    for (let j = i - window + 1; j <= i; j++) s += arr[j];
    out[i] = s / window;
  }
  return out;
}

function filterRows(rows, start, end) {
  return rows.filter(r => r.d >= start && r.d <= end);
}

function computeSignals(closes, shortW, longW) {
  const smaShort = rollingMean(closes, shortW);
  const smaLong = rollingMean(closes, longW);
  const n = closes.length;
  const position = new Array(n).fill(0);
  const buySignal = new Array(n).fill(0);
  const sellSignal = new Array(n).fill(0);

  let prev = 0;
  for (let i = 0; i < n; i++) {
    if (smaShort[i] == null || smaLong[i] == null) {
      position[i] = prev;
      continue;
    }
    let pos = prev;
    if (smaShort[i] > smaLong[i]) pos = 1;
    else if (smaShort[i] < smaLong[i]) pos = 0;
    position[i] = pos;
    const chg = pos - prev;
    if (chg === 1) buySignal[i] = 1;
    if (chg === -1) sellSignal[i] = 1;
    prev = pos;
  }
  return { smaShort, smaLong, position, buySignal, sellSignal };
}

function runBacktest(rows, cfg) {
  const { shortW, longW, capital, commission, slippage, positionRatio } = cfg;
  const closes = rows.map(r => r.c);
  const dates = rows.map(r => r.d);
  const sig = computeSignals(closes, shortW, longW);

  let startIdx = 0;
  for (let i = 0; i < closes.length; i++) {
    if (sig.smaShort[i] != null && sig.smaLong[i] != null) { startIdx = i; break; }
  }

  let cash = capital;
  let shares = 0;
  const trades = [];
  const strategyNv = [];
  const drawdownPct = [];
  const buyCost = 1 + commission + slippage;
  const sellCost = 1 - commission - slippage;
  const firstClose = closes[startIdx];

  for (let i = startIdx; i < rows.length; i++) {
    const price = closes[i];
    const pos = sig.position[i];

    if (pos === 1 && shares === 0) {
      const budget = cash * positionRatio;
      const execPrice = price * buyCost;
      const qty = Math.floor(budget / execPrice);
      if (qty > 0) {
        cash -= qty * execPrice;
        shares = qty;
        trades.push({ action: 'BUY', idx: i, price, execPrice, qty });
      }
    } else if (pos === 0 && shares > 0) {
      const execPrice = price * sellCost;
      cash += shares * execPrice;
      trades.push({ action: 'SELL', idx: i, price, execPrice, qty: shares });
      shares = 0;
    }

    const equity = cash + shares * price;
    strategyNv.push(equity / capital);
  }

  if (shares > 0) {
    const last = rows.length - 1;
    const execPrice = closes[last] * sellCost;
    cash += shares * execPrice;
    trades.push({ action: 'SELL', idx: last, price: closes[last], execPrice, qty: shares });
    shares = 0;
    strategyNv[strategyNv.length - 1] = cash / capital;
  }

  const sliceDates = dates.slice(startIdx);
  const sliceCloses = closes.slice(startIdx);
  const benchmarkNv = sliceCloses.map(c => c / firstClose);

  let peak = strategyNv[0] || 1;
  for (let i = 0; i < strategyNv.length; i++) {
    peak = Math.max(peak, strategyNv[i]);
    drawdownPct.push((strategyNv[i] / peak - 1) * 100);
  }

  const metrics = computeMetrics(strategyNv, benchmarkNv, trades, sliceDates.length);
  const buyDates = [], buyPrices = [], sellDates = [], sellPrices = [];
  for (let i = startIdx; i < rows.length; i++) {
    if (sig.buySignal[i]) { buyDates.push(dates[i]); buyPrices.push(closes[i]); }
    if (sig.sellSignal[i]) { sellDates.push(dates[i]); sellPrices.push(closes[i]); }
  }

  return {
    dates: sliceDates,
    close: sliceCloses,
    smaShort: sig.smaShort.slice(startIdx),
    smaLong: sig.smaLong.slice(startIdx),
    strategyNv,
    benchmarkNv,
    drawdownPct,
    buyDates, buyPrices, sellDates, sellPrices,
    metrics,
  };
}

function computeMetrics(strategyNv, benchmarkNv, trades, nDays) {
  const years = Math.max(nDays / 252, 1 / 252);
  const finalNv = strategyNv[strategyNv.length - 1] || 1;
  const benchFinal = benchmarkNv[benchmarkNv.length - 1] || 1;

  const cumReturn = (finalNv - 1) * 100;
  const annReturn = (Math.pow(finalNv, 1 / years) - 1) * 100;
  const benchCum = (benchFinal - 1) * 100;
  const benchAnn = (Math.pow(benchFinal, 1 / years) - 1) * 100;

  let maxDd = 0, peak = strategyNv[0] || 1;
  let ddStart = 0, ddEnd = 0, ddPeakIdx = 0;
  for (let i = 0; i < strategyNv.length; i++) {
    if (strategyNv[i] > peak) { peak = strategyNv[i]; ddPeakIdx = i; }
    const dd = strategyNv[i] / peak - 1;
    if (dd < maxDd) { maxDd = dd; ddEnd = i; ddStart = ddPeakIdx; }
  }

  const dailyRet = [];
  for (let i = 1; i < strategyNv.length; i++) {
    dailyRet.push(strategyNv[i] / strategyNv[i - 1] - 1);
  }
  const rf = 0.02 / 252;
  const mean = dailyRet.reduce((a, b) => a + b, 0) / (dailyRet.length || 1);
  const std = Math.sqrt(dailyRet.reduce((a, b) => a + (b - mean) ** 2, 0) / (dailyRet.length || 1));
  const sharpe = std > 0 ? ((mean - rf) / std) * Math.sqrt(252) : 0;

  const sells = trades.filter(t => t.action === 'SELL');
  const buys = trades.filter(t => t.action === 'BUY');
  let wins = 0, winSum = 0, lossSum = 0, lossCnt = 0;
  for (let i = 0; i < sells.length; i++) {
    if (i < buys.length) {
      const pnl = (sells[i].execPrice - buys[i].execPrice) / buys[i].execPrice;
      if (pnl >= 0) { wins++; winSum += pnl; } else { lossSum += Math.abs(pnl); lossCnt++; }
    }
  }
  const winRate = sells.length ? (wins / sells.length) * 100 : 0;
  const plr = lossCnt > 0 ? (winSum / wins || 0) / (lossSum / lossCnt) : 0;

  return {
    cumulative_return: round(cumReturn, 2),
    annualized_return: round(annReturn, 2),
    max_drawdown: round(maxDd * 100, 2),
    sharpe_ratio: round(sharpe, 3),
    win_rate: round(winRate, 1),
    trade_count: sells.length,
    profit_loss_ratio: round(plr, 2),
    benchmark_cumulative: round(benchCum, 2),
    benchmark_annualized: round(benchAnn, 2),
    excess_return: round(cumReturn - benchCum, 2),
    max_dd_start: '', max_dd_end: '',
  };
}

function round(v, d) {
  const f = Math.pow(10, d);
  return Math.round(v * f) / f;
}

function readCfg() {
  const shortW = parseInt(document.getElementById('shortMa').value, 10);
  const longW = parseInt(document.getElementById('longMa').value, 10);
  return {
    shortW,
    longW,
    capital: parseFloat(document.getElementById('capital').value) || 100000,
    commission: document.getElementById('useComm').checked ? 0.0003 : 0,
    slippage: document.getElementById('useSlip').checked ? 0.0001 : 0,
    positionRatio: 1.0,
    start: document.getElementById('startDate').value,
    end: document.getElementById('endDate').value,
  };
}

function backtestStock(symbol, cfg) {
  const meta = PAYLOAD.quotes[symbol];
  const rows = filterRows(meta.rows, cfg.start, cfg.end);
  if (rows.length < cfg.longW + 1) throw new Error('数据不足');
  if (cfg.shortW >= cfg.longW) throw new Error('短期均线必须小于长期均线');
  const result = runBacktest(rows, cfg);
  return { ...result, name: meta.name, ts_code: meta.ts_code, diagnostic_text: meta.diagnostic_text };
}

function fmtPct(v, signed = true) {
  const s = signed && v > 0 ? '+' : '';
  return s + v.toFixed(2) + '%';
}

let charts = {};

function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); charts[key] = null; }
}

function renderKPI(m) {
  const el = document.getElementById('kpiGrid');
  el.innerHTML = '';
  const cards = [
    ['年化收益率', fmtPct(m.annualized_return), '回测基准 ' + fmtPct(m.benchmark_annualized), m.annualized_return >= 0 ? 'pos' : 'neg'],
    ['夏普比率', m.sharpe_ratio.toFixed(3), m.sharpe_ratio >= 1 ? '较好' : '中等', ''],
    ['最大回撤', m.max_drawdown.toFixed(2) + '%', '相对历史最高净值', 'neg'],
    ['胜率', m.win_rate.toFixed(1) + '%', m.trade_count + ' 笔交易，盈亏比 ' + m.profit_loss_ratio, ''],
  ];
  cards.forEach(([label, value, hint, cls]) => {
    el.insertAdjacentHTML('beforeend',
      `<div class="kpi"><div class="label">${label}</div><div class="value ${cls}">${value}</div><div class="hint">${hint}</div></div>`);
  });
}

function renderMainCharts(item) {
  renderKPI(item.metrics);
  document.getElementById('diagText').textContent = item.diagnostic_text;

  const common = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } } },
    scales: {
      x: { ticks: { maxTicksLimit: 8, font: { size: 10 } }, grid: { display: false } },
      y: { ticks: { font: { size: 10 } }, grid: { color: '#f1f5f9' } },
    },
  };

  destroyChart('equity');
  charts.equity = new Chart(document.getElementById('equityChart'), {
    type: 'line',
    data: {
      labels: item.dates,
      datasets: [
        { label: '策略净值', data: item.strategyNv, borderColor: '#dc2626', backgroundColor: 'rgba(220,38,38,.08)', fill: true, pointRadius: 0, borderWidth: 2 },
        { label: '买入持有', data: item.benchmarkNv, borderColor: '#94a3b8', pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: common,
  });

  destroyChart('dd');
  charts.dd = new Chart(document.getElementById('ddChart'), {
    type: 'line',
    data: {
      labels: item.dates,
      datasets: [{ label: '回撤%', data: item.drawdownPct, borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,.15)', fill: true, pointRadius: 0 }],
    },
    options: common,
  });

  const buyMap = Object.fromEntries(item.buyDates.map((d, i) => [d, item.buyPrices[i]]));
  const sellMap = Object.fromEntries(item.sellDates.map((d, i) => [d, item.sellPrices[i]]));
  destroyChart('price');
  charts.price = new Chart(document.getElementById('priceChart'), {
    type: 'line',
    data: {
      labels: item.dates,
      datasets: [
        { label: '收盘价', data: item.close, borderColor: '#f97316', pointRadius: 0, borderWidth: 1.5 },
        { label: 'SMA短', data: item.smaShort, borderColor: '#38bdf8', pointRadius: 0, borderWidth: 1 },
        { label: 'SMA长', data: item.smaLong, borderColor: '#1d4ed8', pointRadius: 0, borderWidth: 1 },
        { label: '买入', data: item.dates.map(d => buyMap[d] ?? null), pointStyle: 'triangle', pointRadius: 6, pointBackgroundColor: '#dc2626', showLine: false },
        { label: '卖出', data: item.dates.map(d => sellMap[d] ?? null), pointStyle: 'triangle', rotation: 180, pointRadius: 6, pointBackgroundColor: '#16a34a', showLine: false },
      ],
    },
    options: common,
  });
}

function renderComparison(cfg) {
  const results = PAYLOAD.stock_list.map(s => {
    try {
      const r = backtestStock(s.symbol, cfg);
      return { name: s.name, ...r.metrics };
    } catch { return null; }
  }).filter(Boolean);

  const labels = results.map(r => r.name);
  const barCommon = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { x: { ticks: { font: { size: 10 } } }, y: { grid: { color: '#f1f5f9' } } },
  };
  const color = vals => vals.map(v => v >= 0 ? '#dc2626' : '#16a34a');

  destroyChart('cmpAnn');
  charts.cmpAnn = new Chart(document.getElementById('cmpAnn'), {
    type: 'bar',
    data: { labels, datasets: [{ data: results.map(r => r.annualized_return), backgroundColor: color(results.map(r => r.annualized_return)) }] },
    options: { ...barCommon, plugins: { ...barCommon.plugins, title: { display: true, text: `年化收益率 (%) — SMA(${cfg.shortW}/${cfg.longW})` } } },
  });
  destroyChart('cmpSharpe');
  charts.cmpSharpe = new Chart(document.getElementById('cmpSharpe'), {
    type: 'bar',
    data: { labels, datasets: [{ data: results.map(r => r.sharpe_ratio), backgroundColor: '#2563eb' }] },
    options: { ...barCommon, plugins: { ...barCommon.plugins, title: { display: true, text: '夏普比率' } } },
  });
  destroyChart('cmpMdd');
  charts.cmpMdd = new Chart(document.getElementById('cmpMdd'), {
    type: 'bar',
    data: { labels, datasets: [{ data: results.map(r => Math.abs(r.max_drawdown)), backgroundColor: '#16a34a' }] },
    options: { ...barCommon, plugins: { ...barCommon.plugins, title: { display: true, text: '最大回撤 (%)' } } },
  });
  destroyChart('cmpExcess');
  charts.cmpExcess = new Chart(document.getElementById('cmpExcess'), {
    type: 'bar',
    data: { labels, datasets: [{ data: results.map(r => r.excess_return), backgroundColor: color(results.map(r => r.excess_return)) }] },
    options: { ...barCommon, plugins: { ...barCommon.plugins, title: { display: true, text: '相对买入持有的超额收益 (%)' } } },
  });
}

function applyParams() {
  try {
    const cfg = readCfg();
    const sym = document.getElementById('stockSel').value;
    renderMainCharts(backtestStock(sym, cfg));
    renderComparison(cfg);
  } catch (e) {
    alert(e.message || String(e));
  }
}

function initDashboard() {
  const sel = document.getElementById('stockSel');
  PAYLOAD.stock_list.forEach(s => {
    sel.insertAdjacentHTML('beforeend', `<option value="${s.symbol}">${s.name} (${s.ts_code})</option>`);
  });
  sel.value = '002202';
  const rows = PAYLOAD.quotes['002202'].rows;
  document.getElementById('startDate').value = rows[0].d;
  document.getElementById('endDate').value = rows[rows.length - 1].d;

  document.getElementById('shortMa').oninput = e => document.getElementById('shortVal').textContent = e.target.value;
  document.getElementById('longMa').oninput = e => document.getElementById('longVal').textContent = e.target.value;
  document.getElementById('applyBtn').onclick = applyParams;
  document.getElementById('resetBtn').onclick = () => {
    document.getElementById('shortMa').value = 5;
    document.getElementById('longMa').value = 15;
    document.getElementById('shortVal').textContent = '5';
    document.getElementById('longVal').textContent = '15';
    document.getElementById('capital').value = 100000;
    document.getElementById('useComm').checked = true;
    document.getElementById('useSlip').checked = true;
    applyParams();
  };
  sel.onchange = () => {
    const r = PAYLOAD.quotes[sel.value].rows;
    document.getElementById('startDate').value = r[0].d;
    document.getElementById('endDate').value = r[r.length - 1].d;
    applyParams();
  };
  ['shortMa', 'longMa', 'startDate', 'endDate', 'capital', 'useComm', 'useSlip'].forEach(id => {
    document.getElementById(id).addEventListener('change', applyParams);
  });

  applyParams();
}

document.addEventListener('DOMContentLoaded', initDashboard);
