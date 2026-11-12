"""Tests of :mod:`src.sheets` (sheets from files: images, PDF pages with an embedded JPEG; no PDF dependency)."""

import hashlib
import io
import os
import sys
import types

import numpy as np
import pytest
from PIL import Image

from src import sheets as SH

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOTE9 = os.path.join(REPO, "images", "pieces", "lote 9.pdf")


def _jpeg(w=120, h=80, dpi=(300, 300), seed=0) -> bytes:
	rng = np.random.default_rng(seed)
	img = Image.fromarray(rng.integers(0, 255, (h, w, 3), dtype=np.uint8))
	buf = io.BytesIO()
	img.save(buf, "JPEG", quality=85, dpi=dpi)
	return buf.getvalue()


def _pdf(pages, eol=b"\n") -> bytes:
	"""Minimal PDF: ``pages`` = [(mediabox (w, h) points, [image dicts {bytes, w, h, filter}] )]."""
	objs = []

	def add(body: bytes) -> int:
		objs.append(body)
		return len(objs)

	page_ids = []
	for (mw, mh), imgs in pages:
		names = []
		for k, im in enumerate(imgs):
			flt = im.get("filter", b"/DCTDecode")
			num = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 "
					  b"/Filter [ %s ] /Length %d >>" % (im["w"], im["h"], flt, len(im["bytes"]))
					  + b"\nstream" + eol + im["bytes"] + eol + b"endstream")
			names.append(b"/Im%d %d 0 R" % (k + 1, num))
		page_ids.append(add(b"<< /Type /Page /MediaBox [0 0 %d %d] /Parent PARENT 0 R /Resources << /XObject << %s >> >> >>"
							% (mw, mh, b" ".join(names))))
	pages_id = add(b"<< /Type /Pages /Kids [ " + b" ".join(b"%d 0 R" % i for i in page_ids) + b" ] /Count %d >>" % len(page_ids))
	cat = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
	out = b"%PDF-1.7" + eol
	for i, body in enumerate(objs, 1):
		body = body.replace(b"PARENT", str(pages_id).encode())
		out += b"%d 0 obj" % i + eol + body + eol + b"endobj" + eol
	out += b"trailer << /Root %d 0 R >>" % cat + eol + b"%%EOF" + eol
	return out


@pytest.mark.parametrize("eol", [b"\n", b"\r\n", b"\r"])
def test_pdf_one_page_one_jpeg_bytes_and_mediabox_dpi(tmp_path, eol):
	jp = _jpeg(1275, 1650, dpi=(300, 300))            # 8.5 x 11 in at 150 dpi of the page -> MediaBox 612 x 792 at 150 dpi
	pdf = tmp_path / "saco.pdf"
	pdf.write_bytes(_pdf([((612, 792), [{"bytes": jp, "w": 1275, "h": 1650}])], eol=eol))
	out = SH.expand_sources([str(pdf)], out_dir=str(tmp_path / "o"))
	assert len(out) == 1
	sh = out[0]
	assert sh.erro is None and sh.pagina == 1 and os.path.basename(sh.caminho) == "saco_p1.jpg"
	with open(sh.caminho, "rb") as f:
		assert f.read() == jp                          # the embedded JPEG as is
	assert sh.dpi_fontes["mediabox"] == pytest.approx(150.0, abs=0.01) and sh.dpi_fontes["jfif"] == 300
	# MediaBox 150 is not near 300/600 -> JFIF decides; the two disagree -> warning
	assert sh.dpi == 300 and any("MediaBox" in a and "JFIF" in a for a in sh.avisos)
	assert sh.sha256 == __import__("hashlib").sha256(jp).hexdigest()
	assert (sh.largura, sh.altura) == (1275, 1650)


