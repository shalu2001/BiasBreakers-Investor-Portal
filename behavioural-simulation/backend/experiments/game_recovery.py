"""Full onboarding-game parameter recovery (resumable).
Known personas play Fund A + Fund B + the matched-stakes event round through the REAL
game engine, then are recovered exactly as app.py finish() does (calibration for
alpha/gamma, matched-stakes for lambda). Writes one row per persona-rep to ROWS_CSV.
  python game_recovery.py         -> process one time-boxed batch
  python game_recovery.py agg     -> aggregate + write result sheet
"""
import os, sys, csv, numpy as np, pandas as pd
sys.path.insert(0, os.environ.get("BACKEND","."))
from game.multi_block_session import MultiBlockSession
from estimation.final_estimator import fit_full_profile
from estimation.estimator_v2 import fit_profile_v2
from estimation.calibration import load_default_calibrator, features_from_fits
from estimation.lambda_events import make_events, event_cpt_value, fit_lambda_events
PERSONAS={  # ground-truth answer key (ground_truth_pipeline/config.py)
    "INV_01":(0.88,2.25,0.5),"INV_02":(0.70,4.50,0.1),"INV_03":(0.92,1.25,4.5),
    "INV_04":(0.98,1.05,0.0),"INV_05":(0.75,2.75,0.8)}

ROWS_CSV="/tmp/game_rows.csv"; REPS=5; WC=5000.0
sig=lambda x:1/(1+np.exp(-np.clip(x,-30,30)))
CAL=load_default_calibrator()

def play_blocks(a,l,g,k,noise,data,rng):
    s=MultiBlockSession(data,1_000_000,n_per_bin=3)
    while True:
        st=s.current_session
        wc=(st.total_equity()-st._prev_day_equity)/WC
        v=wc**a if wc>=0 else -l*(abs(wc)**a)
        mg=st.market_gap()
        tgt=float(np.clip(sig(k*(v+g*mg)+rng.normal(0,noise)),0.02,0.98))
        s.set_allocation(s.get_tradable_ticker() or "JKH",tgt)
        if s.advance()["status"]=="all_blocks_complete": break
    return s.get_block_logs()

def play_events(lam,alpha,tau,noise,seed,rng):
    recs=[]
    for (G,Ls) in make_events(seed=seed,n=16):
        val=event_cpt_value(G,Ls,lam,alpha)
        commit=float(np.clip(sig(tau*val+rng.normal(0,noise)),0.02,0.98))
        recs.append({"gain_pct":G,"loss_pct":Ls,"commit":commit})
    return recs

def recover(l1,l2,ev):
    fit=fit_full_profile(l1,l2,starting_equity=1_000_000)
    v2=fit_profile_v2(l1,l2,starting_equity=1_000_000)
    if CAL is not None:
        cal=CAL.calibrate(features_from_fits(fit["raw"],v2))
        prof={"alpha":cal["alpha"],"lambda":cal["lambda"],"gamma":cal["gamma"]}
    else:
        prof={"alpha":v2["alpha"],"lambda":v2["lambda"] if v2["lambda"] is not None else 2.25,"gamma":v2["gamma"]}
    lam_src="free_play"
    el=fit_lambda_events(ev)
    if el and el.get("estimate") is not None and el["confidence"]["level"]!="uninformative":
        prof["lambda"]=float(el["estimate"]); lam_src="events"
    return prof,lam_src

def load():
    d={}
    for s in ["2021_bull_run","2022_crash","2023_recovery"]:
        b=os.path.join(os.environ.get("BACKEND","."),"scenario_build",s)
        d[s]=(pd.read_csv(f"{b}_stocks.csv",parse_dates=["Date"]),pd.read_csv(f"{b}_index.csv",parse_dates=["Date"]))
    return d

def done():
    if not os.path.exists(ROWS_CSV): return set()
    return set((r["persona"],int(r["rep"])) for r in csv.DictReader(open(ROWS_CSV)))

