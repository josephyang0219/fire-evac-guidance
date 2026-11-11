import numpy as np, sys, json
A=sys.argv[sys.argv.index("--")+1:]; S=A[0]; RELAX=True; NOEXIT=True
d=np.load(S+"/derived.npz"); d2=np.load(S+"/derived2.npz"); xs=d['xs']; N=len(xs); R=0.5; X0=xs[0]
bot=d['bot']; st=d2['solid_top']; free=d2['free']; wallany=d2['wallany']
ribs=np.isclose(bot,105.2,atol=0.05)
groove=np.isclose(st,112.0,atol=0.05)
def dil(m,mm):
    k=int(round(mm/R)); out=m.copy()
    for dx in range(-k,k+1):
        for dy in range(-k,k+1):
            if dx*dx+dy*dy<=k*k+1e-9: out|=np.roll(np.roll(m,dx,0),dy,1)
    return out
def sat(m):
    s=np.zeros((N+1,N+1)); s[1:,1:]=np.cumsum(np.cumsum(m.astype(float),0),1); return s
def q(s,x0,x1,y0,y1):
    i0=int(np.ceil((x0-X0)/R-1e-6)); i1=int(np.floor((x1-X0)/R+1e-6)); j0=int(np.ceil((y0-X0)/R-1e-6)); j1=int(np.floor((y1-X0)/R+1e-6))
    if i0<0 or j0<0 or i1>=N or j1>=N: return 1e9
    return s[i1+1,j1+1]-s[i0,j1+1]-s[i1+1,j0]+s[i0,j0]
V={"0.96":dict(pw=27.3,ph=27.8,depth=1.4+1.6+1.5,aa=(0.0,11.5-13.9),hdr=(0.0,13.9-1.68),hdr_along="u"),
   "0.91":dict(pw=38.0,ph=12.0,depth=1.3+1.2+1.2,aa=(21.5-19.0,0.0),hdr=(-19.0+1.68,0.0),hdr_along="v")}
CLR=0.2; TMIN=2.0
def rotp(p,rot): u,v=p; return {0:(u,v),90:(-v,u),180:(-u,-v),270:(v,-u)}[rot]
def box(cx,cy,hu,hv,rot):
    if rot in (90,270): hu,hv=hv,hu
    return cx-hu,cx+hu,cy-hv,cy+hv

# fixed pockets (PCB+0.2) of the other signs: (cx,cy,hx,hy)
FIX={"NW":(-99.5,95.5,13.85,14.1),"NE":(95.5,99.5,14.1,13.85),"SE":(95.5,-99.5,14.1,13.85),
     "N":(0,66,13.85,14.1),"S":(0,-66,13.85,14.1),"E":(66,0,14.1,13.85),"W96":(-66,0,14.1,13.85)}
WALL=1.5
def fixmask(skip):
    m=np.zeros((N,N),bool)
    for k,(cx,cy,hx,hy) in FIX.items():
        if k in skip: continue
        m|=(abs(xs[:,None]-cx)<=hx+WALL)&(abs(xs[None,:]-cy)<=hy+WALL)
    return m
def run(vn,J,win,skip=()):
    D=V[vn]; pocket_top=108+D['depth']+0.1
    bad=np.isnan(st)|(st<pocket_top+TMIN-1e-6); bad&=~groove
    s_ceil=sat(dil(bad,0.8)|fixmask(skip)); s_below=sat(dil(wallany|ribs,0.25))
    cand=[]
    for rot in (0,90,180,270):
        aa=rotp(D['aa'],rot)
        for cx in np.arange(J[0]-win,J[0]+win+0.01,0.5):
            for cy in np.arange(J[1]-win,J[1]+win+0.01,0.5):
                b=box(cx,cy,D['pw']/2+CLR,D['ph']/2+CLR,rot)
                if q(s_ceil,*b) or q(s_below,*b): continue
                ax,ay=cx+aa[0],cy+aa[1]; cand.append((float(np.hypot(ax-J[0],ay-J[1])),cx,cy,rot,ax,ay))
    cand.sort(); return cand
for WALL in (1.2,1.0,0.8,0.5,0.0):
    c=run("0.91",(0,0),50)
    print("RES C091 wall",WALL,len(c), ("best off %.1f PCB (%.1f,%.1f) rot %d AA (%.1f,%.1f)"%c[0]) if c else "")
WALL=1.5
c=run("0.96",(-99,-99),130,skip=tuple(FIX))
print("RES SW096 nofix",len(c))
for t in c[:3]: print("   off %.1f PCB (%.1f,%.1f) rot %d AA (%.1f,%.1f)"%t)
