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
targets=[(0.0,-6.47),(-36.5,84.28),(84.28,-36.5),(-36.5,-84.28),(-84.28,-36.5)]
for W,H,lab in ((82.5,54.5,"half 400-tie"),(54.5,82.5,"half 400-tie rot"),(47,35,"mini 170-tie"),(35,47,"mini rot")):
    best=[]
    for cx in np.arange(-110,110.01,1.0):
        for cy in np.arange(-110,110.01,1.0):
            if q(cx-W/2,cx+W/2,cy-H/2,cy+H/2): continue
            L=sum(abs(cx-tx)+abs(cy-ty) for tx,ty in targets)
            best.append((L,cx,cy))
    best.sort()
    print("H5",lab,len(best),best[:3],flush=True)
# free-area ASCII map (4 mm)
for y in np.arange(116,-117,-4):
    j=np.argmin(abs(xs-y)); print("FM %5d "%y+"".join("#" if bad[np.argmin(abs(xs-x)),j] else "." for x in np.arange(-116,117,3)))
