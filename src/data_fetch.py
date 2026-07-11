#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过东方财富 API 获取 A 股日线数据（支持前/后/不复权）。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

END_DATE = datetime(2026, 7, 4)
START_DATE = END_DATE - timedelta(days=365)

STOCKS = {
    "002202": {"ts_code": "002202.SZ", "name": "金风科技", "market": 0},
    "600031": {"ts_code": "600031.SH", "name": "三一重工", "market": 1},
    "000425": {"ts_code": "000425.SZ", "name": "徐工机械", "market": 0},
    "600207": {"ts_code": "600207.SH", "name": "安彩高科", "market": 1},
    "000816": {"ts_code": "000816.SZ", "name": "智慧农业", "market": 0},
}

ADJUST_MAP = {"none": 0, "qfq": 1, "hfq": 2}


def _eastmoney_url(symbol: str, market: int, adjust: str = "qfq") -> str:
    fqt = ADJUST_MAP.get(adjust, 1)
    return (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&ut=7eea3edcaed734bea9cbfc24409ed989"
        f"&klt=101&fqt={fqt}&secid={market}.{symbol}"
        f"&beg={START_DATE.strftime('%Y%m%d')}&end={END_DATE.strftime('%Y%m%d')}"
    )


def fetch_via_requests(symbol: str, market: int, adjust: str = "qfq") -> pd.DataFrame:
    url = _eastmoney_url(symbol, market, adjust)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    return _parse_klines(payload, symbol, adjust)


def fetch_via_powershell(symbol: str, market: int, adjust: str = "qfq") -> pd.DataFrame:
    url = _eastmoney_url(symbol, market, adjust)
    raw_path = DATA_DIR / f"_raw_{symbol}_{adjust}.json"
    cmd = (
        f'Invoke-WebRequest -Uri "{url}" -UseBasicParsing '
        f'| Select-Object -ExpandProperty Content '
        f'| Out-File -FilePath "{raw_path}" -Encoding utf8'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    return _parse_klines(payload, symbol, adjust)


def _parse_klines(payload: dict, symbol: str, adjust: str) -> pd.DataFrame:
    info = STOCKS[symbol]
    klines = payload.get("data", {}).get("klines") or []
    rows = []
    for line in klines:
        p = line.split(",")
        rows.append(
            {
                "ts_code": info["ts_code"],
                "trade_date": pd.to_datetime(p[0]),
                "open": float(p[1]),
                "close": float(p[2]),
                "high": float(p[3]),
                "low": float(p[4]),
                "volume": float(p[5]),
                "amount": float(p[6]),
                "pct_chg": float(p[8]) if len(p) > 8 else None,
                "adjust_type": adjust,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"{symbol} 未获取到数据")
    return df.sort_values("trade_date").reset_index(drop=True)


def fetch_stock(symbol: str, adjust: str = "qfq") -> pd.DataFrame:
    info = STOCKS[symbol]
    try:
        return fetch_via_requests(symbol, info["market"], adjust)
    except Exception:
        return fetch_via_powershell(symbol, info["market"], adjust)


def fetch_all(adjust: str = "qfq") -> dict[str, pd.DataFrame]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = {}
    for symbol in STOCKS:
        df = fetch_stock(symbol, adjust)
        out = DATA_DIR / f"{symbol}_daily.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        result[symbol] = df
        print(f"  {STOCKS[symbol]['name']}({symbol}): {len(df)} 行 -> {out.name}")
    return result


if __name__ == "__main__":
    print("拉取前复权日线数据...")
    fetch_all("qfq")
