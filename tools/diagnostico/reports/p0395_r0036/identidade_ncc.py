import sys; argv=list(sys.argv); sys.argv=[sys.argv[0],argv[1],argv[2]+'/x.json']
exec(open(sys.argv[0].replace('identidade_ncc.py','identidade.py'),encoding='utf-8').read().split("art=L.CellArt.load")[0])
import numpy as np, cv2
def fine(a,b):
    ic=img_cmp(a,b); wa,crb,m=ic['vis']
    La=cv2.GaussianBlur(lab(wa)[...,0],(0,0),3); Lb=cv2.GaussianBlur(lab(crb)[...,0],(0,0),3)
    h,w=La.shape; c=(w/2,h/2); best=(-2,None)
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(41,41)); mm_=cv2.erode(m.astype(np.uint8),k)>0
    for ang in np.arange(-3,3.01,1.0):
        for dx in range(-20,21,2):
            for dy in range(-20,21,2):
                M=cv2.getRotationMatrix2D(c,ang,1.0); M[:,2]+=[dx,dy]
                A2=cv2.warpAffine(La,M,(w,h)); 
                x=A2[mm_]-A2[mm_].mean(); y=Lb[mm_]-Lb[mm_].mean()
                n=float((x*y).sum()/np.sqrt((x*x).sum()*(y*y).sum()))
                if n>best[0]: best=(n,(ang,dx,dy))
    return round(best[0],3),best[1]
pairs=[('P0782','P0005'),('P0021','P0005')]
for a,b in pairs: print(a,b,fine(a,b))
