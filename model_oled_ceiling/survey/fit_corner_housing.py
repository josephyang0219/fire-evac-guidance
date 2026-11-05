import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sc=bpy.data.scenes['Assembly_Full']; dg=bpy.context.evaluated_depsgraph_get()
def B(n):
  o=sc.objects[n]; me=o.evaluated_get(dg).to_mesh(); return BVHTree.FromPolygons([o.matrix_world@v.co for v in me.vertices],[p.vertices[:] for p in me.polygons])
F=B('1F_樓層'); C=B('1F_天花板'); L=B('1F_天花板封孔板')
cache={}
def blocked(x,y):
  k=(round(x,2),round(y,2))
  if k in cache: return cache[k]
  z=-1;h=[]
  while True:
    r=F.ray_cast(Vector((x,y,z)),Vector((0,0,1)),200)
    if r[0] is None: break
    h.append(r[0].z); z=r[0].z+1e-3
  b=any(h[i+1]>9 and h[i]<107.95 for i in range(0,len(h)-1,2))
  if not b:
    c=C.ray_cast(Vector((x,y,100)),Vector((0,0,1)),20)[0]; l=L.ray_cast(Vector((x,y,100)),Vector((0,0,1)),20)[0]
    b=(c is not None and (c.z<107.9 or c.z>108.05)) or (c is None and not (l is not None and l.z>115.9)) or (l is not None and l.z<109)
  cache[k]=b; return b
def free(cx,cy,hx,hy):
  n=int(2*hx/0.25); m=int(2*hy/0.25)
  for i in range(n+1):
    x=cx-hx+2*hx*i/n
    if blocked(x,cy-hy) or blocked(x,cy+hy): return False
  for j in range(m+1):
    y=cy-hy+2*hy*j/m
    if blocked(cx-hx,y) or blocked(cx+hx,y): return False
  for i in range(1,int(2*hx)):
    for j in range(1,int(2*hy)):
      if blocked(cx-hx+i,cy-hy+j): return False
  return True
HU,HV=30.1/2,30.6/2
for J in [(-99,99),(99,-99)]:
  for long_axis in ('x','y'):
    hx,hy=(HV,HU) if long_axis=='x' else (HU,HV)
    best=None
    for g in [0.6,0.5,0.4,0.3,0.2,0.1,0.0]:
      for dx in [i*0.25 for i in range(-14,15)]:
        for dy in [i*0.25 for i in range(-14,15)]:
          cx,cy=J[0]+dx,J[1]+dy
          if free(cx,cy,hx+g,hy+g): best=(g,cx,cy); break
        if best: break
      if best: break
    print('FIT',J,'30.6 along',long_axis,best)