def test_pdf_mediabox_at_300_wins_and_agreeing_sources_no_warning(tmp_path):
	jp = _jpeg(600, 300, dpi=(300, 300))
	pdf = tmp_path / "a.pdf"
	pdf.write_bytes(_pdf([((144, 72), [{"bytes": jp, "w": 600, "h": 300}]),
						  ((144, 72), [{"bytes": _jpeg(600, 300, seed=1), "w": 600, "h": 300}])]))
	out = SH.expand_sources([str(pdf)], out_dir=str(tmp_path))
	assert [s.pagina for s in out] == [1, 2] and all(s.erro is None for s in out)
	assert all(s.dpi == 300 and s.avisos == [] for s in out)
	assert out[0].sha256 != out[1].sha256
	# again: same files, not duplicated
	again = SH.expand_sources([str(pdf)], out_dir=str(tmp_path))
	assert [s.caminho for s in again] == [s.caminho for s in out]


def _pdf_without_single_jpeg() -> bytes:
	"""3 pages none of which has a single embedded JPEG: no image, a FlateDecode image, two JPEGs."""
	return _pdf([((612, 792), []),
				 ((612, 792), [{"bytes": b"x" * 50, "w": 10, "h": 5, "filter": b"/FlateDecode"}]),
				 ((612, 792), [{"bytes": _jpeg(), "w": 120, "h": 80}, {"bytes": _jpeg(seed=2), "w": 120, "h": 80}])])


