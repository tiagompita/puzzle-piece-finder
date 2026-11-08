"""Sheets from files: one scanned sheet per image, one per PDF page (no new dependency).

A *sheet* is what :func:`src.ingest.segment_sheet` reads: one image file. :func:`expand_sources` turns a list of
uploaded / given files into sheets:

* an image (JPEG / PNG / TIFF, by extension and by ``PIL.Image.open``) is one sheet, the file itself (no copy);
* a PDF is one sheet per page. The PDF is read with a minimal parser over the bytes (objects, the page tree
  ``/Kids``, ``/MediaBox`` inherited from the parents, ``/Resources /XObject``): a page whose only image is a
  ``/DCTDecode`` XObject (what flatbed scanners write) gives that JPEG **as is** (no re-compression), saved as
  ``<out_dir>/<prefix>_p<k>.jpg``. Any other page (0 or > 1 images, JPX / Flate filters) gives a sheet with
  ``erro`` (rasterising needs PyMuPDF, which is not installed; the path is prepared but [NT]).

Resolution (``dpi``): from the PDF page size (``MediaBox``, 1/72 in) and the image pixels, and from the JFIF
density of the JPEG. :func:`decide_dpi`: the MediaBox value rounded when it is within 2 % of 300 or 600, else the
JFIF one when present and plausible, else ``None`` (the caller uses its argument or 300). Disagreements > 2 %
between the two sources are a warning, never a refusal (the piece-scale check of :mod:`src.ingest` is the real
test).

Pure helpers (:func:`parse_pdf`, :func:`pdf_page_images`, :func:`mediabox_dpi`, :func:`decide_dpi`) are separate
from the file I/O of :func:`expand_sources`.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

__all__ = ["Sheet", "IMAGE_EXT", "PDF_EXT", "STD_DPI", "DPI_SNAP_FRAC", "DPI_AXES_FRAC", "parse_pdf", "pdf_pages",
		   "pdf_page_images", "mediabox_dpi", "jfif_dpi", "decide_dpi", "expand_sources", "safe_stem"]

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
PDF_EXT = (".pdf",)
STD_DPI = (300.0, 600.0)
DPI_SNAP_FRAC = 0.02       # MediaBox dpi within 2 % of 300 / 600 -> that value
DPI_AXES_FRAC = 0.01       # x and y MediaBox dpi must agree within 1 %
DPI_DISAGREE_FRAC = 0.02   # MediaBox vs JFIF: warning above 2 %
JFIF_PLAUSIBLE = (100.0, 1200.0)


@dataclass
class Sheet:
	"""One sheet to ingest. ``origem``: the given file; ``pagina``: 1-based PDF page (None for an image);
	``caminho``: the image file to segment (the file itself, or the JPEG extracted from the page);
	``dpi_fontes``: ``{mediabox, jfif}``; ``dpi``: decided (None = let the caller decide); ``avisos``: warnings;
	``erro``: why the sheet cannot be ingested (None when it can); ``sha256``: hash of the sheet's image bytes."""

	origem: str
	pagina: Optional[int] = None
	caminho: Optional[str] = None
	dpi_fontes: dict = field(default_factory=lambda: {"mediabox": None, "jfif": None})
	dpi: Optional[float] = None
	avisos: list = field(default_factory=list)
	erro: Optional[str] = None
	sha256: Optional[str] = None
	largura: Optional[int] = None
	altura: Optional[int] = None

	def to_dict(self) -> dict:
		return asdict(self)


