import numpy as np, sys, math
S=sys.argv[sys.argv.index("--")+1]
d=np.load(S+"/derived.npz"); d2=np.load(S+"/derived2.npz"); xs=d['xs']; N=len(xs); R=0.5; X0=xs[0]
bot=d['bot']; st=d2['solid_top']; free=d2['free']
plug=np.isclose(bot,108.2,atol=0.05)
def dil(m,mm):
    k=int(round(mm/R)); out=m.copy()
    for dx in range(-k,k+1):
        for dy in range(-k,k+1):
            if dx*dx+dy*dy<=k*k: out|=np.roll(np.roll(m,dx,0),dy,1)
    return out
top=np.nan_to_num(st,nan=0)+free           # z of first 1F object above the ceiling (99+ = nothing)
low=(top<140)|np.isnan(st)                  # pods, pillars, pins, lens openings
inside=(abs(xs)[:,None]<117)&(abs(xs)[None,:]<117)
SL=[(-85.0,100.0),(100.0,85.0),(99.0,-113.0),(-100.0,-85.0),(0.0,-6.47),(43.0,97.0),(97.0,43.0),(43.0,-100.5),(-100.5,43.0)]
slots=np.zeros((N,N),bool)
for x,y in SL: slots|=(abs(xs[:,None]-x)<10)&(abs(xs[None,:]-y)<10)
bad=dil(plug,1.5)|dil(low,1.5)|slots|~inside
s=np.zeros((N+1,N+1)); s[1:,1:]=np.cumsum(np.cumsum(bad.astype(float),0),1)
def q(x0,x1,y0,y1):
    i0=int(np.ceil((x0-X0)/R)); i1=int(np.floor((x1-X0)/R)); j0=int(np.ceil((y0-X0)/R)); j1=int(np.floor((y1-X0)/R))
    if i0<0 or j0<0 or i1>=N or j1>=N: return 1e9
    return s[i1+1,j1+1]-s[i0,j1+1]-s[i1+1,j0]+s[i0,j0]

import itertools
bad2=dil(plug,0.5)|dil(low,0.5)|slots|~inside
s2=np.zeros((N+1,N+1)); s2[1:,1:]=np.cumsum(np.cumsum(bad2.astype(float),0),1)
def q2(x0,x1,y0,y1):
    i0=int(np.ceil((x0-X0)/R)); i1=int(np.floor((x1-X0)/R)); j0=int(np.ceil((y0-X0)/R)); j1=int(np.floor((y1-X0)/R))
    if i0<0 or j0<0 or i1>=N or j1>=N: return 1e9
    return s2[i1+1,j1+1]-s2[i0,j1+1]-s2[i1+1,j0]+s2[i0,j0]
res=[]
for W in (29,30,32,34,36,38,40,42,44):
    bestH=0; at=None
    for cx in np.arange(-115,115.1,1.0):
        for cy in np.arange(-115,115.1,1.0):
            if q2(cx-W/2,cx+W/2,cy-1,cy+1): continue
            lo=1; hi=230
            while lo<hi:
                m=(lo+hi+1)//2
                if q2(cx-W/2,cx+W/2,cy-m/2,cy+m/2)==0: lo=m
                else: hi=m-1
            if lo>bestH: bestH=lo; at=(cx,cy)
    print("RECT W",W,"maxH",bestH,"at",at,flush=True)
