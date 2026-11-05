import bpy, numpy as np, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree
out=sys.argv[sys.argv.index("--")+1]
sc=bpy.data.scenes["Assembly_Full"]; dg=bpy.context.evaluated_depsgraph_get()
names=[o.name for o in sc.objects if o.type=='MESH' and o.name.startswith("1F_")]
def bvh(o):
    me=o.evaluated_get(dg).to_mesh(); M=o.matrix_world
    return BVHTree.FromPolygons([M@v.co for v in me.vertices],[p.vertices[:] for p in me.polygons])
# Fill objects from FireModel scene for comparison
fills=[o for o in bpy.data.objects if o.name.startswith("Fill_")]
for o in fills:
    pts=[o.matrix_world@Vector(v) for v in o.bound_box]
    mn=[min(p[i] for p in pts) for i in range(3)]; mx=[max(p[i] for p in pts) for i in range(3)]
    print("FILL",o.name,[round(a,1) for a in mn],[round(a,1) for a in mx])
xs=np.arange(-122.25,122.5,0.5); N=len(xs)
K=8
res={}
for n in names:
    if not any(k in n for k in ("樓層","天花板","封孔板","麵包版座","Lens","支撐柱","長銷","Breadboard_","PCB","Parts","Headers")): continue
    if "Rail" in n: continue
    t=bvh(sc.objects[n]); arr=np.full((N,N,K),np.nan,dtype=np.float32)
    for ix,x in enumerate(xs):
        for iy,y in enumerate(xs):
            z=-1.0; k=0
            while k<K:
                h=t.ray_cast(Vector((x,y,z)),Vector((0,0,1)),200)
                if h[0] is None: break
                arr[ix,iy,k]=h[0].z; z=h[0].z+1e-3; k+=1
    res[n]=arr; print("done",n,flush=True)
np.savez_compressed(out,xs=xs,**{n.encode('unicode_escape').decode():a for n,a in res.items()})
