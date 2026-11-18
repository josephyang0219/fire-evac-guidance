# 2F 角落 OLED 位置搜尋：1F 的位置在 2F 會壓到較大的房間塊，找最小移位（用法：python search_2f_corners.py <fire_model.blend>）
import bpy, sys, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
sc=bpy.data.scenes["Assembly_Full"]
def B(n):
    o=sc.objects[n];M=o.matrix_world
    return BVHTree.FromPolygons([M@v.co for v in o.data.vertices],[p.vertices[:] for p in o.data.polygons])
bf,bc,bl=B("2F_樓層"),B("2F_天花板"),B("2F_天花板封孔板")
Z=Vector((0,0,1));dz=150
def stack(b,x,y,z0,lim):
    hs=[]
    while True:
        h=b.ray_cast(Vector((x,y,z0)),Z,lim)
        if h[0] is None:break
        hs.append(h[0].z);z0=h[0].z+1e-3
    return hs
def wall(x,y):
    hs=stack(bf,x,y,-1+dz,300)
    return any(hs[i+1]>98+dz and hs[i]<107.95+dz for i in range(0,len(hs)-1,2))
def solid(x,y):
    iv=sorted([(round(a-dz,2),round(b-dz,2)) for a,b in zip(*[iter(stack(bc,x,y,100+dz,40))]*2)]+[(round(a-dz,2),round(b-dz,2)) for a,b in zip(*[iter(stack(bl,x,y,100+dz,40))]*2)])
    cov=108.2
    for a,b in iv:
        if a>cov+0.05: return False
        cov=max(cov,b)
    return cov>=117.55
D={"N":(0,1),"E":(1,0),"S":(0,-1),"W":(-1,0)}
P={"NW":((-97,100),"E"),"NE":((100,97),"S"),"SE":((99,-101),"S"),"SW":((-100,-97),"N")}
for nm,(c,up) in P.items():
    upv=Vector((*D[up],0)); r=Z.cross(upv)
    best=None
    cands=sorted([(dx/4,dy/4) for dx in range(-24,25) for dy in range(-24,25)], key=lambda t:math.hypot(*t))
    for dx,dy in cands:
        cc=Vector((c[0]+dx,c[1]+dy,0))
        W=lambda u,v: cc+u*r+v*upv
        ok=True
        for k in range(16):
            for m in range(16):
                q=W(-13.9-0.6+(27.8+1.2)*k/15,-13.65-0.6+(27.3+1.2)*m/15)
                if wall(q.x,q.y): ok=False;break
            if not ok:break
        if not ok: continue
        sl=W(0,13.65-1.68); long_x=abs(r.x)>0.5; hx,hy=(5.7,1.7) if long_x else (1.7,5.7)
        for k in range(13):
            for m in range(7):
                if not solid(sl.x-hx-0.8+(2*hx+1.6)*k/12, sl.y-hy-0.8+(2*hy+1.6)*m/6): ok=False;break
            if not ok:break
        if ok: best=(dx,dy);break
    print(nm,"best shift",best)
