"""
美Gu恐慌指数 VIX 监控 — VIX × SPX × NDX 联动分析
"""
import sqlite3, os
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import math

import yfinance as yf
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = "/var/lib/meigu/vix.db"
STATIC_DIR = "/var/www/meigu/static"

def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS vix_daily(date TEXT PRIMARY KEY, close REAL NOT NULL, open REAL, high REAL, low REAL);
        CREATE TABLE IF NOT EXISTS spx_daily(date TEXT PRIMARY KEY, close REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS ndx_daily(date TEXT PRIMARY KEY, close REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS crisis_events(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, start_date TEXT, peak_date TEXT, peak_vix REAL, description TEXT);
        CREATE INDEX IF NOT EXISTS idx_vix_date ON vix_daily(date);
        CREATE INDEX IF NOT EXISTS idx_spx_date ON spx_daily(date);
        CREATE INDEX IF NOT EXISTS idx_ndx_date ON ndx_daily(date);
    """)
    conn.commit(); conn.close()

def _fetch_yahoo(symbol, table, years=35):
    df = yf.download(symbol, period=f"{years}y", interval="1d", progress=False)
    if df.empty: return 0
    conn = get_db(); count = 0
    for idx, row in df.iterrows():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx,'strftime') else str(idx)[:10]
        c = float(row['Close'].iloc[0]) if hasattr(row['Close'],'iloc') else float(row['Close'])
        conn.execute(f"INSERT OR REPLACE INTO {table}(date,close) VALUES(?,?)", (d,c)); count += 1
    conn.commit(); conn.close(); return count

def fetch_all():
    return {"vix":_fetch_yahoo("^VIX","vix_daily"),"spx":_fetch_yahoo("^GSPC","spx_daily"),"ndx":_fetch_yahoo("^NDX","ndx_daily")}

def seed_crisis():
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM crisis_events").fetchone()[0] > 0: conn.close(); return
    for n,s,p,v,d in [
        ("黑色星期一","1987-10-19","1987-10-19",150.19,"1987全球股市崩盘"),
        ("全球金融危机","2008-09-15","2008-10-24",89.53,"雷曼破产"),
        ("新冠疫情","2020-02-19","2020-03-16",82.69,"COVID-19"),
        ("俄罗斯违约/LTCM","1998-08-17","1998-10-08",60.63,"俄违约+LTCM"),
        ("中国股灾","2015-08-18","2015-08-24",53.29,"中国股市暴跌"),
        ("中美贸易战 2.0","2025-04-02","2025-04-08",52.33,"美对华新关税"),
        ("Volmageddon","2018-02-05","2018-02-06",50.30,"波动率ETP崩盘"),
        ("911事件","2001-09-11","2001-09-21",49.35,"恐怖袭击"),
        ("欧债危机","2011-08-01","2011-08-08",48.00,"美降级+欧债"),
        ("闪电崩盘","2010-05-06","2010-05-20",45.79,"算法闪崩"),
        ("亚洲金融危机","1997-07-02","1997-10-28",45.74,"泰铢贬值"),
        ("世通/安然","2002-06-25","2002-07-24",45.08,"企业丑闻"),
        ("互联网泡沫","2000-03-10","2000-04-14",40.67,"纳指见顶"),
        ("海湾战争","1990-08-02","1990-08-23",36.47,"伊拉克入侵"),
        ("SVB危机","2023-03-08","2023-03-13",30.81,"硅谷银行"),
        ("英国脱欧","2016-06-23","2016-06-27",25.76,"脱欧公投"),
    ]:
        conn.execute("INSERT INTO crisis_events(name,start_date,peak_date,peak_vix,description) VALUES(?,?,?,?,?)",(n,s,p,v,d))
    conn.commit(); conn.close()

# ── Stats helpers ──
def pearson(xs, ys):
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
    return round(cov/(sx*sy),3) if sx*sy>0 else 0

def linreg(pts):
    n = len(pts); xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    mx = sum(xs)/n; my = sum(ys)/n
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n)); vx = sum((x-mx)**2 for x in xs)
    slope = cov/vx if vx>0 else 0; intercept = my - slope*mx
    yp = [slope*x+intercept for x in xs]
    ss_res = sum((ys[i]-yp[i])**2 for i in range(n)); ss_tot = sum((y-my)**2 for y in ys)
    r2 = round(1 - ss_res/ss_tot, 3) if ss_tot>0 else 0
    r = pearson(xs, ys)
    xr = [min(xs), max(xs)]
    return {"slope":round(slope,1),"intercept":round(intercept,0),"r":r,"r2":r2,
            "line":[{"x":xr[0],"y":round(slope*xr[0]+intercept,0)},{"x":xr[1],"y":round(slope*xr[1]+intercept,0)}]}

def regress_from_db(sql, xcol, ycol, params=()):
    conn = get_db(); rows = conn.execute(sql, params).fetchall(); conn.close()
    if len(rows) < 3: return None
    return linreg([(r[xcol], r[ycol]) for r in rows])

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(); seed_crisis(); yield

app = FastAPI(title="VIX Monitor", lifespan=lifespan)

# ═══════════════ API ═══════════════

@app.get("/api/vix/current")
def vix_current():
    conn = get_db()
    r = conn.execute("SELECT date,close FROM vix_daily ORDER BY date DESC LIMIT 1").fetchone()
    if not r: return JSONResponse({"error":"no data"},404)
    cs = [x[0] for x in conn.execute("SELECT close FROM vix_daily WHERE close>0")]; conn.close()
    v = r["close"]; pct = sum(1 for x in cs if x<v)/len(cs)*100
    mu = sum(cs)/len(cs); sd = math.sqrt(sum((x-mu)**2 for x in cs)/len(cs))
    sig = (v-mu)/sd if sd>0 else 0
    it = ("极度恐慌" if sig>2 else "恐慌" if sig>1 else "偏高" if sig>0.5
          else "正常" if sig>-0.5 else "偏低" if sig>-1 else "极度平静")
    return {"date":r["date"],"value":round(v,2),"percentile":round(pct,1),
            "sigma":round(sig,2),"mean":round(mu,2),"std":round(sd,2),"interpretation":it}

@app.get("/api/vix/history")
def vix_history(days:int=Query(default=365,ge=1,le=15000)):
    conn=get_db(); rows=conn.execute("SELECT date,close FROM vix_daily ORDER BY date DESC LIMIT ?",(days,)).fetchall(); conn.close()
    return {"data":[{"date":r["date"],"close":r["close"]} for r in reversed(rows)]}

@app.get("/api/vix/peaks")
def vix_peaks(n:int=Query(default=30,ge=1,le=100)):
    conn=get_db(); rows=conn.execute("SELECT date,close FROM vix_daily ORDER BY close DESC LIMIT ?",(n,)).fetchall(); conn.close()
    return {"peaks":[{"rank":i+1,"date":r["date"],"value":round(r["close"],2)} for i,r in enumerate(rows)]}

@app.get("/api/vix/crises")
def vix_crises():
    conn=get_db(); rows=conn.execute("SELECT * FROM crisis_events ORDER BY peak_date DESC").fetchall(); conn.close()
    return {"events":[dict(r) for r in rows]}

@app.get("/api/vix/stats")
def vix_stats():
    conn=get_db()
    s=conn.execute("SELECT COUNT(*) as n,MIN(date) as lo,MAX(date) as hi,ROUND(AVG(close),2) as mu,ROUND(MAX(close),2) as mx,ROUND(MIN(close),2) as mn FROM vix_daily WHERE close>0").fetchone()
    cs=sorted([r[0] for r in conn.execute("SELECT close FROM vix_daily WHERE close>0")]); conn.close()
    p=lambda p:round(cs[min(int(len(cs)*p/100),len(cs)-1)],2)
    return {"total_days":s["n"],"date_range":f"{s['lo']}~{s['hi']}","mean":s["mu"],"max":s["mx"],"min":s["mn"],
            "p50":p(50),"p75":p(75),"p90":p(90),"p95":p(95),"p99":p(99)}

@app.get("/api/vix/fetch")
def trigger_fetch():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "/var/www/meigu/fetch_daily.py"],
        capture_output=True, text=True, timeout=120
    )
    return {"status": "ok", "output": result.stdout.strip(), "source": "yfinance(daily) + FRED(historical)"}

@app.get("/api/market/current")
def market_current():
    conn=get_db()
    def fmt(t): 
        rows=conn.execute(f"SELECT date,close FROM {t} ORDER BY date DESC LIMIT 2").fetchall()
        if len(rows)<2: return{"value":rows[0]["close"]if rows else 0,"date":rows[0]["date"]if rows else"","change_pct":0}
        ch=(rows[0]["close"]-rows[1]["close"])/rows[1]["close"]*100
        return{"value":round(rows[0]["close"],2),"date":rows[0]["date"],"change_pct":round(ch,2)}
    v=conn.execute("SELECT close FROM vix_daily ORDER BY date DESC LIMIT 1").fetchone()
    result={"spx":fmt("spx_daily"),"ndx":fmt("ndx_daily"),"vix":round(v["close"],2)if v else 0}
    conn.close()
    return result

@app.get("/api/market/signal")
def market_signal():
    conn=get_db()
    r=conn.execute("SELECT close FROM vix_daily ORDER BY date DESC LIMIT 1").fetchone()
    cs=sorted([x[0] for x in conn.execute("SELECT close FROM vix_daily WHERE close>0")]); conn.close()
    v=r["close"]; pct=sum(1 for x in cs if x<v)/len(cs)*100
    if v>=35: sg,cl,ac="强烈买入","#10b981","VIX≥35 历史性恐慌 → 逆向买入窗口"
    elif v>=30: sg,cl,ac="买入","#34d399","VIX 30-35 恐慌区域 → 分批建仓"
    elif v>=25: sg,cl,ac="关注买入","#f59e0b","VIX 25-30 偏高 → 关注回调加仓"
    elif v>=20: sg,cl,ac="持有","#3b82f6","VIX 20-25 正常偏高 → 持有观望"
    elif v>=15: sg,cl,ac="持有","#3b82f6","VIX 15-20 正常 → 正常配置"
    elif v>=12: sg,cl,ac="谨慎","#f59e0b","VIX 12-15 偏低 → 注意仓位"
    else: sg,cl,ac="减仓","#ef4444","VIX<12 极度平静 → 历史常预示回调"
    p=lambda q:round(cs[int(len(cs)*q/100)],1)
    return{"vix":round(v,2),"percentile":round(pct,1),"signal":sg,"signal_color":cl,"action":ac,
           "levels":{"extreme_fear":p(90),"fear":p(75),"complacency":p(25),"extreme_calm":p(10)}}

@app.get("/api/market/correlation")
def mkt_corr_spx(days:int=Query(default=252,ge=20,le=5000)):
    reg=regress_from_db("SELECT v.close as vix,s.close as spx FROM vix_daily v JOIN spx_daily s ON v.date=s.date ORDER BY v.date DESC LIMIT ?","vix","spx",(days,))
    conn=get_db(); rows=conn.execute("SELECT v.date,v.close as vix,s.close as spx FROM vix_daily v JOIN spx_daily s ON v.date=s.date ORDER BY v.date DESC LIMIT ?",(days,)).fetchall(); conn.close()
    return{"data":[{"date":r["date"],"vix":r["vix"],"spx":r["spx"]} for r in reversed(rows)],"regression":reg}

@app.get("/api/market/correlation_ndx")
def mkt_corr_ndx(days:int=Query(default=252,ge=20,le=5000)):
    reg=regress_from_db("SELECT v.close as vix,n.close as ndx FROM vix_daily v JOIN ndx_daily n ON v.date=n.date ORDER BY v.date DESC LIMIT ?","vix","ndx",(days,))
    conn=get_db(); rows=conn.execute("SELECT v.date,v.close as vix,n.close as ndx FROM vix_daily v JOIN ndx_daily n ON v.date=n.date ORDER BY v.date DESC LIMIT ?",(days,)).fetchall(); conn.close()
    return{"data":[{"date":r["date"],"vix":r["vix"],"ndx":r["ndx"]} for r in reversed(rows)],"regression":reg}

# ── Forward returns with confidence ──
def _fwd_returns(table, label):
    conn=get_db()
    rows=conn.execute(f"SELECT v.date,v.close as vix,m.close as {label} FROM vix_daily v JOIN {table} m ON v.date=m.date WHERE v.close>0 AND m.close>0 ORDER BY v.date").fetchall()
    conn.close()
    data=[(r["date"],r["vix"],r[label]) for r in rows]
    def calc(hmonths):
        res=[]
        for i,(d,vix,px) in enumerate(data):
            target=(datetime.strptime(d,"%Y-%m-%d")+timedelta(days=hmonths*30)).strftime("%Y-%m-%d")
            for j in range(i+1,len(data)):
                if data[j][0]>=target:
                    res.append({"date":d,"vix":vix,"fwd":round((data[j][2]-px)/px*100,2)}); break
        return res
    fwds={h:calc(m) for h,m in[("1m",1),("3m",3),("6m",6),("12m",12)]}
    zones=[("极度平静",0,12),("平静",12,15),("正常",15,20),("偏高",20,25),("恐慌",25,30),("极度恐慌",30,100)]
    result={}
    for h,fd in fwds.items():
        result[h]=[]
        for zn,lo,hi in zones:
            xs=[f["fwd"] for f in fd if lo<=f["vix"]<hi]
            if xs:
                mu=sum(xs)/len(xs); sd=math.sqrt(sum((x-mu)**2 for x in xs)/len(xs))
                result[h].append({"zone":zn,"vix_range":f"{lo}-{hi}","avg":round(mu,2),"std":round(sd,2),
                    "ci_low":round(mu-2*sd,2),"ci_high":round(mu+2*sd,2),
                    "count":len(xs),"pos_pct":round(sum(1 for x in xs if x>0)/len(xs)*100,1)})
    return result

@app.get("/api/market/forward_returns")
def fwd_spx(): return _fwd_returns("spx_daily","spx")

@app.get("/api/market/forward_returns_ndx")
def fwd_ndx(): return _fwd_returns("ndx_daily","ndx")

# ── Backtesting ──
@app.get("/api/market/backtest")
def backtest():
    conn=get_db()
    rows=conn.execute("SELECT v.date,v.close as vix,s.close as spx FROM vix_daily v JOIN spx_daily s ON v.date=s.date WHERE v.close>0 AND s.close>0 ORDER BY v.date").fetchall()
    conn.close()
    data=[(r["date"],r["vix"],r["spx"]) for r in rows]
    n=len(data)
    
    thresholds=[12,15,20,25,30,35]
    results=[]
    def find_fwd(si, months):
        target=(datetime.strptime(data[si][0],"%Y-%m-%d")+timedelta(days=months*30)).strftime("%Y-%m-%d")
        for j in range(si+1,n):
            if data[j][0]>=target: return (data[j][2]-data[si][2])/data[si][2]*100
        return None
    
    for th in thresholds:
        signals=[i for i,(d,vix,_) in enumerate(data) if vix>=th]
        if not signals: continue
        r3=[x for x in (find_fwd(si,3) for si in signals) if x is not None]
        r6=[x for x in (find_fwd(si,6) for si in signals) if x is not None]
        r12=[x for x in (find_fwd(si,12) for si in signals) if x is not None]
        
        def stats(xs,label):
            if not xs: return None
            mu=sum(xs)/len(xs); sd=math.sqrt(sum((x-mu)**2 for x in xs)/len(xs))
            wins=sum(1 for x in xs if x>0)
            # Max drawdown: worst single-trade loss + worst cumulative drawdown streak
            worst_trade=min(xs)
            # Find worst consecutive drawdown (max peak-to-trough in sequence)
            peak_val=0; worst_dd=0
            running=0
            for x in xs:
                running+=x
                if running>peak_val: peak_val=running
                dd=peak_val-running
                if dd>worst_dd: worst_dd=dd
            return{"horizon":label,"count":len(xs),"avg":round(mu,2),"std":round(sd,2),
                   "ci_low":round(mu-2*sd,2),"ci_high":round(mu+2*sd,2),
                   "win_rate":round(wins/len(xs)*100,1),
                   "worst_trade":round(worst_trade,1),"worst_drawdown":round(worst_dd,1)}
        
        h3=stats(r3,"3个月"); h6=stats(r6,"6个月"); h12=stats(r12,"12个月")
        if h3:
            results.append({"threshold":th,"label":f"VIX ≥ {th}","signal_count":len(signals),
                           "horizons":[x for x in[h3,h6,h12] if x]})
    return{"backtests":results}

# Static
os.makedirs(STATIC_DIR,exist_ok=True)
app.mount("/",StaticFiles(directory=STATIC_DIR,html=True),name="static")
