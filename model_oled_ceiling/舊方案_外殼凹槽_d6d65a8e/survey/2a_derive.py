import numpy as np, sys, bpy
S=sys.argv[sys.argv.index("--")+1]
d=np.load(S+"/occ.npz"); xs=d['xs']; N=len(xs)
def g(n): return d[n.encode('unicode_escape').decode().replace(chr(92),'/')]
def inside(arr,z): return (np.sum(arr<z,axis=2)%2)==1
def save(name,rgb):
    h,w,_=rgb.shape; im=bpy.data.images.new(name,w,h)
    a=np.concatenate([rgb,np.ones((h,w,1))],axis=2).astype(np.float32)
    im.pixels.foreach_set(a.transpose(1,0,2).reshape(-1)) if False else im.pixels.foreach_set(np.ascontiguousarray(a.transpose(1,0,2)).reshape(-1))
    im.filepath_raw=S+"/"+name+".png"; im.file_format='PNG'; im.save()
F=g("1F_樓層"); C=g("1F_天花板"); P=g("1F_天花板封孔板")
# arrays indexed [ix,iy]; image pixels row = iy (bottom-up), col = ix -> transpose to [iy,ix]
wall=inside(F,60)
rgb=np.ones((N,N,3))*0.95
rgb[wall]=(0.1,0.1,0.1)
# grid lines every 10mm
for k,x in enumerate(xs):
    if abs((x+0.25)%10)<0.3: rgb[k,:,:]*=0.85; rgb[:,k,:]*=0.85
# junction marks
for i in (-1,0,1):
  for j in (-1,0,1):
    ix=np.argmin(abs(xs-i*99)); iy=np.argmin(abs(xs-j*99)); rgb[ix-2:ix+3,iy-2:iy+3]=(1,0,0)
save("map_walls",rgb.transpose(1,0,2))
# ceiling: combined stack; bottom surface = lowest hit z>100 among C,P ; holes = no material at all between 104 and 118
def zs(arr): 
    a=np.where(arr>100,arr,np.nan); return a
Cb=np.nanmin(zs(C),axis=2); Pb=np.nanmin(zs(P),axis=2)
bot=np.fmin(Cb,Pb)
Ct=np.nanmax(zs(C),axis=2); Pt=np.nanmax(zs(P),axis=2); top=np.fmax(Ct,Pt)
hole=np.isnan(bot)
rgb=np.zeros((N,N,3))
cm={105.2:(0.2,0.2,0.9),108.0:(0.3,0.8,0.3),108.2:(0.9,0.8,0.2),111.0:(0.9,0.5,0.1),111.2:(0.6,0.3,0.7),112.0:(0.5,0.9,0.9),112.8:(0.9,0.6,0.9)}
rb=np.round(bot,1)
for z,c in cm.items(): rgb[np.isclose(rb,z)]=c
other=~hole & ~np.isin(rb,list(cm)); rgb[other]=(1,1,1)
rgb[hole]=(1,0,0)
rgb[wall]*=0.5
save("map_ceil_bottom",rgb.transpose(1,0,2))
print("bottom z values:",{float(k):int(v) for k,v in zip(*np.unique(rb[~hole],return_counts=True))})
rt=np.round(top,1); print("top z values:",{float(k):int(v) for k,v in zip(*np.unique(rt[~hole],return_counts=True))})
# thickness of material = sum of intervals of union... approximate: print per-cell interval list for samples
def ints(arr,ix,iy):
    a=arr[ix,iy]; a=a[~np.isnan(a)]; return [(round(float(a[k]),1),round(float(a[k+1]),1)) for k in range(0,len(a)-1,2)]
for (x,y) in [(0,0),(99,99),(-99,-99),(99,-99),(-99,99),(0,99),(99,0),(0,-99),(-99,0),(0,80),(50,50),(-60,99),(30,0),(99,30)]:
    ix=np.argmin(abs(xs-x)); iy=np.argmin(abs(xs-y))
    print((x,y),"樓層",ints(F,ix,iy)[-2:],"天花板",ints(C,ix,iy),"封孔板",ints(P,ix,iy))
# equipment above ceiling: any object other than F,C,P occupying z in [top, 150]
occ=np.zeros((N,N),bool); low=np.full((N,N),999.0)
for k in d.files:
    if k in ('xs',): continue
    n=k.replace('/',chr(92)).encode().decode('unicode_escape')
    if n in ("1F_樓層","1F_天花板","1F_天花板封孔板"): continue
    a=d[k]; m=~np.isnan(a[:,:,0]); occ|=m; low=np.minimum(low,np.where(m,a[:,:,0],999))
rgb=np.ones((N,N,3))*0.9
rgb[hole]=(1,0,0)
lv=np.clip((low-105)/45,0,1); rgb[occ]=np.stack([lv[occ]*0.2,0.3+0.7*lv[occ],1-lv[occ]],axis=1)
rgb[wall]*=0.6
save("map_above",rgb.transpose(1,0,2))
np.savez_compressed(S+"/derived.npz",xs=xs,wall=wall,bot=bot,top=top,hole=hole,occ=occ,low=low)
