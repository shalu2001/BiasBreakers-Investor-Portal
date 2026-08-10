"""
joint_estimator.py -- trains the affine rescalers + archetype thresholds for the
joint lambda/gamma estimator (estimation/joint_profile.py) and validates it
end-to-end on the real engine. Saves estimation/joint_estimator.json.
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import pearsonr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
from game.multi_block_session import MultiBlockSession
from game.event_round import EventRound
from estimation.lambda_events import event_cpt_value
from estimation.joint_profile import fit_joint
from estimation.alpha_features import estimate_alpha

sig=lambda x:1.0/(1.0+np.exp(-np.clip(x,-30,30))); WC=5000.0
def load_scen():
    d={}
    for n in ["2021_bull_run","2022_crash","2023_recovery"]:
        b=os.path.join(paths.SCENARIO_BUILD,n)
        d[n]=(pd.read_csv(f"{b}_stocks.csv",parse_dates=["Date"]),pd.read_csv(f"{b}_index.csv",parse_dates=["Date"]))
    return d
DATA=load_scen()
def gap_now(cs):
    try: return float(cs.get_index_return())-float(cs.held_stock_return())
    except Exception: return 0.0
def value(wc,a,lam):
    x=wc/WC; return x**a if x>=0 else -lam*(abs(x)**a)
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
    l1,l2=s.get_block_logs(); return l1,l2,er.records

def anchors(arr):
    out=[]; prev=-1e9
    for pc in range(0,101,10):
        v=round(float(np.percentile(arr,pc)),3)
        if v<=prev: v=round(prev+0.01,3)
        out.append([v,pc]); prev=v
    return out

def main(N=55, base=700000):
    ta,tl,tg,jl,jg,fa=[],[],[],[],[],[]; ok=0
    for i in range(N):
        rng=np.random.default_rng(base+i)
        a=rng.uniform(0.6,1.0); lam=rng.uniform(1.1,4.2); g=rng.uniform(0,4)
        tau=rng.uniform(0.4,1.0); k=rng.uniform(0.4,1.05); noise=rng.uniform(0.1,0.2)  # k widened DOWN to cover gentler real play
        l1,l2,evs=play(a,lam,g,tau,k,noise,base+i)
        aj,lj,gj,kk,tt=fit_joint(l1,l2,evs)
        ta.append(a);tl.append(lam);tg.append(g);jl.append(lj);jg.append(gj);fa.append(estimate_alpha(l1)["alpha"]); ok+=1
    ta,tl,tg,jl,jg,fa=map(np.array,(ta,tl,tg,jl,jg,fa))
    print(f"GAME INTEGRITY: {ok}/{N} sessions, no errors.\n")
    # affine rescalers  true ~ [1, joint]
    lb=np.polyfit(jl,tl,1); gb=np.polyfit(jg,tg,1)   # slope,intercept
    lam_s=lb[0]*jl+lb[1]; gam_s=gb[0]*jg+gb[1]
    print("RECOVERY (joint, after affine rescale):")
    print(f"  lambda r={pearsonr(tl,lam_s)[0]:+.3f}  MAE={np.mean(abs(tl-lam_s)):.3f}")
    print(f"  gamma  r={pearsonr(tg,gam_s)[0]:+.3f}  MAE={np.mean(abs(tg-gam_s)):.3f}")
    print(f"  alpha (feature) r={pearsonr(ta,fa)[0]:+.3f}\n")
    lt=[round(float(np.percentile(lam_s,33)),3),round(float(np.percentile(lam_s,67)),3)]
    gt=[round(float(np.percentile(gam_s,33)),3),round(float(np.percentile(gam_s,67)),3)]
    bd=lambda v,t:0 if v<t[0] else 1 if v<t[1] else 2
    rb=np.array([bd(v,lt) for v in lam_s]); sb=np.array([bd(v,gt) for v in gam_s])
    tr=lambda x:(lambda o,n:np.where(o<n/3,0,np.where(o<2*n/3,1,2)))(np.argsort(np.argsort(x)),len(x))
    print("ARCHETYPES (rescaled joint):")
    print(f"  lambda terciles {lt}  gamma terciles {gt}")
    print(f"  splits risk={[int((rb==k).sum()) for k in (0,1,2)]} style={[int((sb==k).sum()) for k in (0,1,2)]}")
    print(f"  construct validity risk={100*np.mean(tr(tl)==rb):.0f}% style={100*np.mean(tr(tg)==sb):.0f}% (chance 33%)")
    print(f"  coverage {len(set(zip(rb.tolist(),sb.tolist())))}/9\n")
    out={"lambda_rescale":[float(lb[1]),float(lb[0])],"gamma_rescale":[float(gb[1]),float(gb[0])],
         "lam_terciles":lt,"gam_terciles":gt,"lam_anchors":anchors(lam_s),"gam_anchors":anchors(gam_s),
         "lambda_r":float(pearsonr(tl,lam_s)[0]),"gamma_r":float(pearsonr(tg,gam_s)[0]),"trained_n":int(ok)}
    dst=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"estimation","joint_estimator.json")
    json.dump(out,open(dst,"w"),indent=2); print("SAVED ->",dst)
    print("\nFRONTEND ANCHORS:")
    print("  LAM_ANCHORS =",out["lam_anchors"]); print("  GAM_ANCHORS =",out["gam_anchors"])

if __name__=="__main__": main()
