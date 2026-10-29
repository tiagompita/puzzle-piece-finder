"""Run segment_pieces(debug=True) + classify_pieces on every scan/photo; save overlays + stats."""
import os, sys, time, json, glob
import numpy as np
from PIL import Image, ImageDraw
REPO = r"C:/Users/Tiago/Desktop/puzzle-piece-finder"
sys.path.insert(0, REPO)
from src.segmentation import segment_pieces
from src.edges import classify_pieces
OUT = os.path.join(REPO, "docs", "diagnostico", "segmentacao")
S = os.path.join(os.environ.get("PPF_SCRATCH", "scratch"), "seg")
os.makedirs(OUT, exist_ok=True); os.makedirs(S, exist_ok=True)

files = sorted(glob.glob(os.path.join(REPO, "images/pieces/*.jpg"))) + \
        sorted(glob.glob(os.path.join(REPO, "images/pieces/Phone Link/*.jpeg"))) + \
        [os.path.join(REPO, "images/pieces/IMG_2114.DNG")]
stats = []
for f in files:
    name = os.path.splitext(os.path.basename(f))[0].replace("digitalização_fundo_", "scan_").replace("digitalizado com impressora", "scan_impressora_branco").replace(" ", "_")
    im = Image.open(f); im.load(); im = im.convert("RGB")
    t = time.time()
    res = segment_pieces(im, debug=True)
    dt = time.time() - t
    rec = {"file": os.path.relpath(f, REPO), "name": name, "size": im.size, "seconds": round(dt, 1)}
    if "error" in res:
        rec["error"] = res["error"]; stats.append(rec); print(name, "ERROR", res["error"]); continue
    pieces = res["pieces"]
    classify_pieces(pieces)
    for p in pieces:
        if p.get("is_cluster"): p["piece_type"] = "cluster"
    types = {}
    for p in pieces: types[p["piece_type"]] = types.get(p["piece_type"], 0) + 1
    areas = [p["area_px"] for p in pieces if not p["is_cluster"]]
    rec.update({"count": res["count"], "clusters": sum(p["is_cluster"] for p in pieces),
                "types": types, "working_scale": round(res["working_scale"], 4),
                "bg_model": res.get("background_model"),
                "area_median": float(np.median(areas)) if areas else None,
                "area_cv": float(np.std(areas) / np.mean(areas)) if areas else None,
                "sides_straight_hist": {}})
    for p in pieces:
        if p["is_cluster"]: continue
        k = str(p["straight_sides"]); rec["sides_straight_hist"][k] = rec["sides_straight_hist"].get(k, 0) + 1
    # overlay: labels_overlay from debug + our own annotated full-res (downscaled) with bbox, index, type
    dbg = res["debug"]
    dbg["labels_overlay"].save(os.path.join(OUT, f"{name}__labels.jpg"), quality=80)
    dbg["binary_mask"].save(os.path.join(OUT, f"{name}__mask.png"))
    ann = im.copy(); d = ImageDraw.Draw(ann)
    W, H = ann.size; lw = max(2, W // 800)
    colors = {"interior": (0, 200, 0), "edge": (255, 160, 0), "corner": (255, 0, 0), "suspect": (255, 0, 255), "cluster": (0, 0, 0)}
    for p in pieces:
        x, y, w, h = p["bbox"]; c = colors.get(p["piece_type"], (255, 255, 255))
        d.rectangle([x, y, x + w, y + h], outline=c, width=lw)
        cnt = np.asarray(p["contour"]).reshape(-1, 2)
        if len(cnt) > 2: d.line([tuple(map(int, q)) for q in cnt] + [tuple(map(int, cnt[0]))], fill=(255, 255, 0), width=lw)
        d.text((x + 4, y + 4), f"{p['index']+1}:{p['piece_type'][:3]}", fill=c)
    ann.thumbnail((1800, 1800)); ann.save(os.path.join(OUT, f"{name}__contours.jpg"), quality=80)
    # persist pieces for downstream experiments (image, mask, contour, bbox, type)
    np.savez_compressed(os.path.join(S, f"{name}.npz"),
        images=np.array([np.asarray(p["image"].convert("RGB")) for p in pieces], dtype=object),
        masks=np.array([np.asarray(p["mask"]) for p in pieces], dtype=object),
        contours=np.array([np.asarray(p["contour"]).reshape(-1, 2) for p in pieces], dtype=object),
        bboxes=np.array([p["bbox"] for p in pieces]), angles=np.array([p["angle"] for p in pieces]),
        types=np.array([p["piece_type"] for p in pieces]), is_cluster=np.array([p["is_cluster"] for p in pieces]),
        straight=np.array([p["straight_sides"] for p in pieces]),
        sides=np.array([p["sides"] for p in pieces]), devs=np.array([p["side_deviations"] for p in pieces]))
    stats.append(rec)
    print(f"{name:38s} {im.size} n={res['count']:3d} clusters={rec['clusters']:2d} types={types} areaCV={rec['area_cv']:.2f} t={dt:.1f}s bg={rec['bg_model']}", flush=True)
with open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8") as fh: json.dump(stats, fh, indent=1, ensure_ascii=False)
