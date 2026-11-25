# C3: identidade de P0395 (forma corrigida, cópia do projeto em argv[1])
import sys, json, numpy as np, cv2
sys.path.insert(0,'.')
from src.state import Project
from src import shape as SH, overrides as OV, render as R, locate as L
from src.locate import body_beta_deg
cp=sys.argv[1]; pr=Project.open(cp); prof=pr.profile
A='P0395'; sa=pr.shape(A)
rows,cols=prof.rows,prof.cols
def border(cell): return cell is not None and (cell[0] in (1,rows) or cell[1] in (1,cols))
def twin(cell): return (rows+1-cell[0], cols+1-cell[1])
cands=[]
for p in pr.pieces.values():
    if p.id==A or p.estado=='descartada': continue
    sb=pr.shape(p.id)
    if sb is None or not sb.ok: continue
    if not (p.n_flat>=1 or border(p.celula)): continue
    rms,_,phi=SH.free_dist(sa,sb)
    cands.append((rms,p.id,p.estado,tuple(p.celula) if p.celula else None,sb.cls,phi))
cands.sort()
print('candidatos com F ou em borda:',len(cands))
scans={}
def scan(sid):
    if sid not in scans: scans[sid]=OV.load_scan_rgb(pr,sid)
    return scans[sid]
def lab(x): return cv2.cvtColor(x,cv2.COLOR_RGB2LAB).astype(np.float32)*np.array([100/255,1,1],np.float32)-np.array([0,128,128],np.float32)
mm=25.4/300
def img_cmp(a,b):
    """P0395 (a) registada sobre b (contornos em mm, register_rigid), imagem do scan de a levada ao scan de b:
    dE médio e NCC de L* no interior comum (erodido 1 mm)."""
    pa,pb=pr.piece(a),pr.piece(b)
    ca=np.asarray(pr.contour_px(a),float)*mm; cb=np.asarray(pr.contour_px(b),float)*mm
    reg=SH.register_rigid(ca,cb)
    src=SH._resample_closed(ca,400) if False else ca
    # afim exata src->dst a partir dos pontos transformados
    P=np.asarray(reg['points_mm']); M,_=cv2.estimateAffinePartial2D(ca.astype(np.float32),P.astype(np.float32))
    M[:,2]/=mm  # px->px (mesma escala)
    ra,rb=scan(pa.scan_id),scan(pb.scan_id)
    x0,y0,w,h=cv2.boundingRect(np.round(cb/mm).astype(np.int32)); pad=10
    x0-=pad;y0-=pad;w+=2*pad;h+=2*pad
    T=np.array([[1,0,-x0],[0,1,-y0],[0,0,1]],float)
    M3=T@np.vstack([M,[0,0,1]])
    wa=cv2.warpAffine(ra,M3[:2],(w,h),flags=cv2.INTER_LINEAR)
    ma=np.zeros(ra.shape[:2],np.uint8); cv2.fillPoly(ma,[np.round(ca/mm).astype(np.int32)],1)
    wma=cv2.warpAffine(ma,M3[:2],(w,h),flags=cv2.INTER_NEAREST)
    crb=rb[y0:y0+h,x0:x0+w]
    mb=np.zeros((h,w),np.uint8); cv2.fillPoly(mb,[np.round(cb/mm-[x0,y0]).astype(np.int32)],1)
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(25,25))
    m=(cv2.erode(wma,k)>0)&(cv2.erode(mb,k)>0)
    la,lb=lab(wa)[m],lab(crb)[m]
    dE=float(np.sqrt(((la-lb)**2).sum(1)).mean())
    x,y=la[:,0]-la[:,0].mean(),lb[:,0]-lb[:,0].mean()
    ncc=float((x*y).sum()/np.sqrt((x*x).sum()*(y*y).sum()))
    return dict(rms_reg=round(reg['rms_mm'],3),dE=round(dE,1),ncc=round(ncc,3),n=int(m.sum()),vis=(wa,crb,m))
art=L.CellArt.load(prof,'.')
rgbaA=R.piece_rgba_for_display(pr,A); rgbaA=rgbaA[0] if isinstance(rgbaA,tuple) else rgbaA
def art_cell(pid,cell):
    sh=pr.shape(pid); rg=R.piece_rgba_for_display(pr,pid); rg=rg[0] if isinstance(rg,tuple) else rg
    b=body_beta_deg(sh); best=None
    for k in range(4):
        r=L.render_item(np.asarray(rg),sh,b+90*k,art,mm)
        d=L.de_cell(r,cell[0],cell[1],art)
        if best is None or d['dE']<best[0]: best=(d['dE'],d['ncc'],b+90*k)
    return best
res=[]
for rms,pid,est,cell,cls,phi in cands[:12]:
    ic=img_cmp(A,pid)
    aA=art_cell(A,cell) if cell else None
    aB=art_cell(pid,cell) if cell else None
    res.append(dict(pid=pid,estado=est,cell=cell,twin=twin(cell) if cell else None,cls=cls,free=round(rms,3),**{k:v for k,v in ic.items() if k!='vis'},
        art_P0395=None if aA is None else (round(aA[0],1),round(aA[1],2)), art_peca=None if aB is None else (round(aB[0],1),round(aB[1],2))))
    print(res[-1])
json.dump(res,open(sys.argv[2],'w'),default=str,indent=1)
