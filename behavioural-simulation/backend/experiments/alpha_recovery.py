"""
alpha_recovery.py -- trains + validates the scale-free ALPHA estimator and, on the
same synthetic run, checks lambda/gamma recovery (existing pipeline) and the
archetype tercile thresholds. Plays the REAL engine end-to-end (so it also proves
the game itself doesn't break). Saves the trained alpha regressor to
estimation/alpha_regressor.json for the production estimator to load.
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import pearsonr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
from game.multi_block_session import MultiBlockSession
from game.event_round import EventRound
from estimation.final_estimator import fit_full_profile
from estimation.estimator_v2 import fit_profile_v2
from estimation.calibration import load_default_calibrator, features_from_fits
from estimation.lambda_events import event_cpt_value

WC = 5000.0
CAL = load_default_calibrator()
sig = lambda x: 1.0/(1.0+np.exp(-np.clip(x,-30,30)))
def clogit(p): p=np.clip(p,0.02,0.98); return np.log(p/(1-p))

def load_scenarios():
    d={}
    for n in ["2021_bull_run","2022_crash","2023_recovery"]:
        b=os.path.join(paths.SCENARIO_BUILD,n)
        d[n]=(pd.read_csv(f"{b}_stocks.csv",parse_dates=["Date"]),pd.read_csv(f"{b}_index.csv",parse_dates=["Date"]))
    return d
DATA=load_scenarios()
def gap_now(cs):
    try: return float(cs.get_index_return())-float(cs.held_stock_return())
    except Exception: return 0.0
def value(wc,a,lam):
    x=wc/WC; return x**a if x>=0 else -lam*(abs(x)**a)

def _sscale(wc):
    w=np.abs(np.asarray(wc,float)); w=w[w>0]
    return float(np.clip(np.median(w) if w.size else 5000.0, 3000.0, 1e6))

def alpha_features(l1):
    wc=l1["wealth_change"].values.astype(float); y=clogit(l1["target_pct"].values); m=wc>0
    if m.sum()<4: return None
    s=_sscale(wc)                       # per-session normalisation (matches production alpha_features)
    x,yy=wc[m]/s,y[m]
    gc=np.corrcoef(x,yy)[0,1] if (np.std(x)>0 and np.std(yy)>0) else 0.0
    st=float(np.std(l1["target_pct"].values))
    X=np.column_stack([x,x**2,np.ones_like(x)]); b=np.linalg.lstsq(X,yy,rcond=None)[0]
    return [float(gc), st, float(b[1]/(abs(b[0])+1e-9))]

def play(a,lam,g,tau,k,noise,seed):
    rng=np.random.default_rng(seed); s=MultiBlockSession(DATA,1_000_000,n_per_bin=2); last=1e6
    while True:
        cs=s.current_session; E=cs.total_equity(); wc=E-last; v=value(wc,a,lam)
        if s.block=="loss_aversion": tgt=sig(k*v+rng.normal(0,noise)); tk=sorted(s.get_market_state().keys())[0]
        else: tgt=sig(k*(v+g*gap_now(cs))+rng.normal(0,noise)); tk="DIAL"
        s.set_allocation(tk,float(np.clip(tgt,0.02,0.98))); last=E
        st=s.advance()["status"]
        if st=="all_blocks_complete": break
        if st in ("new_scenario_started","new_block_started"): last=s.current_session.total_equity()
    er=EventRound(n_events=16,seed=seed)
    while not er.is_complete():
        ev=er.current(); er.commit(float(np.clip(sig(tau*event_cpt_value(ev["gain_pct"],ev["loss_pct"],lam,a)+rng.normal(0,0.18)),0.02,0.98)))
    l1,l2=s.get_block_logs()
    fit=fit_full_profile(l1,l2,starting_equity=s.starting_cash)
    v2=fit_profile_v2(l1,l2,starting_equity=s.starting_cash)
    cal=CAL.calibrate(features_from_fits(fit["raw"],v2))
    lam_hat,gam_hat,alpha_old=cal["lambda"],cal["gamma"],cal["alpha"]
    el=er.estimate_lambda()
    if el and el.get("estimate") is not None and el["confidence"]["level"]!="uninformative": lam_hat=float(el["estimate"])
    return l1,alpha_old,lam_hat,gam_hat

def main(N=55, base=400000):
    ta,tl,tg,ao,lh,gh,F=[],[],[],[],[],[],[]
    ok=0
    for i in range(N):
        rng=np.random.default_rng(base+i)
        a=rng.uniform(0.6,1.0); lam=rng.uniform(1.1,4.2); g=rng.uniform(0.0,4.0)
        tau=rng.uniform(0.4,1.0); k=rng.uniform(0.4,1.05); noise=rng.uniform(0.1,0.2)  # k widened DOWN for gentler players
        l1,alpha_old,lam_hat,gam_hat=play(a,lam,g,tau,k,noise,base+i)
        ta.append(a);tl.append(lam);tg.append(g);ao.append(alpha_old);lh.append(lam_hat);gh.append(gam_hat)
        F.append(alpha_features(l1)); ok+=1
    print(f"GAME INTEGRITY: {ok}/{N} sessions played + recovered with no errors.\n")
    ta,tl,tg,ao,lh,gh=map(np.array,(ta,tl,tg,ao,lh,gh))

    # ---- train alpha regressor on players with valid features ----
    valid=np.array([f is not None for f in F])
    Fe=np.array([f for f in F if f is not None]); av=ta[valid]
    MU=Fe.mean(0); SD=Fe.std(0)+1e-9; Z=(Fe-MU)/SD
    X=np.column_stack([Z,np.ones(len(Z))]); BETA=np.linalg.lstsq(X,av,rcond=None)[0]
    # leave-one-out
    n=len(av); pred=np.zeros(n)
    for i in range(n):
        tr=[j for j in range(n) if j!=i]
        Xt=np.column_stack([Z[tr],np.ones(len(tr))]); bt=np.linalg.lstsq(Xt,av[tr],rcond=None)[0]
        pred[i]=np.clip(np.r_[Z[i],1.0]@bt,0.5,1.0)
    print("1. ALPHA (new scale-free estimator, leave-one-out):")
    print(f"   r={pearsonr(av,pred)[0]:+.3f}  MAE={np.mean(np.abs(av-pred)):.3f}  range {pred.min():.2f}-{pred.max():.2f}   (old pipeline r={pearsonr(ta,ao)[0]:+.3f})\n")

    print("2. LAMBDA / GAMMA (existing pipeline, same run):")
    print(f"   lambda r={pearsonr(tl,lh)[0]:+.3f}  MAE={np.mean(np.abs(tl-lh)):.3f}")
    print(f"   gamma  r={pearsonr(tg,gh)[0]:+.3f}  MAE={np.mean(np.abs(tg-gh)):.3f}\n")

    # ---- recalibrate lambda/gamma tercile anchors ----
    lp33,lp67=np.percentile(lh,[33,67]); gp33,gp67=np.percentile(gh,[33,67])
    print("3. RECALIBRATED archetype thresholds (p33 / p67 of the recovered distribution):")
    print(f"   lambda: {lp33:.2f} / {lp67:.2f}   gamma: {gp33:.2f} / {gp67:.2f}")
    bd=lambda v,a,b:0 if v<a else 1 if v<b else 2
    rb=np.array([bd(v,lp33,lp67) for v in lh]); sb=np.array([bd(v,gp33,gp67) for v in gh])
    for nm,arr in [("risk",rb),("style",sb)]:
        print(f"   {nm} split: {[int((arr==k).sum()) for k in (0,1,2)]}")
    tr=lambda x:(np.where(np.argsort(np.argsort(x))<len(x)/3,0,np.where(np.argsort(np.argsort(x))<2*len(x)/3,1,2)))
    print(f"   construct validity: risk={100*np.mean(tr(tl)==rb):.0f}%  style={100*np.mean(tg==tg)*0+100*np.mean(tr(tg)==sb):.0f}%  (chance 33%)\n")

    # ---- full frontend percentile anchors (monotone) ----
    def anchors(arr):
        out=[]; prev=-1e9
        for pc in range(0,101,10):
            v=round(float(np.percentile(arr,pc)),3)
            if v<=prev: v=round(prev+0.01,3)
            out.append([v,pc]); prev=v
        return out
    lamA=anchors(lh); gamA=anchors(gh)
    print("4. FRONTEND ANCHORS (value, percentile):")
    print("   LAM_ANCHORS =",lamA)
    print("   GAM_ANCHORS =",gamA)
    # ---- save regressor ----
    out={"lam_anchors":lamA,"gam_anchors":gamA,"features":["gain_corr","alloc_std","gain_curvature"],"mu":MU.tolist(),"sd":SD.tolist(),
         "beta":BETA.tolist(),"alpha_prior":0.88,"min_gain_obs":4,"clip":[0.5,1.0],
         "loo_r":float(pearsonr(av,pred)[0]),"trained_n":int(n)}
    dst=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"estimation","alpha_regressor.json")
    json.dump(out,open(dst,"w"),indent=2)
    print("SAVED regressor ->",dst)

if __name__=="__main__": main()