# ---------------------------------------------------------------- pure: PDF bytes
_OBJ = re.compile(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b")
_REF = re.compile(rb"(\d+)\s+(\d+)\s+R\b")
_NUM = rb"[-+]?(?:\d+\.?\d*|\.\d+)"


def _skip_ws(b: bytes, i: int) -> int:
	while i < len(b) and b[i:i + 1] in b" \t\r\n\x0c\x00":
		i += 1
	return i


def _dict_end(b: bytes, i: int) -> int:
	"""Index just after the ``>>`` closing the dictionary that opens at ``b[i:i+2] == b'<<'`` (strings skipped)."""
	depth, n = 0, len(b)
	while i < n:
		c = b[i:i + 1]
		if b[i:i + 2] == b"<<":
			depth += 1
			i += 2
			continue
		if b[i:i + 2] == b">>":
			depth -= 1
			i += 2
			if depth == 0:
				return i
			continue
		if c == b"(":                              # literal string: balanced parentheses, backslash escapes
			lvl = 0
			while i < n:
				ch = b[i:i + 1]
				if ch == b"\\":
					i += 2
					continue
				if ch == b"(":
					lvl += 1
				elif ch == b")":
					lvl -= 1
					if lvl == 0:
						i += 1
						break
				i += 1
			continue
		i += 1
	return -1


def parse_pdf(data: bytes) -> dict:
	"""``{num: {"dict": bytes | None, "stream": (start, end) | None, "raw": bytes}}`` of every indirect object.

	Sequential scan: after a dictionary followed by ``stream``, the data is skipped with a direct ``/Length``
	(binary image data never gets parsed as objects); with an indirect ``/Length`` the end is the next
	``endstream`` and the stream is re-cut once the length object is known. The last definition of a number wins
	(incremental updates)."""
	objs, pend = {}, []
	pos, n = 0, len(data)
	while True:
		m = _OBJ.search(data, pos)
		if m is None:
			break
		num = int(m.group(1))
		i = _skip_ws(data, m.end())
		d, stream = None, None
		if data[i:i + 2] == b"<<":
			e = _dict_end(data, i)
			if e < 0:
				break
			d = data[i:e]
			j = _skip_ws(data, e)
			if data[j:j + 6] == b"stream":
				k = j + 6
				if data[k:k + 2] == b"\r\n":
					k += 2
				elif data[k:k + 1] in (b"\n", b"\r"):
					k += 1
				lm = re.search(rb"/Length\s+(\d+)(\s+\d+\s+R)?", d)
				if lm and not lm.group(2) and k + int(lm.group(1)) <= n:
					stream = (k, k + int(lm.group(1)))
				else:
					es = data.find(b"endstream", k)
					if es < 0:
						break
					s_end = es
					if data[s_end - 2:s_end] == b"\r\n":
						s_end -= 2
					elif data[s_end - 1:s_end] in (b"\n", b"\r"):
						s_end -= 1
					stream = (k, s_end)
					if lm and lm.group(2):
						pend.append((num, int(_REF.search(lm.group(2)).group(1)), k))
				pos = stream[1]
			else:
				pos = e
		else:
			pos = i
		eo = data.find(b"endobj", pos)
		raw = b"" if stream is not None else (data[i:eo] if eo >= 0 else data[i:i + 64])
		objs[num] = {"dict": d, "stream": stream, "raw": raw}
		pos = eo + 6 if eo >= 0 else pos + 1
	for num, lnum, k in pend:                      # indirect /Length: trust it when the referenced number is sane
		lo = objs.get(lnum)
		if lo is None:
			continue
		mm = re.match(rb"\s*(\d+)", lo["raw"])
		if mm and k + int(mm.group(1)) <= n:
			objs[num]["stream"] = (k, k + int(mm.group(1)))
	return objs


def _resolve(objs: dict, v: bytes) -> bytes:
	"""``N G R`` -> the referenced object's dictionary (or raw value); anything else unchanged."""
	m = re.fullmatch(rb"\s*(\d+)\s+\d+\s+R\s*", v)
	if not m:
		return v
	o = objs.get(int(m.group(1)))
	if o is None:
		return b""
	return o["dict"] if o["dict"] is not None else o["raw"]


def _value(d: bytes, key: bytes) -> Optional[bytes]:
	"""Raw value of ``/key`` in the dictionary bytes ``d`` (a nested dict, an array, a reference or a token)."""
	m = re.search(rb"/" + key + rb"(?![A-Za-z0-9])\s*", d)
	if not m:
		return None
	i = m.end()
	if d[i:i + 2] == b"<<":
		e = _dict_end(d, i)
		return d[i:e] if e > 0 else None
	if d[i:i + 1] == b"[":
		e = d.find(b"]", i)
		return d[i:e + 1] if e > 0 else None
	r = _REF.match(d, i)
	if r:
		return r.group(0)
	t = re.match(rb"/?[^\s/<>\[\]()]+", d[i:])
	return t.group(0) if t else None


def _is_type(d: Optional[bytes], t: bytes) -> bool:
	return d is not None and re.search(rb"/Type\s*/" + t + rb"(?![A-Za-z0-9])", d) is not None


def pdf_pages(objs: dict) -> list:
	"""Page object numbers in document order: the ``/Kids`` of the root ``/Pages`` (recursively), else the
	``/Type /Page`` objects in file order."""
	roots = []
	for num, o in objs.items():
		if _is_type(o["dict"], b"Catalog"):
			v = _value(o["dict"], b"Pages")
			r = _REF.match(v or b"")
			if r:
				roots.append(int(r.group(1)))
	if not roots:
		roots = [num for num, o in objs.items() if _is_type(o["dict"], b"Pages")
				 and _value(o["dict"], b"Parent") is None]
	out, seen = [], set()

	def walk(num, depth=0):
		if num in seen or depth > 32:
			return
		seen.add(num)
		o = objs.get(num)
		if o is None or o["dict"] is None:
			return
		if _is_type(o["dict"], b"Page"):
			out.append(num)
			return
		kids = _resolve(objs, _value(o["dict"], b"Kids") or b"")
		for r in _REF.finditer(kids or b""):
			walk(int(r.group(1)), depth + 1)

	for r in roots:
		walk(r)
	if not out:
		out = [num for num, o in objs.items() if _is_type(o["dict"], b"Page")]   # file order
	return out


def _inherited(objs: dict, num: int, key: bytes) -> Optional[bytes]:
	"""``/key`` of page ``num``, or of the first ``/Parent`` that has it."""
	for _ in range(32):
		o = objs.get(num)
		if o is None or o["dict"] is None:
			return None
		v = _value(o["dict"], key)
		if v is not None:
			return _resolve(objs, v)
		p = _REF.match(_value(o["dict"], b"Parent") or b"")
		if not p:
			return None
		num = int(p.group(1))
	return None


def _filters(d: bytes) -> list:
	v = _value(d, b"Filter")
	return [x.decode("latin-1") for x in re.findall(rb"/(\w+)", v or b"")]


def pdf_page_images(data: bytes, objs: dict, page: int) -> dict:
	"""``{mediabox: [a, b, c, d] | None, rotate, images: [{name, num, width, height, filters, bytes | None}]}`` of
	the page object ``page`` (image XObjects of its resources; ``bytes`` only for a pure ``DCTDecode`` stream)."""
	mb = _inherited(objs, page, b"MediaBox")
	box = None
	if mb:
		nums = [float(x) for x in re.findall(_NUM, mb)]
		box = nums[:4] if len(nums) >= 4 else None
	rot = _inherited(objs, page, b"Rotate")
	try:
		rot = int(float(rot)) if rot else 0
	except ValueError:
		rot = 0
	res = _inherited(objs, page, b"Resources") or b""
	xo = _resolve(objs, _value(res, b"XObject") or b"") or b""
	images = []
	for m in re.finditer(rb"/([^\s/<>\[\]()]+)\s+(\d+)\s+\d+\s+R", xo):
		num = int(m.group(2))
		o = objs.get(num)
		if o is None or o["dict"] is None or not re.search(rb"/Subtype\s*/Image\b", o["dict"]):
			continue
		d = o["dict"]
		w = re.search(rb"/Width\s+(\d+)", d)
		h = re.search(rb"/Height\s+(\d+)", d)
		fl = _filters(d)
		blob = None
		if fl == ["DCTDecode"] and o["stream"] is not None:
			blob = data[o["stream"][0]:o["stream"][1]]
			if not blob.startswith(b"\xff\xd8"):         # wrong cut: look for the SOI / EOI markers inside
				s0 = blob.find(b"\xff\xd8")
				blob = blob[s0:] if s0 >= 0 else None
			if blob is not None:
				eoi = blob.rfind(b"\xff\xd9")
				if eoi >= 0:
					blob = blob[:eoi + 2]
		images.append({"name": m.group(1).decode("latin-1"), "num": num, "width": int(w.group(1)) if w else None,
					   "height": int(h.group(1)) if h else None, "filters": fl, "bytes": blob})
	return {"mediabox": box, "rotate": rot, "images": images}


# ---------------------------------------------------------------- pure: resolution
def mediabox_dpi(box, w_px: int, h_px: int, rotate: int = 0) -> tuple:
	"""``(dpi | None, aviso | None)`` of an image filling the page ``box`` (points). The two axes must agree within
	:data:`DPI_AXES_FRAC` (with ``/Rotate 90/270`` the axes swap); otherwise the x value and a warning."""
	if not box or not w_px or not h_px:
		return None, None
	pw, ph = abs(box[2] - box[0]), abs(box[3] - box[1])
	if pw <= 0 or ph <= 0:
		return None, None
	if rotate % 180 == 90:
		pw, ph = ph, pw
	dx, dy = 72.0 * w_px / pw, 72.0 * h_px / ph
	if abs(dx - dy) <= DPI_AXES_FRAC * max(dx, dy):
		return (dx + dy) / 2.0, None
	return dx, f"dpi: eixos do MediaBox discordam (x {dx:.1f}, y {dy:.1f}); uso o de x"


def jfif_dpi(info: dict) -> Optional[float]:
	"""Density of a PIL ``info`` dict (JFIF in inches, or PNG / TIFF ``dpi``), None when absent or implausible."""
	if info.get("jfif_unit") == 0:                # aspect ratio only, no density
		return None
	v = info.get("dpi")
	if not v:
		return None
	try:
		vals = [float(x) for x in (v if isinstance(v, (tuple, list)) else (v, v))]
	except (TypeError, ValueError):
		return None
	d = sum(vals) / len(vals)
	return d if JFIF_PLAUSIBLE[0] <= d <= JFIF_PLAUSIBLE[1] else None


def decide_dpi(mediabox: Optional[float], jfif: Optional[float]) -> tuple:
	"""``(dpi | None, avisos)``: ``round(mediabox)`` snapped when within :data:`DPI_SNAP_FRAC` of 300 / 600, else
	``jfif`` when present, else None. Warning when both exist and disagree by more than 2 %."""
	avisos = []
	if mediabox and jfif and abs(mediabox - jfif) > DPI_DISAGREE_FRAC * max(mediabox, jfif):
		avisos.append(f"dpi: MediaBox {mediabox:.1f} ≠ JFIF {jfif:.0f}".replace(".", ","))
	if mediabox:
		for s in STD_DPI:
			if abs(mediabox - s) <= DPI_SNAP_FRAC * s:
				return float(s), avisos
	if jfif:
		return float(round(jfif)), avisos
	if mediabox:
		avisos.append(f"dpi: MediaBox {mediabox:.1f} longe de 300/600 e sem JFIF; decide o chamador".replace(".", ","))
	return None, avisos


def safe_stem(path: str) -> str:
	"""File stem with anything outside ``[A-Za-z0-9._-]`` replaced by ``_`` (the server's upload names)."""
	return re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.splitext(os.path.basename(path))[0]) or "folha"


