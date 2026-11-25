import json,sys,numpy as np,cv2
sys.path.insert(0,'.')
from src import overrides as OV
from src.state import Project
pr=Project.open('projects/alpes')
mm=25.4/300
allv=OV.latest_overrides(pr, incluir_reposicao=True)
act=OV.latest_overrides(pr)
for pid,o in sorted(allv.items()):
    ci=np.array(o['contour_px'],float)
    tag=f"{pid} t={o['t']} met={o.get('metodo')} conv={o.get('convencao')} ind={o.get('indice')} ativo={pid in act}"
    if not o.get('aresta_px'):
        print(tag); continue
    ca=np.array(o['aresta_px'],float)
    x0,y0=np.floor(np.minimum(ci.min(0),ca.min(0))).astype(int)-5; x1,y1=np.ceil(np.maximum(ci.max(0),ca.max(0))).astype(int)+5
    sh=(y1-y0,x1-x0)
    def fill(c):
        m=np.zeros(sh,np.uint8); cv2.fillPoly(m,[np.round(c-[x0,y0]).astype(np.int32)],1); return m>0
    mi,ma=fill(ci),fill(ca)
    d=cv2.distanceTransform((~ma).astype(np.uint8),cv2.DIST_L2,5)*mm
    out=mi&~ma
    din=cv2.distanceTransform(ma.astype(np.uint8),cv2.DIST_L2,5)*mm
    cut=ma&~mi
    print(tag, f"idx-fora-aresta {out.sum()*mm*mm:.1f}mm2 maxdist {d[out].max() if out.any() else 0:.2f} p99 {np.percentile(d[out],99) if out.any() else 0:.2f} >2mm {(out&(d>2)).sum()*mm*mm:.2f}mm2 >1.5 {(out&(d>1.5)).sum()*mm*mm:.2f} | aresta-fora-idx {cut.sum()*mm*mm:.1f} maxd {din[cut].max() if cut.any() else 0:.2f}")
