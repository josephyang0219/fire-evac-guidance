import bpy, numpy as np, sys, math, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
S=sys.argv[sys.argv.index("--")+1]
d=np.load(S+"/derived.npz"); d2=np.load(S+"/derived2.npz"); xs=d['xs']; N=len(xs); R=0.5; X0=xs[0]
bot=d['bot']; hole=d['hole']; wallany=d2['wallany']
ribs=np.isclose(bot,105.2,atol=0.05); plug=np.isclose(bot,108.2,atol=0.05)
lens=np.zeros((N,N),bool)
for (x0,x1,y0,y1) in [(-11.5,11.5,81,100),(-11.5,11.5,-100,-81),(81,100,-11.5,11.5),(-100,-81,-11.5,11.5)]:
    lens|=(xs[:,None]>=x0)&(xs[:,None]<=x1)&(xs[None,:]>=y0)&(xs[None,:]<=y1)
small=(hole&~lens)|np.isclose(bot,116.0,atol=0.05)          # 5x5 路口孔：可以被外殼蓋住（線從孔上去）
ok108=np.isclose(bot,108.0,atol=0.05)|small
def dil(m,mm):
    k=int(round(mm/R)); out=m.copy()
    for dx in range(-k,k+1):
        for dy in range(-k,k+1):
            if dx*dx+dy*dy<=k*k: out|=np.roll(np.roll(m,dx,0),dy,1)
    return out
bad=dil(~ok108 & ~(wallany|ribs),0.0)|dil(plug,1.0)|dil(lens,1.0)|dil(wallany|ribs,0.5)|~ok108
def sat(m):
    s=np.zeros((N+1,N+1)); s[1:,1:]=np.cumsum(np.cumsum(m.astype(float),0),1); return s
SB=sat(bad)
def q(x0,x1,y0,y1):
    i0=int(np.ceil((x0-X0)/R-1e-6)); i1=int(np.floor((x1-X0)/R+1e-6)); j0=int(np.ceil((y0-X0)/R-1e-6)); j1=int(np.floor((y1-X0)/R+1e-6))
    if i0<0 or j0<0 or i1>=N or j1>=N: return 1e9
    return SB[i1+1,j1+1]-SB[i0,j1+1]-SB[i1+1,j0]+SB[i0,j0]
sc=bpy.data.scenes["Assembly_Full"]; dg=bpy.context.evaluated_depsgraph_get()
def bvh(o):
    me=o.evaluated_get(dg).to_mesh(); M=o.matrix_world
    return BVHTree.FromPolygons([M@v.co for v in me.vertices],[p.vertices[:] for p in me.polygons])
occ=[bvh(o) for o in sc.objects if o.type=='MESH' and (o.name.startswith("1F_") or o.name.startswith("2F_")) and "Lens" not in o.name and "HUB8735" not in o.name]
CAMS={"N":0.0,"W":90.0,"E":-90.0,"S":180.0}
cams=[]
for fl,dz in (("1F",0),("2F",150)):
    for cn,rz in CAMS.items():
        Rz=Matrix.Rotation(math.radians(rz),3,"Z")
        cams.append((fl+cn,Rz@Vector((0,92,111+dz)),Rz@Matrix.Rotation(math.radians(-18),3,"X")@Vector((0,0,-1))))
def visible(cx,cy,hw,hh,h):
    pts=[]
    for i in range(7):
        for j in range(7):
            pts.append(Vector((cx-hw+2*hw*i/6,cy-hh+2*hh*j/6,108-h)))
    for t in np.linspace(0,1,7):
        for zz in (108-h, 108-h/2, 108-0.3):
            pts+= [Vector((cx-hw+2*hw*t,cy-hh-0.01,zz)),Vector((cx-hw+2*hw*t,cy+hh+0.01,zz)),Vector((cx-hw-0.01,cy-hh+2*hh*t,zz)),Vector((cx+hw+0.01,cy-hh+2*hh*t,zz))]
    seen={}
    for name,c,ax in cams:
        best=None
        for p in pts:
            v=p-c; ang=math.degrees(ax.angle(v))
            if ang>65: continue
            if any(b.ray_cast(c,v.normalized(),v.length-0.05)[0] is not None for b in occ): continue
            best=min(best or 99,ang)
        if best is not None: seen[name]=round(best)
    return seen

def vis_pts(pts):
    seen={}
    for name,c,ax in cams:
        for p in pts:
            v=p-c; ang=math.degrees(ax.angle(v))
            if ang>65: continue
            if any(b.ray_cast(c,v.normalized(),v.length-0.05)[0] is not None for b in occ): continue
            seen[name]=min(seen.get(name,99),round(ang))
    return seen
for cx in (-26,-28,-30,-33,-36.5):
    print("VISC module",cx,visible(cx,96.5,13.9,13.65,5.0),flush=True)
# wire along underside from header (-26,84.3) west to x=-32, z 107.3 (Dupont housings lying flat would be ~2.5 thick: test z 105.5..107.5)
pts=[Vector((x,84.3,z)) for x in np.arange(-32,-25,0.5) for z in (105.5,106.5,107.4)]
print("VISC wire",vis_pts(pts))