# ---------------------------------------------------------------- I/O
def _sha(b: bytes) -> str:
	return hashlib.sha256(b).hexdigest()


def _file_sha(path: str) -> str:
	h = hashlib.sha256()
	with open(path, "rb") as f:
		for chunk in iter(lambda: f.read(1 << 20), b""):
			h.update(chunk)
	return h.hexdigest()


def _image_sheet(path: str) -> Sheet:
	from PIL import Image
	sh = Sheet(origem=path, caminho=path)
	try:
		with Image.open(path) as im:
			im.verify()
		with Image.open(path) as im:
			sh.largura, sh.altura = im.size
			sh.dpi_fontes["jfif"] = jfif_dpi(im.info)
			if getattr(im, "n_frames", 1) > 1:
				sh.avisos.append(f"imagem com {im.n_frames} páginas: só a primeira é lida")
	except Exception as e:  # noqa: BLE001 - any decoder failure: not an image we can read
		sh.erro = f"{os.path.basename(path)}: não é uma imagem legível ({type(e).__name__}: {e})"
		return sh
	sh.dpi, av = decide_dpi(None, sh.dpi_fontes["jfif"])
	sh.avisos += av
	sh.sha256 = _file_sha(path)
	return sh


def _unique_out(out_dir: str, name: str, blob: bytes) -> str:
	"""``out_dir/name``; when a file with other bytes is already there, ``stem_2.jpg``, ``stem_3.jpg``… (a registered
	scan's file is never overwritten)."""
	stem, ext = os.path.splitext(name)
	k = 1
	while True:
		fp = os.path.join(out_dir, name if k == 1 else f"{stem}_{k}{ext}")
		if not os.path.exists(fp):
			return fp
		with open(fp, "rb") as f:
			if f.read() == blob:
				return fp
		k += 1


