import numpy as np, sys, json
A=sys.argv[sys.argv.index("--")+1:]; S=A[0]; RELAX=len(A)>1
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
import bpy
D=V["0.96"]; pocket_top=108+D['depth']+0.1
bc=np.isnan(st)|(st<pocket_top+TMIN-1e-6)
rgb=np.ones((N,N,3))*0.95
rgb[dil(bc,0.8)]=(1,0.75,0.75); rgb[bc]=(0.85,0.1,0.1)
rgb[groove]=(0.9,0.5,0.0)
bl=wallany|ribs; rgb[bl]=(0.1,0.1,0.1)
rgb[np.isclose(bot,108.2,atol=0.05)]=(0.3,0.3,1.0)   # plugs
up=(~np.isnan(st))&(np.nan_to_num(st)+free<108+D['depth']-1.5+18.5)
rgb[up&~bc]=rgb[up&~bc]*0.5+np.array((0,0.6,0))*0.5
for k,x in enumerate(xs):
    if abs((x+0.25)%10)<0.3: rgb[k,:,:]*=0.9; rgb[:,k,:]*=0.9
for i in (-1,0,1):
  for j in (-1,0,1):
    ix=np.argmin(abs(xs-i*99)); iy=np.argmin(abs(xs-j*99)); rgb[ix-1:ix+2,iy-1:iy+2]=(1,0,1)
img=rgb.transpose(1,0,2); big=np.repeat(np.repeat(img,2,0),2,1)
h,w,_=big.shape; im=bpy.data.images.new("allow",w,h)
im.pixels.foreach_set(np.ascontiguousarray(np.concatenate([big,np.ones((h,w,1))],2).astype(np.float32)).reshape(-1))
im.filepath_raw=S+"/map_allow.png"; im.file_format='PNG'; im.save()
