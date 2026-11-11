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
SL=[(-85.0,100.0),(100.0,85.0),(99.0,-113.0),(-100.0,-85.0),(0.0,-6.47),(-36.5,84.28),(84.28,-36.5),(-36.5,-84.28),(-84.28,-36.5)]
slots=np.zeros((N,N),bool)
for x,y in SL: slots|=(abs(xs[:,None]-x)<10)&(abs(xs[None,:]-y)<10)
bad=dil(plug,1.5)|dil(low,1.5)|slots|~inside
s=np.zeros((N+1,N+1)); s[1:,1:]=np.cumsum(np.cumsum(bad.astype(float),0),1)
def q(x0,x1,y0,y1):
    i0=int(np.ceil((x0-X0)/R)); i1=int(np.floor((x1-X0)/R)); j0=int(np.ceil((y0-X0)/R)); j1=int(np.floor((y1-X0)/R))
    if i0<0 or j0<0 or i1>=N or j1>=N: return 1e9
    return s[i1+1,j1+1]-s[i0,j1+1]-s[i1+1,j0]+s[i0,j0]

from collections import deque
targets={"C":(0.0,-6.47),"N":(-36.5,84.28),"E":(84.28,-36.5),"S":(-36.5,-84.28),"W":(-84.28,-36.5)}
# 走線障礙：麵包板座、支撐柱、銷（low），外牆外；塞子頂面可以壓線（線可拿起）。線束寬 3 mm → 障礙外擴 1.5
obs=dil(low&~np.isnan(st)|(np.isnan(st)&~plug),1.5)|~inside
def bfs(src):
    D=np.full((N,N),-1); q=deque()
    for (i,j) in src: D[i,j]=0; q.append((i,j))
    while q:
        i,j=q.popleft()
        for di,dj in ((1,0),(-1,0),(0,1),(0,-1)):
            a,b=i+di,j+dj
            if 0<=a<N and 0<=b<N and D[a,b]<0 and not obs[a,b]: D[a,b]=D[i,j]+1; q.append((a,b))
    return D
def idx(x,y): return int(np.argmin(abs(xs-x))), int(np.argmin(abs(xs-y)))
for (cx,cy,W,H) in [(52,-84,44,31),(-84,52,30,44),(-30,18,32,31)]:
    src=[idx(x,y) for x in np.arange(cx-W/2,cx+W/2+0.1,0.5) for y in (cy-H/2,cy+H/2)]+[idx(x,y) for y in np.arange(cy-H/2,cy+H/2+0.1,0.5) for x in (cx-W/2,cx+W/2)]
    src=[t for t in src if not obs[t]]
    D=bfs(src)
    out={k:(round(D[idx(*v)]*R/10,1) if D[idx(*v)]>=0 else None) for k,v in targets.items()}
    print("PATH",(cx,cy,W,H),out,"max",max(v for v in out.values() if v),flush=True)
