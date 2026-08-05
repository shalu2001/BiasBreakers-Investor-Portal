"""Resumable gamma-recovery experiment: BROAD index vs OWN (DIAL-only) benchmark.
Each run processes a small batch of players and appends to ROWS_CSV so it fits the
45s shell limit. Final `python bench_test.py agg` prints the comparison."""
import os, sys, csv, numpy as np, pandas as pd
sys.path.insert(0,os.environ.get("BACKEND","."))
from game.multi_block_session import MultiBlockSession

ROWS_CSV="/tmp/bench_rows.csv"
N=40; SEED=7
WC=5000.0; ALPHA_FIX=0.88
sig=lambda x:1/(1+np.exp(-np.clip(x,-30,30)))
def logit(p): p=np.clip(p,0.02,0.98); return np.log(p/(1-p))

def load():
    d={}
    for s in ["2021_bull_run","2022_crash","2023_recovery"]:
        b=os.path.join(os.environ.get("BACKEND","."),"scenario_build",s)
        d[s]=(pd.read_csv(f"{b}_stocks.csv",parse_dates=["Date"]),
              pd.read_csv(f"{b}_index.csv",parse_dates=["Date"]))
    return d

def own_gap(st,tk):
    eq=st.total_equity(); hf=(eq-st.cash)/eq if eq>0 else 0.0
    r=st.get_market_state().get(tk,{}).get("ticker_return_pct")
    r=0.0 if (r is None or (isinstance(r,float) and np.isnan(r))) else float(r)
    return (1.0-hf)*r

def play(a,l,g,k,noise,data,rng,design):
    s=MultiBlockSession(data,1_000_000,n_per_bin=2); rows=[]
    while True:
        st=s.current_session
        wc=(st.total_equity()-st._prev_day_equity)/WC
        v=wc**a if wc>=0 else -l*(abs(wc)**a)
        tk=s.get_tradable_ticker(); regret=tk is not None
        gap=(st.market_gap() if design=="BROAD" else own_gap(st,tk)) if regret else 0.0
        tgt=float(np.clip(sig(k*(v+g*gap)+rng.normal(0,noise)),0.02,0.98))
        if regret: rows.append((wc,gap,tgt))
        s.set_allocation(tk or "JKH",tgt)
        if s.advance()["status"]=="all_blocks_complete": break
    return pd.DataFrame(rows,columns=["wc","gap","tgt"])

def recover(df):
    if len(df)<6: return np.nan
    wc=df["wc"].values
    v=np.where(wc>=0,np.abs(wc)**ALPHA_FIX,-(np.abs(wc)**ALPHA_FIX))
    y=logit(df["tgt"].values); X=np.column_stack([v,df["gap"].values,np.ones(len(df))])
    b,*_=np.linalg.lstsq(X,y,rcond=None); bv,bm=b[0],b[1]
    return float(np.clip(bm/bv if abs(bv)>1e-6 else bm,0.0,8.0))

def done_ids():
    if not os.path.exists(ROWS_CSV): return set()
    return set(int(r["i"]) for r in csv.DictReader(open(ROWS_CSV)))

def draw(i):
    rng=np.random.default_rng(SEED*1000+i)
    return dict(a=rng.uniform(0.75,0.98),l=rng.uniform(1.0,3.5),g=rng.uniform(0.0,4.5),
                k=rng.uniform(0.6,1.0),noise=rng.uniform(0.12,0.22))

def batch(nmax=8):
    import time; t0=time.time(); data=load(); done=done_ids()
    todo=[i for i in range(N) if i not in done][:nmax]
    new=os.path.exists(ROWS_CSV)
    fh=open(ROWS_CSV,"a",newline=""); w=csv.writer(fh)
    if not new: w.writerow(["i","true_g","rec_broad","rec_own","var_broad","var_own"])
    for i in todo:
        if time.time()-t0>34: break
        p=draw(i)
        db=play(p['a'],p['l'],p['g'],p['k'],p['noise'],data,np.random.default_rng(1000+i),"BROAD")
        do=play(p['a'],p['l'],p['g'],p['k'],p['noise'],data,np.random.default_rng(1000+i),"OWN")
        w.writerow([i,round(p['g'],4),recover(db),recover(do),
                    round(float(np.var(db['gap'])),5),round(float(np.var(do['gap'])),5)])
        fh.flush()
    fh.close()
    print(f"batch done. total rows now: {len(done_ids())}/{N}")

def pear(x,y):
    x=np.asarray(x); y=np.asarray(y); m=~(np.isnan(x)|np.isnan(y))
    x,y=x[m],y[m]
    return float(np.corrcoef(x,y)[0,1]) if len(x)>2 and x.std()>0 and y.std()>0 else np.nan
def rankcorr(x,y):
    def rk(a):
        a=np.asarray(a,float); o=a.argsort(); r=np.empty(len(a)); r[o]=np.arange(len(a)); return r
    return pear(rk(x),rk(y))

def agg():
    rows=list(csv.DictReader(open(ROWS_CSV)))
    tg=np.array([float(r["true_g"]) for r in rows])
    rb=np.array([float(r["rec_broad"]) for r in rows]); ro=np.array([float(r["rec_own"]) for r in rows])
    vb=np.array([float(r["var_broad"]) for r in rows]); vo=np.array([float(r["var_own"]) for r in rows])
    print("\n"+"="*68)
    print(f"GAMMA RECOVERY  —  BROAD (S&P SL20) vs OWN (DIAL-only)   N={len(rows)}")
    print("="*68)
    print(f"{'design':6} | {'Pearson r':>9} | {'Spearman':>8} | {'MAE':>6} | {'mean gap var':>12}")
    for nm,rec,vv in [("BROAD",rb,vb),("OWN",ro,vo)]:
        mae=np.nanmean(np.abs(tg-rec))
        print(f"{nm:6} | {pear(tg,rec):9.3f} | {rankcorr(tg,rec):8.3f} | {mae:6.3f} | {np.nanmean(vv):12.4f}")
    print("="*68)

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="agg": agg()
    else: batch()
