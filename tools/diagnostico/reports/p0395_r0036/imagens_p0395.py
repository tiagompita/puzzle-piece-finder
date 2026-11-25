# Imagens e números de P0395 / G0033 (só leitura do projeto dado em argv[1]); saída em argv[2] com sufixo argv[3]
import sys,numpy as np,cv2
sys.path.insert(0,'.')
from PIL import Image
from src.state import Project
from src import grupos, render
from src.locate import body_beta_deg, body_center_mm
pr=Project.open(sys.argv[1]); out=sys.argv[2]; suf=sys.argv[3]
p=pr.piece('P0395'); sh=pr.shape('P0395')
print('piece', p.estado, p.cls, p.chords_mm, p.bbox, p.area_mm2, p.flags)
print('shape cls',sh.cls,'types',sh.types,'chords',[round(x,2) for x in sh.lens],'body_angle',round(sh.body_angle_deg,2),'beta',round(body_beta_deg(sh),2),'centro',np.round(body_center_mm(sh),2))
print('corners mm', np.round(sh.c[sh.corners],2).tolist())
print('theta grupo', grupos.group_theta(pr,'P0395',0))
rgba=grupos.group_rgba(pr,'G0033',0,96.0)
Image.fromarray(rgba).save(f'{out}/04_grupo_G0033_{suf}.png')
rd=render.piece_rgba_for_display(pr,'P0395') if hasattr(render,'piece_rgba_for_display') else None
if rd is not None:
    im=rd[0] if isinstance(rd,tuple) else rd
    Image.fromarray(np.asarray(im)).save(f'{out}/03_display_clean_{suf}.png')
# cantos e lados sobre a folha
c=pr.contour_px('P0395'); mm=25.4/300
im=np.array(Image.open('images/pieces/legado/montado_p05_300dpi.jpg').convert('RGB'))[:,:,::-1].copy()
x0,y0=1990,3150; crop=im[y0:3504,x0:2544].copy()
cols=[(0,0,255),(0,200,0),(255,0,0),(0,200,255)]
cpx=sh.c/mm
for i,s in enumerate(sh.sides):
    a=np.round(np.array([s.p0_mm,s.p1_mm])/mm-[x0,y0]).astype(int)
    cv2.line(crop,tuple(a[0]),tuple(a[1]),cols[i],1)
    m=a.mean(0); cv2.putText(crop,f'{i}:{s.kind} {s.chord_mm:.1f}',tuple(int(v) for v in m+[-30,-4]),cv2.FONT_HERSHEY_SIMPLEX,0.45,cols[i],1)
cv2.polylines(crop,[np.round(cpx-[x0,y0]).astype(np.int32)],True,(255,255,255),1)
for k in sh.corners: cv2.circle(crop,tuple(np.round(cpx[k]-[x0,y0]).astype(int)),5,(0,0,255),2)
bx,by,bw,bh=p.bbox; cv2.rectangle(crop,(bx-x0,by-y0),(bx-x0+bw,by-y0+bh),(0,255,255),1)
cv2.imwrite(f'{out}/06_cantos_lados_{suf}.png',cv2.resize(crop,None,fx=2,fy=2))