def _rasterise(path: str, k: int, out_dir: str, stem: str) -> Optional[str]:
	"""Page ``k`` rendered at 300 dpi with PyMuPDF when it is installed (it is not: [NT]); None otherwise."""
	try:
		import fitz  # noqa: F401
	except ImportError:
		return None
	doc = fitz.open(path)                         # pragma: no cover - PyMuPDF not installed here
	try:
		pix = doc[k - 1].get_pixmap(dpi=300)
		fp = os.path.join(out_dir, f"{stem}_p{k}.png")
		pix.save(fp)
		return fp
	finally:
		doc.close()


def _pdf_sheets(path: str, out_dir: str, stem: str) -> list:
	from PIL import Image
	with open(path, "rb") as f:
		data = f.read()
	if not data.startswith(b"%PDF"):
		return [Sheet(origem=path, erro=f"{os.path.basename(path)}: não começa por %PDF")]
	objs = parse_pdf(data)
	pages = pdf_pages(objs)
	if not pages:
		return [Sheet(origem=path, erro=f"{os.path.basename(path)}: nenhuma página encontrada")]
	out = []
	for k, num in enumerate(pages, 1):
		sh = Sheet(origem=path, pagina=k)
		info = pdf_page_images(data, objs, num)
		imgs = info["images"]
		dct = [im for im in imgs if im["filters"] == ["DCTDecode"] and im["bytes"]]
		if len(imgs) != 1 or len(dct) != 1:
			fl = ", ".join(sorted({"/".join(im["filters"]) or "sem filtro" for im in imgs})) or "nenhuma imagem"
			fp = _rasterise(path, k, out_dir, stem)
			if fp is None:
				sh.erro = (f"página {k}: sem JPEG incorporado único ({len(imgs)} imagens; filtro {fl}); "
						   "rasterizar exige PyMuPDF, que não está instalado")
				out.append(sh)
				continue
			sh.caminho, sh.dpi, sh.sha256 = fp, 300.0, _file_sha(fp)          # pragma: no cover
			sh.avisos.append(f"página {k}: rasterizada a 300 dpi (PyMuPDF)")  # pragma: no cover
			out.append(sh)                                                    # pragma: no cover
			continue                                                          # pragma: no cover
		im = dct[0]
		blob = im["bytes"]
		try:
			with Image.open(io.BytesIO(blob)) as pil:
				pil.load()
				size, pinfo = pil.size, dict(pil.info)
		except Exception as e:  # noqa: BLE001
			sh.erro = f"página {k}: o JPEG incorporado não abre ({type(e).__name__}: {e})"
			out.append(sh)
			continue
		if im["width"] and im["height"] and size != (im["width"], im["height"]):
			sh.avisos.append(f"página {k}: JPEG {size[0]}×{size[1]} ≠ declarado {im['width']}×{im['height']}")
		sh.largura, sh.altura = size
		mdpi, av = mediabox_dpi(info["mediabox"], size[0], size[1], info["rotate"])
		if av:
			sh.avisos.append(av)
		if info["rotate"]:
			sh.avisos.append(f"página {k}: /Rotate {info['rotate']} ignorado (a orientação das peças não importa)")
		sh.dpi_fontes = {"mediabox": None if mdpi is None else round(mdpi, 2), "jfif": jfif_dpi(pinfo)}
		sh.dpi, av = decide_dpi(mdpi, sh.dpi_fontes["jfif"])
		sh.avisos += av
		os.makedirs(out_dir, exist_ok=True)
		fp = _unique_out(out_dir, f"{stem}_p{k}.jpg", blob)
		if not os.path.exists(fp):
			with open(fp, "wb") as f:
				f.write(blob)
		sh.caminho, sh.sha256 = fp, _sha(blob)
		out.append(sh)
	return out