def batch(nmax=8):
    import time; t0=time.time(); data=load(); dn=done()
    jobs=[(p,rep) for p in PERSONAS for rep in range(REPS) if (p,rep) not in dn][:nmax]
    new=os.path.exists(ROWS_CSV); fh=open(ROWS_CSV,"a",newline=""); w=csv.writer(fh)
    if not new: w.writerow(["persona","rep","ta","tl","tg","ra","rl","rg","lam_src"])
    for p,rep in jobs:
        if time.time()-t0>32: break
        a,l,g=PERSONAS[p]
        rng=np.random.default_rng(hash((p,rep))%(2**32))
        k=rng.uniform(0.6,1.0); noise=rng.uniform(0.12,0.22); tau=rng.uniform(0.5,1.1)
        l1,l2=play_blocks(a,l,g,k,noise,data,rng)
        ev=play_events(l,a,tau,0.22,1000+rep,rng)
        prof,src=recover(l1,l2,ev)
        w.writerow([p,rep,a,l,g,round(prof["alpha"],3),round(prof["lambda"],3),round(prof["gamma"],3),src]); fh.flush()
    fh.close(); print(f"batch done: {len(done())}/{len(PERSONAS)*REPS} rows")

def pear(x,y):
    x=np.asarray(x,float);y=np.asarray(y,float)
    return float(np.corrcoef(x,y)[0,1]) if len(x)>2 and x.std()>0 and y.std()>0 else float('nan')

def agg():
    rows=list(csv.DictReader(open(ROWS_CSV)))
    out=os.path.join(os.environ.get("BACKEND","."),"experiments","game_recovery_results.csv")
    os.makedirs(os.path.dirname(out),exist_ok=True)
    # per-persona means
    import collections
    per=collections.defaultdict(list)
    for r in rows: per[r["persona"]].append(r)
    with open(out,"w",newline="") as fh:
        w=csv.writer(fh)
        w.writerow(["persona","true_alpha","true_lambda","true_gamma",
                    "rec_alpha","rec_lambda","rec_gamma","abs_err_alpha","abs_err_lambda","abs_err_gamma","reps"])
        for p in PERSONAS:
            rs=per[p]; 
            ta,tl,tg=PERSONAS[p]
            ra=np.mean([float(r["ra"]) for r in rs]); rl=np.mean([float(r["rl"]) for r in rs]); rg=np.mean([float(r["rg"]) for r in rs])
            w.writerow([p,ta,tl,tg,round(ra,3),round(rl,3),round(rg,3),
                        round(abs(ra-ta),3),round(abs(rl-tl),3),round(abs(rg-tg),3),len(rs)])
    # overall metrics across all games
    ta=[float(r["ta"]) for r in rows]; tl=[float(r["tl"]) for r in rows]; tg=[float(r["tg"]) for r in rows]
    ra=[float(r["ra"]) for r in rows]; rl=[float(r["rl"]) for r in rows]; rg=[float(r["rg"]) for r in rows]
    print("\n"+"="*66)
    print(f"FULL-GAME RECOVERY — {len(rows)} games ({len(PERSONAS)} personas x {REPS} reps)")
    print("="*66)
    print(f"{'param':6} | {'Pearson r':>9} | {'MAE':>6}")
    print(f"{'alpha':6} | {pear(ta,ra):9.3f} | {np.mean(np.abs(np.array(ta)-np.array(ra))):6.3f}")
    print(f"{'lambda':6} | {pear(tl,rl):9.3f} | {np.mean(np.abs(np.array(tl)-np.array(rl))):6.3f}")
    print(f"{'gamma':6} | {pear(tg,rg):9.3f} | {np.mean(np.abs(np.array(tg)-np.array(rg))):6.3f}")
    print("="*66)
    print("lambda source counts:", {s: sum(1 for r in rows if r["lam_src"]==s) for s in set(r["lam_src"] for r in rows)})
    print("wrote", out)

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="agg": agg()
    else: batch()
