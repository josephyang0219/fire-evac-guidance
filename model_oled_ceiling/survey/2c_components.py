import numpy as np, sys
from collections import deque
S=sys.argv[sys.argv.index("--")+1]
d=np.load(S+"/derived.npz"); d2=np.load(S+"/derived2.npz"); xs=d['xs']; N=len(xs)
bot=d['bot']; hole=d['hole']; st=d2['solid_top']; gap=d2['gap']
def comps(mask,label):
    seen=np.zeros_like(mask); out=[]
    for i in range(N):
        for j in range(N):
            if mask[i,j] and not seen[i,j]:
                q=deque([(i,j)]); seen[i,j]=1; cells=[]
                while q:
                    a,b=q.popleft(); cells.append((a,b))
                    for da,db in ((1,0),(-1,0),(0,1),(0,-1)):
                        u,v=a+da,b+db
                        if 0<=u<N and 0<=v<N and mask[u,v] and not seen[u,v]: seen[u,v]=1; q.append((u,v))
                c=np.array(cells); out.append((len(c),xs[c[:,0].min()]-.25,xs[c[:,0].max()]+.25,xs[c[:,1].min()]-.25,xs[c[:,1].max()]+.25))
    print("==",label,len(out))
    for n,x0,x1,y0,y1 in sorted(out,key=lambda t:(t[3],t[1])):
        if n>=2: print(f"  n={n*0.25:7.1f}mm2 x[{x0:7.2f},{x1:7.2f}] y[{y0:7.2f},{y1:7.2f}]  size {x1-x0:.1f}x{y1-y0:.1f}")
inner=(abs(xs)[:,None]<120)&(abs(xs)[None,:]<120)
comps(hole&inner,"through holes (no ceiling/plug)")
comps(np.isclose(bot,108.2,atol=0.05),"plugs (封孔板 from below)")
comps(np.isclose(bot,116.0,atol=0.05),"blind-from-below to 116")
comps(np.isclose(bot,111.2,atol=0.05),"bottom 111.2")
comps(np.isclose(bot,105.2,atol=0.05),"ribs 105.2")
comps(np.isclose(st,112.0,atol=0.05),"groove (solid top 112)")
comps(np.isclose(st,115.0,atol=0.05),"top 115 (no sheet)")
comps(np.isclose(st,116.0,atol=0.05),"top 116")
