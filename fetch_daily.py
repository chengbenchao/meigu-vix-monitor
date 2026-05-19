#!/usr/bin/env python3
"""
Hybrid data fetcher for VIX Monitor.
- yfinance: daily updates (T-1, fast) — 最新数据
- FRED API: historical backfill (legitimate, complete) — 历史底仓

Cron runs this daily; yfinance gets latest, FRED fills any gaps.
"""
import sqlite3, os, json, urllib.request, sys
from datetime import datetime, timedelta

DB_PATH = "/var/lib/meigu/vix.db"
FRED_KEY = os.environ.get("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ── yfinance (daily latest) ──
YF_SYMBOLS = {"^VIX": "vix_daily", "^GSPC": "spx_daily", "^NDX": "ndx_daily"}

def yf_fetch():
    """Fetch latest data from yfinance. Returns total new rows."""
    import yfinance as yf
    conn = sqlite3.connect(DB_PATH)
    total = 0
    for symbol, table in YF_SYMBOLS.items():
        try:
            df = yf.download(symbol, period="5d", interval="1d", progress=False)
            if df.empty:
                print(f"  [yf:{symbol}] no data")
                continue
            new = 0
            for idx, row in df.iterrows():
                d = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
                c = float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close'])
                existing = conn.execute(f"SELECT 1 FROM {table} WHERE date=?", (d,)).fetchone()
                if not existing:
                    conn.execute(f"INSERT OR REPLACE INTO {table}(date,close) VALUES(?,?)", (d, c))
                    new += 1
            print(f"  [yf:{symbol}] {new} new rows")
            total += new
        except Exception as e:
            print(f"  [yf:{symbol}] ERROR: {e}")
    conn.commit(); conn.close()
    return total

# ── FRED (historical backfill) ──
FRED_SERIES = {"vix_daily": "VIXCLS", "spx_daily": "SP500", "ndx_daily": "NASDAQ100"}

def fred_fetch(series_id, start_date):
    """Fetch observations from FRED API since start_date."""
    url = (f"{FRED_BASE}?series_id={series_id}&api_key={FRED_KEY}"
           f"&file_type=json&observation_start={start_date}"
           f"&sort_order=asc&limit=100000")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return [(obs["date"], float(obs["value"])) for obs in data.get("observations", [])
            if obs["value"] != "."]

def fred_backfill():
    """Backfill any missing historical dates from FRED."""
    conn = sqlite3.connect(DB_PATH)
    total = 0
    for table, series_id in FRED_SERIES.items():
        # Find earliest date in DB that we might need to backfill
        earliest = conn.execute(f"SELECT MIN(date) FROM {table}").fetchone()
        if not earliest or not earliest[0]:
            earliest_date = "1990-01-01"
        else:
            earliest_date = earliest[0]

        # Get all FRED data from the earliest DB date
        print(f"  [fred:{series_id}] backfill from {earliest_date}...", end=" ")
        sys.stdout.flush()
        try:
            rows = fred_fetch(series_id, earliest_date)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        existing = set(r[0] for r in conn.execute(
            f"SELECT date FROM {table} WHERE date >= ?", (earliest_date,)
        ).fetchall())
        new_rows = [(d, v) for d, v in rows if d not in existing]

        if new_rows:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table}(date,close) VALUES(?,?)", new_rows
            )
            print(f"{len(new_rows)} new rows")
            total += len(new_rows)
        else:
            print("up to date")
    conn.commit(); conn.close()
    return total


def main():
    print("=" * 50)
    print(f"VIX Monitor 数据抓取 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Step 1: yfinance for latest data (fast, T-1)
    print("\n📡 yfinance (最新数据):")
    yf_total = yf_fetch()

    # Step 2: FRED for historical backfill (fills any gaps)
    print("\n🏛️  FRED (历史底仓):")
    fred_total = fred_backfill()

    # Summary
    conn = sqlite3.connect(DB_PATH)
    counts = {}
    for t in ["vix_daily", "spx_daily", "ndx_daily"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        latest = conn.execute(f"SELECT MAX(date) FROM {t}").fetchone()[0]
        counts[t] = (n, latest)
    conn.close()

    print(f"\n📊 数据库状态:")
    for t, (n, latest) in counts.items():
        print(f"  {t}: {n} rows, latest={latest}")
    print(f"\n✅ Done. yfinance +{yf_total} | FRED +{fred_total} | 总计 {sum(c[0] for c in counts.values())} rows")
    return yf_total + fred_total

if __name__ == "__main__":
    main()
