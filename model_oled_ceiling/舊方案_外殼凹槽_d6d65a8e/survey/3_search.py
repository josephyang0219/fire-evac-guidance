import numpy as np, sys, json
A=sys.argv[sys.argv.index("--")+1:]; S=A[0]; RELAX=A[1]=='1'; NOEXIT=A[2]=='1'
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
res={}
for vn,D in V.items():
    pocket_top=108+D['depth']+0.1
    bad_ceil=np.isnan(st)|(st<pocket_top+TMIN-1e-6)
    if RELAX: bad_ceil&=~groove
    s_ceil=sat(dil(bad_ceil,0.8)); s_below=sat(dil(wallany|ribs,0.25))
    need=108+D['depth']-1.5+2.5+14+2
    s_slot=sat(np.isnan(st)|(np.nan_to_num(st)+free<need)|(groove if RELAX else False))
    s_cap=sat(np.isnan(st)|(np.nan_to_num(st)<115.9)|(np.nan_to_num(st)+free<need+1))
    su0,sv0=(10.16+0.6)/2,(2.54+0.6)/2
    if D['hdr_along']=="v": su0,sv0=sv0,su0
    for J in [(i*99,j*99) for j in (1,0,-1) for i in (-1,0,1)]:
        best_rot={}
        cand=[]
        for rot in (0,90,180,270):
            aa=rotp(D['aa'],rot); hd=rotp(D['hdr'],rot)
            for cx in np.arange(J[0]-45,J[0]+45.01,0.5):
                for cy in np.arange(J[1]-45,J[1]+45.01,0.5):
                    b=box(cx,cy,D['pw']/2+CLR,D['ph']/2+CLR,rot)
                    if q(s_ceil,*b) or q(s_below,*b): continue
                    hx,hy=cx+hd[0],cy+hd[1]
                    if not NOEXIT and q(s_slot,*box(hx,hy,su0+1.5,sv0+1.5,rot)): continue
                    if not NOEXIT and q(s_cap,*box(hx,hy,su0+4,sv0+4,rot)): continue
                    ax,ay=cx+aa[0],cy+aa[1]
                    cand.append((float(np.hypot(ax-J[0],ay-J[1])),float(cx),float(cy),rot,float(ax),float(ay),float(hx),float(hy)))
        for c in cand:
            best_rot.setdefault(c[3],c) if c[0]<=best_rot.get(c[3],(1e9,))[0] else None
        cand.sort(); res[f"{vn}|{J[0]},{J[1]}"]=cand[:300]
        if cand:
            b=cand[0]; print(vn,J,"n=%d best AA-offset %.1f  PCB (%.1f,%.1f) rot %d AA (%.1f,%.1f) hdr (%.1f,%.1f)"%((len(cand),)+b),flush=True)
        else: print(vn,J,"NO FIT",flush=True)
json.dump(res,open(S+"/search_%d%d.json"%(RELAX,NOEXIT),"w"))
