#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""双均线策略：信号生成、模拟交易与回测指标计算。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    short_window: int = 5
    long_window: int = 15
    initial_capital: float = 100_000.0
    commission: float = 0.0003  # 万三
    slippage: float = 0.0001  # 万一
    position_ratio: float = 1.0  # 1.0=全仓, 0.5=固定50%


def compute_ma_signals(
    df: pd.DataFrame,
    short_window: int = 5,
    long_window: int = 15,
) -> pd.DataFrame:
    out = df.copy().sort_values("trade_date").reset_index(drop=True)
    out["sma_short"] = out["close"].rolling(short_window).mean()
    out["sma_long"] = out["close"].rolling(long_window).mean()

    # position: 1=持有多头, 0=空仓
    out["position"] = 0
    out.loc[out["sma_short"] > out["sma_long"], "position"] = 1
    out.loc[out["sma_short"] < out["sma_long"], "position"] = 0
    out["position"] = out["position"].ffill().fillna(0).astype(int)

    # 金叉/死叉：position 变化日
    out["signal_change"] = out["position"].diff().fillna(0)
    out["buy_signal"] = (out["signal_change"] == 1).astype(int)
    out["sell_signal"] = (out["signal_change"] == -1).astype(int)
    return out


def run_backtest(df: pd.DataFrame, cfg: BacktestConfig | None = None) -> dict[str, Any]:
    cfg = cfg or BacktestConfig()
    data = compute_ma_signals(df, cfg.short_window, cfg.long_window)
    data = data.dropna(subset=["sma_short", "sma_long"]).reset_index(drop=True)
    if data.empty:
        raise ValueError("有效数据不足，无法回测")

    cash = cfg.initial_capital
    shares = 0.0
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    for i, row in data.iterrows():
        price = float(row["close"])
        pos = int(row["position"])
        buy_cost_rate = 1 + cfg.commission + cfg.slippage
        sell_cost_rate = 1 - cfg.commission - cfg.slippage

        if pos == 1 and shares == 0:
            budget = cash * cfg.position_ratio
            exec_price = price * buy_cost_rate
            qty = int(budget // exec_price)
            if qty > 0:
                cost = qty * exec_price
                cash -= cost
                shares = qty
                trades.append(
                    {
                        "trade_date": row["trade_date"],
                        "action": "BUY",
                        "price": round(price, 4),
                        "exec_price": round(exec_price, 4),
                        "qty": qty,
                        "cash_after": round(cash, 2),
                    }
                )
        elif pos == 0 and shares > 0:
            exec_price = price * sell_cost_rate
            proceeds = shares * exec_price
            trades.append(
                {
                    "trade_date": row["trade_date"],
                    "action": "SELL",
                    "price": round(price, 4),
                    "exec_price": round(exec_price, 4),
                    "qty": shares,
                    "cash_after": round(cash + proceeds, 2),
                }
            )
            cash += proceeds
            shares = 0.0

        equity = cash + shares * price
        equity_rows.append(
            {
                "trade_date": row["trade_date"],
                "equity": equity,
                "cash": cash,
                "shares": shares,
                "close": price,
                "position": pos,
            }
        )

    # 期末平仓
    if shares > 0:
        last = data.iloc[-1]
        exec_price = float(last["close"]) * (1 - cfg.commission - cfg.slippage)
        cash += shares * exec_price
        trades.append(
            {
                "trade_date": last["trade_date"],
                "action": "SELL",
                "price": round(float(last["close"]), 4),
                "exec_price": round(exec_price, 4),
                "qty": shares,
                "cash_after": round(cash, 2),
            }
        )
        equity_rows[-1]["equity"] = cash
        equity_rows[-1]["cash"] = cash
        equity_rows[-1]["shares"] = 0

    equity_df = pd.DataFrame(equity_rows)
    equity_df["net_value"] = equity_df["equity"] / cfg.initial_capital
    equity_df["drawdown"] = equity_df["net_value"] / equity_df["net_value"].cummax() - 1

    # 买入持有基准
    first_close = float(data.iloc[0]["close"])
    data["benchmark_nv"] = data["close"] / first_close

    metrics = compute_metrics(equity_df, trades, data, cfg)
    return {
        "data": data,
        "equity": equity_df,
        "trades": pd.DataFrame(trades),
        "metrics": metrics,
        "config": cfg,
    }


def compute_metrics(
    equity_df: pd.DataFrame,
    trades: list[dict[str, Any]],
    price_df: pd.DataFrame,
    cfg: BacktestConfig,
) -> dict[str, float]:
    nv = equity_df["net_value"]
    daily_ret = nv.pct_change().fillna(0)
    n_days = len(equity_df)
    years = max(n_days / 252, 1 / 252)

    cum_return = (nv.iloc[-1] - 1) * 100
    ann_return = ((nv.iloc[-1]) ** (1 / years) - 1) * 100 if nv.iloc[-1] > 0 else -100.0
    max_dd = float(equity_df["drawdown"].min() * 100)

    rf = 0.02 / 252
    excess = daily_ret - rf
    sharpe = float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0

    # 基准
    bench_nv = price_df["benchmark_nv"]
    bench_cum = (bench_nv.iloc[-1] - 1) * 100
    bench_ann = ((bench_nv.iloc[-1]) ** (1 / years) - 1) * 100 if bench_nv.iloc[-1] > 0 else -100.0
    excess_vs_bench = cum_return - bench_cum

    # 胜率与盈亏比
    sell_trades = [t for t in trades if t["action"] == "SELL"]
    buy_trades = [t for t in trades if t["action"] == "BUY"]
    wins, losses = [], []
    for i, sell in enumerate(sell_trades):
        if i < len(buy_trades):
            buy = buy_trades[i]
            pnl = (sell["exec_price"] - buy["exec_price"]) / buy["exec_price"]
            if pnl >= 0:
                wins.append(pnl)
            else:
                losses.append(abs(pnl))
    win_rate = len(wins) / len(sell_trades) * 100 if sell_trades else 0.0
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

    dd_end_idx = equity_df["drawdown"].idxmin()
    dd_start_idx = int(nv.iloc[: dd_end_idx + 1].idxmax()) if dd_end_idx >= 0 else 0

    return {
        "cumulative_return": round(cum_return, 2),
        "annualized_return": round(ann_return, 2),
        "max_drawdown": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 3),
        "win_rate": round(win_rate, 1),
        "trade_count": len(sell_trades),
        "profit_loss_ratio": round(profit_loss_ratio, 2),
        "benchmark_cumulative": round(bench_cum, 2),
        "benchmark_annualized": round(bench_ann, 2),
        "excess_return": round(excess_vs_bench, 2),
        "final_net_value": round(float(nv.iloc[-1]), 4),
        "max_dd_start": equity_df.iloc[dd_start_idx]["trade_date"].strftime("%Y-%m-%d"),
        "max_dd_end": equity_df.iloc[dd_end_idx]["trade_date"].strftime("%Y-%m-%d"),
    }


def run_multi_experiments(
    stock_data: dict[str, pd.DataFrame],
    ma_pairs: list[tuple[int, int]] | None = None,
) -> pd.DataFrame:
    ma_pairs = ma_pairs or [(5, 15), (5, 20), (5, 35), (10, 30)]
    rows = []
    for symbol, df in stock_data.items():
        for short_w, long_w in ma_pairs:
            cfg = BacktestConfig(short_window=short_w, long_window=long_w)
            try:
                res = run_backtest(df, cfg)
                m = res["metrics"]
                rows.append(
                    {
                        "symbol": symbol,
                        "short_ma": short_w,
                        "long_ma": long_w,
                        "annualized_return": m["annualized_return"],
                        "sharpe_ratio": m["sharpe_ratio"],
                        "max_drawdown": m["max_drawdown"],
                        "excess_return": m["excess_return"],
                        "win_rate": m["win_rate"],
                        "trade_count": m["trade_count"],
                    }
                )
            except Exception:
                continue
    return pd.DataFrame(rows)
