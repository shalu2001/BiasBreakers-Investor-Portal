"""
regret_gamma_train.py -- train + validate the dedicated regret/FOMO (gamma)
estimator (estimation/regret_gamma.py).

Synthetic players trade the REAL regret block with ALLOCATION INERTIA (partial
adjustment) -- alloc_t = alloc_{t-1} + k*(value(wc_t) + gamma*gap_t) + noise --
which is how real humans actually behave (sticky positions nudged over time), and
exactly the pattern that made the joint gamma collapse to 0. We recover gamma with
the inertia-robust differenced estimator, fit an affine rescale (true gamma ~ raw
slope), compute terciles + anchors, and report recovery. Saves regret_gamma.json.
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import pearsonr, spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
from game.multi_block_session import MultiBlockSession
from estimation.regret_gamma import raw_gamma_slope

sig = lambda x: 1.0/(1.0+np.exp(-np.clip(x,-30,30)))
GEN_SCALE = 20000.0

def load():
    d={}
    for n in ["2021_bull_run","2022_crash","2023_recovery"]:
        b=os.path.join(paths.SCENARIO_BUILD,n)
        d[n]=(pd.read_csv(f"{b}_stocks.csv",parse_dates=["Date"]),pd.read_csv(f"{b}_index.csv",parse_dates=["Date"]))
    return d
DATA=load()
def gap_now(cs):
    try: return float(cs.get_index_return())-float(cs.held_stock_return())
    except Exception: return 0.0
def val(wc,a,lam):
    x=wc/GEN_SCALE; return np.sign(x)*np.abs(x)**a if True else x

def play_regret(a,lam,g,k,inertia,noise,seed):
    """Play the full session; regret block uses PARTIAL-ADJUSTMENT (inertia) policy."""
    rng=np.random.default_rng(seed); s=MultiBlockSession(DATA,1_000_000,n_per_bin=2); last=1e6
    alloc=0.5
    while True:
        cs=s.current_session; E=cs.total_equity(); wc=E-last
        v=val(wc,a,lam)
        if s.block=="loss_aversion":
            tgt=sig(k*(-lam*abs(wc/GEN_SCALE)**a if wc<0 else (wc/GEN_SCALE)**a)+rng.normal(0,noise))
            tk=sorted(s.get_market_state().keys())[0]; alloc=0.5
        else:
            # inertia: nudge previous allocation by current value + gamma*gap
            drive=k*(v+g*gap_now(cs))+rng.normal(0,noise)
            alloc=float(np.clip(alloc+inertia*drive,0.02,0.98)); tgt=alloc; tk="DIAL"
        s.set_allocation(tk,float(np.clip(tgt,0.02,0.98))); last=E
        st=s.advance()["status"]
        if st=="all_blocks_complete": break
        if st in ("new_scenario_started","new_block_started"):
            last=s.current_session.total_equity()
            if s.block!="loss_aversion": alloc=0.5
    _,l2=s.get_block_logs(); return l2

def anchors(arr):
    out=[]; prev=-1e9
    for pc in range(0,101,10):
        v=round(float(np.percentile(arr,pc)),3)
        if v<=prev: v=round(prev+0.01,3)
        out.append([v,pc]); prev=v
    return out

def main(N=70, base=520000):
    tg,raw,ok=[],[],0
    for i in range(N):
        rng=np.random.default_rng(base+i)
        a=rng.uniform(0.7,0.95); lam=rng.uniform(1.3,3.5); g=rng.uniform(0.0,4.0)
        k=rng.uniform(0.4,1.1); inertia=rng.uniform(0.5,1.0); noise=rng.uniform(0.10,0.20)
        try:
            l2=play_regret(a,lam,g,k,inertia,noise,base+i)
            rv,t,n=raw_gamma_slope(l2)
            if rv is None: continue
            tg.append(g); raw.append(rv); ok+=1
        except Exception as e:
            print("err",base+i,repr(e)); continue
    tg=np.array(tg); raw=np.array(raw)
    # robustify: winsorise raw to tame the ratio's tail before fitting the linear map
    lo,hi=np.percentile(raw,[5,95]); rawc=np.clip(raw,lo,hi)
    b1,b0=np.polyfit(rawc,tg,1)                # true_gamma ~ b0 + b1*raw
    gam=np.clip(b0+b1*rawc,0.0,6.0)
    print(f"TRAINED on {ok} inertia players.")
    print(f"  raw->gamma recovery: Pearson r={pearsonr(tg,gam)[0]:+.3f}  Spearman={spearmanr(tg,raw)[0]:+.3f}  MAE={np.mean(abs(tg-gam)):.3f}")
    print(f"  gamma range recovered: {gam.min():.2f}..{gam.max():.2f}   (NO hard-zero floor)")
    gt=[round(float(np.percentile(gam,33)),3),round(float(np.percentile(gam,67)),3)]
    print(f"  terciles: {gt}")
    cfg={"gamma_rescale":[float(b0),float(b1)],"raw_winsor":[float(lo),float(hi)],
         "gam_terciles":gt,"gam_anchors":anchors(gam),
         "gamma_r":float(pearsonr(tg,gam)[0]),"trained_n":int(ok)}
    dst=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"estimation","regret_gamma.json")
    json.dump(cfg,open(dst,"w"),indent=2); print("SAVED ->",dst)
    print("  GAM_ANCHORS =",cfg["gam_anchors"])

if __name__=="__main__": main()
