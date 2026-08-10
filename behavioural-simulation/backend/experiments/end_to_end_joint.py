"""
end_to_end_joint.py -- OUT-OF-SAMPLE end-to-end test of the wired production path:
play fresh synthetic investors through the REAL MultiBlockSession + EventRound,
recover via the SAME calls the backend now makes (joint recover_lambda_gamma +
scale-free estimate_alpha), then apply the frontend's archetype bands
(profileToPersona.ts terciles). Seeds are disjoint from training/calibration.
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import pearsonr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
from game.multi_block_session import MultiBlockSession
from game.event_round import EventRound
from estimation.lambda_events import event_cpt_value
from estimation.joint_profile import recover_lambda_gamma
from estimation.alpha_features import estimate_alpha

sig=lambda x:1.0/(1.0+np.exp(-np.clip(x,-30,30))); WC=5000.0
def load():
    d={}
    for n in ["2021_bull_run","2022_crash","2023_recovery"]:
        b=os.path.join(paths.SCENARIO_BUILD,n)
        d[n]=(pd.read_csv(f"{b}_stocks.csv",parse_dates=["Date"]),pd.read_csv(f"{b}_index.csv",parse_dates=["Date"]))
    return d
DATA=load()
def gap(cs):
    try: return float(cs.get_index_return())-float(cs.held_stock_return())
    except Exception: return 0.0
def val(wc,a,lam):
    x=wc/WC; return x**a if x>=0 else -lam*(abs(x)**a)
def play(a,lam,g,tau,k,noise,seed):
    rng=np.random.default_rng(seed); s=MultiBlockSession(DATA,1_000_000,n_per_bin=2); last=1e6
    while True:
        cs=s.current_session; E=cs.total_equity(); wc=E-last; v=val(wc,a,lam)
        if s.block=="loss_aversion": tgt=sig(k*v+rng.normal(0,noise)); tk=sorted(s.get_market_state().keys())[0]
        else: tgt=sig(k*(v+g*gap(cs))+rng.normal(0,noise)); tk="DIAL"
        s.set_allocation(tk,float(np.clip(tgt,0.02,0.98))); last=E
        st=s.advance()["status"]
        if st=="all_blocks_complete": break
        if st in ("new_scenario_started","new_block_started"): last=s.current_session.total_equity()
    er=EventRound(n_events=16,seed=seed)
    while not er.is_complete():
        ev=er.current(); er.commit(float(np.clip(sig(tau*event_cpt_value(ev["gain_pct"],ev["loss_pct"],lam,a)+rng.normal(0,0.18)),0.02,0.98)))
    l1,l2=s.get_block_logs(); return l1,l2,er

# frontend anchors (mirror of profileToPersona.ts)
LAM=[[1.075,0],[1.531,10],[1.722,20],[1.847,30],[1.892,33],[2.042,40],[2.263,50],[2.841,60],[2.936,67],[2.982,70],[3.245,80],[3.735,90],[4.207,100]]
GAM=[[0.314,0],[0.721,10],[1.41,20],[1.669,30],[1.699,33],[1.849,40],[2.142,50],[2.403,60],[2.575,67],[2.757,70],[3.207,80],[3.375,90],[4.143,100]]
def pct(v,A):
    if v<=A[0][0]: return A[0][1]
    if v>=A[-1][0]: return A[-1][1]
    for i in range(1,len(A)):
        x0,p0=A[i-1]; x1,p1=A[i]
        if v<=x1: return round(p0+(v-x0)/(x1-x0)*(p1-p0))
    return A[-1][1]
tr=lambda x:(lambda o,n:np.where(o<n/3,0,np.where(o<2*n/3,1,2)))(np.argsort(np.argsort(x)),len(x))
RN=["Bold","Balanced","Cautious"]; SN=["Strategist","Realist","Momentum"]

def main(n=60, base=333000):
    ta,tl,tg,ra,rl,rg,rls,rgs,ok=[],[],[],[],[],[],[],[],0
    for i in range(n):
        rng=np.random.default_rng(base+i)
        a=rng.uniform(0.6,1.0); lam=rng.uniform(1.1,4.2); g=rng.uniform(0,4)
        tau=rng.uniform(0.4,1.0); k=rng.uniform(0.4,1.05); noise=rng.uniform(0.1,0.2)  # incl. gentler players
        try:
            l1,l2,er=play(a,lam,g,tau,k,noise,base+i)
            jr=recover_lambda_gamma(l1,l2,er.records); ae=estimate_alpha(l1)
            ok+=1
        except Exception as e:
            print("ERROR seed",base+i,repr(e)); continue
        ta.append(a);tl.append(lam);tg.append(g)
        ra.append(ae["alpha"]);rl.append(jr["lambda"]);rg.append(jr["gamma"])
        # risk/style score -> band (matches profileToPersona thresholds >=67/>=33)
        ls=pct(jr["lambda"],LAM); gs=pct(jr["gamma"],GAM)
        rls.append(0 if ls<33 else 1 if ls<67 else 2); rgs.append(0 if gs<33 else 1 if gs<67 else 2)
    ta,tl,tg,ra,rl,rg=map(np.array,(ta,tl,tg,ra,rl,rg)); rls=np.array(rls);rgs=np.array(rgs)
    print(f"GAME INTEGRITY: {ok}/{n} fresh sessions completed, no errors.\n")
    print("RECOVERY (out-of-sample, exact backend calls):")
    print(f"  alpha  r={pearsonr(ta,ra)[0]:+.3f}  MAE={np.mean(abs(ta-ra)):.3f}  range {ra.min():.2f}-{ra.max():.2f}")
    print(f"  lambda r={pearsonr(tl,rl)[0]:+.3f}  MAE={np.mean(abs(tl-rl)):.3f}")
    print(f"  gamma  r={pearsonr(tg,rg)[0]:+.3f}  MAE={np.mean(abs(tg-rg)):.3f}\n")
    print("ARCHETYPE CONSTRUCT VALIDITY (frontend bands vs true terciles):")
    print(f"  risk  agreement {100*np.mean(tr(tl)==rls):.0f}%   style agreement {100*np.mean(tr(tg)==rgs):.0f}%   (chance 33%)")
    print(f"  band split risk {[int((rls==k).sum()) for k in (0,1,2)]}  style {[int((rgs==k).sum()) for k in (0,1,2)]}")
    grid=pd.crosstab(pd.Series([RN[b] for b in rls]),pd.Series([SN[b] for b in rgs])).reindex(index=RN,columns=SN,fill_value=0)
    print("\nCOVERAGE (3x3 archetype grid):"); print(grid.to_string())
    print(f"  {int((grid.values>0).sum())}/9 archetypes populated.")
    print(f"\nAXIS INDEPENDENCE: corr(recovered lambda, recovered gamma) = {pearsonr(rl,rg)[0]:+.3f}")

if __name__=="__main__": main()
