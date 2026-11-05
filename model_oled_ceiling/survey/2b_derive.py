import numpy as np, sys, bpy
S=sys.argv[sys.argv.index("--")+1]
d=np.load(S+"/occ.npz"); xs=d['xs']; N=len(xs)
names={k:k.replace('/',chr(92)).encode().decode('unicode_escape') for k in d.files if k!='xs'}
inv={v:k for k,v in names.items()}
def save(name,rgb):
    h,w,_=rgb.shape; im=bpy.data.images.new(name,w,h)
    a=np.concatenate([rgb,np.ones((h,w,1))],axis=2).astype(np.float32)
    im.pixels.foreach_set(np.ascontiguousarray(a).reshape(-1)); im.filepath_raw=S+"/"+name+".png"; im.file_format='PNG'; im.save()
def ivs(a):
    a=a[~np.isnan(a)]; return [(float(a[i]),float(a[i+1])) for i in range(0,len(a)-1,2)]
C=d[inv["1F_天花板"]]; P=d[inv["1F_天花板封孔板"]]; F=d[inv["1F_樓層"]]
solid_top=np.full((N,N),np.nan); gap=np.zeros((N,N),bool)
for ix in range(N):
  for iy in range(N):
    iv=sorted([t for t in ivs(C[ix,iy])+ivs(P[ix,iy]) if t[1]>100])
    if not iv or abs(iv[0][0]-108.0)>0.05: continue
    top=iv[0][1]
    for a,b in iv[1:]:
        if a<=top+0.05: top=max(top,b)
        else: gap[ix,iy]=True; break
    solid_top[ix,iy]=top
# free space above solid top: lowest object (other than C,P,F) bottom above solid top
free=np.full((N,N),99.0)
for k,n in names.items():
    if n in ("1F_樓層","1F_天花板","1F_天花板封孔板"): continue
    a=d[k]
    for ix in range(N):
      for iy in range(N):
        if np.isnan(a[ix,iy,0]): continue
        for z0,z1 in ivs(a[ix,iy]):
            base=solid_top[ix,iy] if not np.isnan(solid_top[ix,iy]) else 108
            if z1>base+0.01: free[ix,iy]=min(free[ix,iy],max(0,z0-base)); break
# 1F floor wall under ceiling: any 樓層 material in z 9..107.5
wallany=np.zeros((N,N),bool)
for ix in range(N):
  for iy in range(N):
    for z0,z1 in ivs(F[ix,iy]):
        if z1>9 and z0<107.5: wallany[ix,iy]=True
np.savez_compressed(S+"/derived2.npz",xs=xs,solid_top=solid_top,gap=gap,free=free,wallany=wallany)
rgb=np.zeros((N,N,3))
cmap={112.0:(0.9,0.3,0.3),112.8:(0.9,0.5,0.5),115.0:(0.3,0.6,0.9),116.0:(0.3,0.8,0.3),117.6:(0.6,0.9,0.6)}
r=np.round(solid_top,1)
for z,c in cmap.items(): rgb[np.isclose(r,z)]=c
rgb[np.isnan(solid_top)]=(0,0,0)
rgb[gap]*=0.6
fr=np.clip(free/12,0,1); m=free<12
rgb[m]=rgb[m]*0.4+np.stack([fr[m],fr[m]*0.6,0*fr[m]],1)*0.6
rgb[wallany]=(1,1,1)
save("map_solid",rgb.transpose(1,0,2))
print({float(k):int(v) for k,v in zip(*np.unique(r[~np.isnan(r)],return_counts=True))})