class _FakeFitz(types.ModuleType):
	"""Stand-in for PyMuPDF (``fitz``) with the 3 calls ``sheets._rasterise`` makes:
	``fitz.open(path)`` -> doc, ``doc[i].get_pixmap(dpi=)`` -> pixmap, ``pix.save(fp)``, ``doc.close()``.
	The pixmap is a real PNG (A4 at the requested dpi, scaled 1/10 to keep it small) so the sha256 is real."""

	def __init__(self):
		super().__init__("fitz")
		self.calls = []

	def open(self, path):
		fake = self

		class _Pix:
			def __init__(self, i, dpi):
				self.i, self.dpi = i, dpi

			def save(self, fp):
				fake.calls.append(("save", self.i, os.path.basename(fp)))
				Image.fromarray(np.full((self.dpi * 11 // 10, self.dpi * 85 // 100, 3), 40 * self.i, np.uint8)).save(fp)

		class _Page:
			def __init__(self, i):
				self.i = i

			def get_pixmap(self, dpi):
				fake.calls.append(("pixmap", self.i, dpi))
				return _Pix(self.i, dpi)

		class _Doc:
			def __getitem__(self, i):
				return _Page(i)

			def close(self):
				fake.calls.append(("close",))

		fake.calls.append(("open", os.path.basename(path)))
		return _Doc()


def test_pdf_page_without_image_or_with_flate_is_an_error(tmp_path, monkeypatch):
	"""PyMuPDF ABSENT (forced): ``sys.modules['fitz'] = None`` makes ``import fitz`` raise ImportError,
	whatever is installed in the Python running the suite (the system Python has PyMuPDF 1.28)."""
	monkeypatch.setitem(sys.modules, "fitz", None)
	pdf = tmp_path / "b.pdf"
	pdf.write_bytes(_pdf_without_single_jpeg())
	out = SH.expand_sources([str(pdf)], out_dir=str(tmp_path))
	assert len(out) == 3 and all(s.caminho is None for s in out)
	assert "página 1" in out[0].erro and "PyMuPDF" in out[0].erro
	assert "FlateDecode" in out[1].erro
	assert "2 imagens" in out[2].erro


def test_pdf_page_without_single_jpeg_is_rasterised_when_pymupdf_present(tmp_path, monkeypatch):
	"""PyMuPDF PRESENT (forced with a stand-in, see :class:`_FakeFitz`): every page without a single
	embedded JPEG is rendered at 300 dpi to ``<stem>_p<k>.png`` instead of being an error."""
	fake = _FakeFitz()
	monkeypatch.setitem(sys.modules, "fitz", fake)
	pdf = tmp_path / "b.pdf"
	pdf.write_bytes(_pdf_without_single_jpeg())
	out = SH.expand_sources([str(pdf)], out_dir=str(tmp_path))
	assert len(out) == 3 and all(s.erro is None for s in out)
	assert [s.pagina for s in out] == [1, 2, 3]
	assert [os.path.basename(s.caminho) for s in out] == ["b_p1.png", "b_p2.png", "b_p3.png"]
	assert all(s.dpi == 300.0 for s in out)
	assert all(s.avisos == [f"página {s.pagina}: rasterizada a 300 dpi (PyMuPDF)"] for s in out)
	for s in out:
		with open(s.caminho, "rb") as f:
			assert s.sha256 == hashlib.sha256(f.read()).hexdigest()
	# page k is page k - 1 of the document, rendered at 300 dpi, and every document is closed
	assert [c for c in fake.calls if c[0] == "pixmap"] == [("pixmap", 0, 300), ("pixmap", 1, 300), ("pixmap", 2, 300)]
	assert sum(c[0] == "open" for c in fake.calls) == sum(c[0] == "close" for c in fake.calls) == 3


def test_pdf_rasterised_with_real_pymupdf(tmp_path):
	"""The same page with the real PyMuPDF, only where it is installed (the system Python; not the ``.venv``)."""
	fitz = pytest.importorskip("fitz", reason="PyMuPDF não está instalado neste Python (o .venv não o tem)")
	pdf = tmp_path / "b.pdf"
	pdf.write_bytes(_pdf([((612, 792), [])]))       # an empty page renders on any PyMuPDF
	out = SH.expand_sources([str(pdf)], out_dir=str(tmp_path))
	assert len(out) == 1 and out[0].erro is None and out[0].dpi == 300.0
	with Image.open(out[0].caminho) as im:
		assert im.size == (2550, 3300)              # 8.5 x 11 in at 300 dpi
	assert fitz is not None


def test_images_and_errors(tmp_path):
	png = tmp_path / "f.png"
	Image.fromarray(np.zeros((40, 60, 3), np.uint8)).save(png)
	jpg = tmp_path / "g.jpg"
	jpg.write_bytes(_jpeg(dpi=(600, 600)))
	bad = tmp_path / "bad.png"
	bad.write_bytes(b"not a png at all")
	out = SH.expand_sources([str(png), str(jpg), str(bad), str(tmp_path / "missing.jpg")])
	assert [s.erro is None for s in out] == [True, True, False, False]
	assert out[0].caminho == str(png) and out[0].dpi is None and out[0].pagina is None       # no density: the caller decides
	assert out[1].dpi == 600 and out[1].dpi_fontes == {"mediabox": None, "jfif": 600.0}
	assert "não é uma imagem legível" in out[2].erro and "não encontrado" in out[3].erro


def test_decide_dpi_rules():
	assert SH.decide_dpi(299.88, 300.0) == (300.0, [])
	assert SH.decide_dpi(605.0, None) == (600.0, [])
	d, av = SH.decide_dpi(282.0, 300.0)
	assert d == 300.0 and av and "MediaBox 282,0" in av[0]
	assert SH.decide_dpi(None, None) == (None, [])
	assert SH.jfif_dpi({"dpi": (72, 72), "jfif_unit": 0}) is None
	assert SH.jfif_dpi({"dpi": (50, 50)}) is None
	assert SH.mediabox_dpi([0, 0, 611, 841], 2544, 3504)[0] == pytest.approx(299.88, abs=0.02)
	d, av = SH.mediabox_dpi([0, 0, 600, 600], 2500, 3000)
	assert d == pytest.approx(300.0) and "discordam" in av


def test_real_lote9_pdf(tmp_path):
	if not os.path.exists(LOTE9):
		pytest.skip("images/pieces/lote 9.pdf não está nesta cópia")
	out = SH.expand_sources([LOTE9], out_dir=str(tmp_path))
	assert len(out) == 2 and all(s.erro is None for s in out)
	for s in out:
		assert (s.largura, s.altura) == (2544, 3504) and s.dpi == 300 and s.avisos == []
		with Image.open(s.caminho) as im:
			assert im.size == (2544, 3504)
		with open(s.caminho, "rb") as f:
			b = f.read()
		assert b[:2] == b"\xff\xd8" and b[-2:] == b"\xff\xd9"
	assert [os.path.getsize(s.caminho) for s in out] == [1967544, 1494788]     # the /Length of Im1 / Im2
