import sys; sys.argv=[sys.argv[0],sys.argv[1],sys.argv[2]+'/x.json']
exec(open(sys.argv[0].replace('identidade_fig.py','identidade.py'),encoding='utf-8').read().split("art=L.CellArt.load")[0])
import numpy as np, cv2
out=sys.argv[2].replace('/x.json','')
rows_img=[]
for pid in ['P0782','P0021','P0005','P0755','P0820','P0426']:
    ic=img_cmp(A,pid); wa,crb,m=ic['vis']
    H=200; f=H/wa.shape[0]
    a=cv2.resize(wa,None,fx=f,fy=f); b=cv2.resize(crb,None,fx=f,fy=f)
    row=np.hstack([a,np.full((a.shape[0],6,3),255,np.uint8),b])
    cv2.putText(row,f'P0395 -> {pid} dE {ic["dE"]} ncc {ic["ncc"]}',(5,15),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
    rows_img.append(row)
W=max(r.shape[1] for r in rows_img)
img=np.vstack([np.pad(r,((0,4),(0,W-r.shape[1]),(0,0)),constant_values=255) for r in rows_img])
cv2.imwrite('docs/diagnostico/reports/P0395-R0036/07_identidade_top5.png',img[:,:,::-1])
