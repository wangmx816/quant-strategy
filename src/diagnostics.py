#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""股价数据基础诊断：缺失值、描述统计、复权对比。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .data_fetch import STOCKS, fetch_stock


def _load_adjust_close(symbol: str, adjust: str) -> pd.DataFrame | None:
    from .data_fetch import DATA_DIR

    path = DATA_DIR / f"{symbol}_{adjust}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["trade_date"])
    return None


def _fetch_adjust_close(symbol: str, adjust: str) -> float | None:
    cached = _load_adjust_close(symbol, adjust)
    if cached is not None and not cached.empty:
        return float(cached.iloc[-1]["close"])
    try:
        return float(fetch_stock(symbol, adjust).iloc[-1]["close"])
    except Exception:
        return None


def diagnose(df: pd.DataFrame, symbol: str, fetch_adjust: bool = False) -> dict[str, Any]:
    name = STOCKS[symbol]["name"]
    desc_cols = ["open", "high", "low", "close", "volume", "pct_chg"]
    desc = df[desc_cols].describe().round(4)

    missing = df.isnull().sum()
    dup_dates = int(df["trade_date"].duplicated().sum())
    zero_vol = int((df["volume"] == 0).sum())
    neg_price = int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())

    last = df["trade_date"].max()
    q_close = _fetch_adjust_close(symbol, "qfq") if fetch_adjust else float(df.iloc[-1]["close"])
    h_close = _fetch_adjust_close(symbol, "hfq") if fetch_adjust else None
    n_close = _fetch_adjust_close(symbol, "none") if fetch_adjust else None
    if h_close is None:
        h_close = q_close
    if n_close is None:
        n_close = q_close

    return {
        "symbol": symbol,
        "name": name,
        "ts_code": STOCKS[symbol]["ts_code"],
        "rows": len(df),
        "start": df["trade_date"].min().strftime("%Y-%m-%d"),
        "end": df["trade_date"].max().strftime("%Y-%m-%d"),
        "missing": missing.to_dict(),
        "total_missing": int(missing.sum()),
        "dup_dates": dup_dates,
        "zero_volume_days": zero_vol,
        "neg_price_days": neg_price,
        "describe": desc.to_dict(),
        "adjust_compare": {
            "date": last.strftime("%Y-%m-%d"),
            "qfq_close": round(q_close, 2),
            "hfq_close": round(h_close, 2),
            "none_close": round(n_close, 2),
        },
        "return_stats": {
            "mean_pct": round(float(df["pct_chg"].mean()), 4),
            "std_pct": round(float(df["pct_chg"].std()), 4),
            "max_pct": round(float(df["pct_chg"].max()), 4),
            "min_pct": round(float(df["pct_chg"].min()), 4),
            "positive_days": int((df["pct_chg"] > 0).sum()),
            "negative_days": int((df["pct_chg"] < 0).sum()),
        },
    }


def format_diagnostic_text(d: dict[str, Any]) -> str:
    adj = d["adjust_compare"]
    rs = d["return_stats"]
    return (
        f"{d['name']}（{d['ts_code']}）共 {d['rows']} 个交易日（{d['start']} 至 {d['end']}）。"
        f"缺失值合计 {d['total_missing']} 个，重复日期 {d['dup_dates']} 个，"
        f"零成交量日 {d['zero_volume_days']} 个。"
        f"日收益率均值 {rs['mean_pct']:.4f}%，标准差 {rs['std_pct']:.4f}%，"
        f"上涨日 {rs['positive_days']} 天、下跌日 {rs['negative_days']} 天。"
        f"{'复权对比（' + adj['date'] + '）：前复权收盘 ' + str(adj['qfq_close']) + ' 元，后复权 ' + str(adj['hfq_close']) + ' 元，不复权 ' + str(adj['none_close']) + ' 元。' if adj['qfq_close'] != adj['none_close'] else '当前数据为前复权（qfq）日线。'}"
        f"回测使用前复权价格，以消除除权除息对均线与收益率的扭曲；"
        f"若混用不复权数据，金叉/死叉信号可能与实际可交易价格不一致。"
    )