def expand_sources(paths, *, out_dir: Optional[str] = None, prefix: Optional[str] = None) -> list:
	"""Sheets (:class:`Sheet`) of the given files, in order: an image is one sheet (the file itself), a PDF one
	sheet per page with its JPEG extracted to ``out_dir/<prefix>_p<k>.jpg`` (``out_dir`` default: the PDF's
	folder; ``prefix`` default: the PDF's stem, sanitised, numbered when several PDFs would clash). A missing or
	unreadable file is a sheet with ``erro`` (never an exception)."""
	out, used = [], set()
	for path in paths:
		path = os.fspath(path)
		ext = os.path.splitext(path)[1].lower()
		if not os.path.exists(path):
			out.append(Sheet(origem=path, erro=f"ficheiro não encontrado: {path}"))
			continue
		is_pdf = ext in PDF_EXT
		if not is_pdf and ext not in IMAGE_EXT:
			with open(path, "rb") as f:
				is_pdf = f.read(5) == b"%PDF-"
		if is_pdf:
			stem = prefix or safe_stem(path)
			base, j = stem, 2
			while stem in used:
				stem, j = f"{base}_{j}", j + 1
			used.add(stem)
			try:
				out += _pdf_sheets(path, out_dir or os.path.dirname(os.path.abspath(path)), stem)
			except Exception as e:  # noqa: BLE001 - a broken PDF is a sheet error, not a crash
				out.append(Sheet(origem=path, erro=f"{os.path.basename(path)}: PDF ilegível ({type(e).__name__}: {e})"))
		else:
			out.append(_image_sheet(path))
	return out
