/* Maquete da GUI: toggles, zoom/pan, painel da célula, páginas. Sem regras do puzzle:
   a célula gémea, o fantasma e as listas vêm calculados em mock_data (embutido em cada página). */
(function () {
	"use strict";
	var el = document.getElementById("mock-data");
	var D = el ? JSON.parse(el.textContent) : {};
	var $ = function (s, r) { return (r || document).querySelector(s); };
	var STATE = { vazia: "vazia", ocupada_legado: "ocupada (legado, sem silhueta)", colocada: "colocada" };

	function store(op, k, v) { try { return op === "get" ? localStorage.getItem("mock.layer." + k) : localStorage.setItem("mock.layer." + k, v); } catch (e) { return null; } }
	function esc(s) { return String(s == null ? "—" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
	function lc(k) { return "(" + k.replace(",", ", ") + ")"; }

	/* ---- barra de navegação ---- */
	function nav() {
		var tabs = [["index.html", "Progresso"], ["fetch.html", "Vai buscar"], ["lotes.html", "Lotes"], ["mesa.html", "Mesa"]];
		var cur = location.pathname.split("/").pop() || "index.html";
		var h = tabs.map(function (t) {
			var badge = t[0] === "fetch.html" && D.fetch ? '<span class="badge tab">' + D.fetch.length + "</span>" : "";
			return '<a href="' + t[0] + '" class="' + (cur === t[0] ? "on" : "") + '">' + t[1] + badge + "</a>";
		}).join("");
		var n = document.querySelector("nav.bar");
		if (n) n.innerHTML = h + '<span class="tag">maquete — botões sem efeito</span>';
	}

	/* ---- painel da célula ---- */
	function pieceImg(pid) { var p = D.pieces && D.pieces[pid]; return p && p.img ? '<img src="' + p.img + '" alt="' + pid + '">' : ""; }

	function cellPanel(key, box) {
		var c = D.cells[key];
		if (!c) { box.innerHTML = '<p class="empty">Célula desconhecida.</p>'; return; }
		var st = c[0], pid = c[1], tw = c[2], twc = tw ? D.cells[tw] : null, g = D.ghosts && D.ghosts[key];
		var rows = '<div class="row"><span>estado</span><span class="state">' + esc(STATE[st] || st) + "</span></div>";
		rows += '<div class="row"><span>peça</span><span>' + (pid ? esc(pid) + (D.pieces[pid] && D.pieces[pid].lote != null ? " · lote " + D.pieces[pid].lote : "") : "—") + "</span></div>";
		rows += '<div class="row"><span>gémea</span><span>' + (tw ? lc(tw) + " " + (twc ? (twc[0] === "colocada" ? "colocada (" + esc(twc[1]) + ")" : twc[0] === "vazia" ? "vazia" : "legado") : "") : "sem gémea") + "</span></div>";
		if (g) rows += '<div class="row"><span>fantasma</span><span>de ' + esc(g.src) + " (" + lc(g.src_cell.join(",")) + ")</span></div>";
		var imgs = "";
		if (pid && pieceImg(pid)) imgs += "<figure>" + pieceImg(pid) + "<figcaption>peça</figcaption></figure>";
		if (twc && twc[1] && pieceImg(twc[1])) imgs += "<figure>" + pieceImg(twc[1]) + "<figcaption>gémea</figcaption></figure>";
		if (g) {
			imgs += '<figure><svg viewBox="-0.9 -0.9 1.8 1.8"><path d="' + g.dl + '" fill="rgba(255,255,255,.05)" stroke="#fff" stroke-opacity=".85" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><figcaption>fantasma</figcaption></figure>';
		}
		var act = st === "vazia" ? '<button class="primary" data-act="place">Coloquei aqui</button>' : "";
		box.innerHTML = '<div class="cellpanel"><div style="display:flex;justify-content:space-between;align-items:center"><h2>Célula ' + lc(key) + '</h2><button class="close" data-act="close" aria-label="Fechar">×</button></div>' +
			rows + (imgs ? '<div class="imgs">' + imgs + "</div>" : "") +
			'<div class="actions">' + act + '<button data-act="close">Fechar</button></div><div class="toast"></div></div>';
		box.onclick = function (e) {
			var a = e.target.getAttribute && e.target.getAttribute("data-act");
			if (a === "place") box.querySelector(".toast").textContent = "Maquete: nada foi gravado.";
			if (a === "close") { box.innerHTML = '<p class="empty">Clica numa célula do tabuleiro.</p>'; var s = document.querySelector("svg .cell.sel"); if (s) s.classList.remove("sel"); }
		};
	}

	/* ---- tabuleiro (index.html) ---- */
	function board() {
		var svg = $("#board"), view = $("#view");
		if (!svg) return;
		var W = D.board.w, H = D.board.h, vb = [0, 0, W, H];
		function A() { return (view.clientHeight || 1) / (view.clientWidth || 1); }
		function fit() { var w = Math.max(W, H / A()); vb = [(W - w) / 2, (H - w * A()) / 2, w, w * A()]; }
		function apply() {
			svg.setAttribute("viewBox", vb.map(function (v) { return v.toFixed(3); }).join(" "));
			svg.classList.toggle("zoomed", vb[2] < W / 2.6);
		}
		function clamp() {
			var wmax = Math.max(W, H / A()) * 1.05;
			vb[2] = Math.min(Math.max(vb[2], 3), wmax); vb[3] = vb[2] * A();
			vb[0] = Math.min(Math.max(vb[0], Math.min(0, W - vb[2])), Math.max(0, W - vb[2]));
			vb[1] = Math.min(Math.max(vb[1], Math.min(0, H - vb[3])), Math.max(0, H - vb[3]));
		}
		function zoomAt(fx, fy, k) {
			var px = vb[0] + fx * vb[2], py = vb[1] + fy * vb[3];
			vb[2] *= k; clamp();
			vb[0] = px - fx * vb[2]; vb[1] = py - fy * vb[3]; clamp(); apply();
		}
		function frac(e) { var r = svg.getBoundingClientRect(); return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; }
		/* preserveAspectRatio meet: o viewBox ocupa o rect inteiro só se as proporções coincidirem; usamos o rect como aproximação */
		view.addEventListener("wheel", function (e) { e.preventDefault(); var f = frac(e); zoomAt(f[0], f[1], e.deltaY > 0 ? 1.2 : 1 / 1.2); }, { passive: false });
		var ptrs = {}, last = null, moved = 0, pinch = 0;
		view.addEventListener("pointerdown", function (e) { ptrs[e.pointerId] = e; last = [e.clientX, e.clientY]; moved = 0; view.setPointerCapture(e.pointerId); });
		view.addEventListener("pointermove", function (e) {
			if (!ptrs[e.pointerId]) return;
			ptrs[e.pointerId] = e;
			var ids = Object.keys(ptrs);
			if (ids.length === 2) {
				var a = ptrs[ids[0]], b = ptrs[ids[1]], d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
				if (pinch) { var f = frac({ clientX: (a.clientX + b.clientX) / 2, clientY: (a.clientY + b.clientY) / 2 }); zoomAt(f[0], f[1], pinch / d); }
				pinch = d; moved = 99; return;
			}
			var r = svg.getBoundingClientRect(), dx = e.clientX - last[0], dy = e.clientY - last[1];
			moved += Math.abs(dx) + Math.abs(dy); last = [e.clientX, e.clientY];
			if (moved > 4) { vb[0] -= dx * vb[2] / r.width; vb[1] -= dy * vb[3] / r.height; clamp(); apply(); }
		});
		function up(e) {
			delete ptrs[e.pointerId]; pinch = 0;
			if (moved <= 4 && Object.keys(ptrs).length === 0) {
				var t = document.elementFromPoint(e.clientX, e.clientY);
				if (t && t.getAttribute && t.getAttribute("data-cell") && t.classList.contains("cell")) select(t);
			}
		}
		view.addEventListener("pointerup", up); view.addEventListener("pointercancel", function (e) { delete ptrs[e.pointerId]; pinch = 0; });
		view.addEventListener("dblclick", function () { fit(); apply(); });
		window.addEventListener("resize", function () { fit(); apply(); });
		function select(t) {
			var o = document.querySelector("svg .cell.sel"); if (o) o.classList.remove("sel");
			t.classList.add("sel"); cellPanel(t.getAttribute("data-cell"), $("#panel"));
		}
		/* toggles */
		var map = { ghosts: "layer-ghosts", legacy: "layer-legacy", fetch: "layer-fetch", art: "layer-art" };
		document.querySelectorAll(".toggles input").forEach(function (cb) {
			var k = cb.getAttribute("data-layer"), saved = store("get", k);
			if (saved !== null) cb.checked = saved === "1";
			function sync() { var n = document.getElementById(map[k]); if (n) n.classList.toggle("hidden", !cb.checked); store("set", k, cb.checked ? "1" : "0"); }
			cb.addEventListener("change", sync); sync();
		});
		fit(); apply();
		/* progresso */
		var P = D.progress, pc = $("#prog"), lg = $("#legend");
		if (pc) {
			var seg = function (cls, n) { return '<div class="bar-seg ' + cls + '" style="width:' + (100 * n / P.total).toFixed(2) + '%"></div>'; };
			pc.innerHTML = '<strong class="tab">' + P.ocupadas + "/" + P.total + '</strong> <span class="dim">células ocupadas</span><div class="bar-track">' + seg("col", P.colocadas) + seg("leg", P.legado) + "</div>";
			var src = Object.keys(P.por_fonte).map(function (k) { return k + " " + P.por_fonte[k]; }).join(" · ");
			lg.innerHTML = '<i style="background:#5b9bd5"></i>colocadas ' + P.colocadas + (src ? " (" + esc(src) + ")" : "") + '<i style="background:#7d8fa6"></i>legado (foto) ' + P.legado + "<br>soltas " + P.soltas + " · gémeas pendentes " + P.gemeas_pendentes + " · buracos " + P.buracos;
		}
	}

	/* ---- vai buscar ---- */
	function fetchPage() {
		var list = $("#cards"); if (!list) return;
		var mm = $("#minimap .frame"), hl = $("#minimap .hl");
		var rows = D.grid.rows, cols = D.grid.cols;
		function show(e) {
			if (!e.cell) { hl.style.display = "none"; return; }
			hl.style.display = "block";
			hl.style.left = ((e.cell[1] - 1) / cols * 100) + "%"; hl.style.top = ((e.cell[0] - 1) / rows * 100) + "%";
			hl.style.width = (100 / cols) + "%"; hl.style.height = (100 / rows) + "%";
			$("#minicap").textContent = "Célula " + lc(e.cell.join(","));
		}
		if (!D.fetch.length) { list.innerHTML = '<div class="placeholder">Nada a ir buscar. Importa um scan para começar.</div>'; return; }
		list.innerHTML = D.fetch.map(function (e, i) {
			var title = e.piece ? "Lote " + esc(e.lote) + " · peça " + esc(e.n) : "Peça por encontrar (gémea de " + esc(e.from) + ")";
			var dec = e.decision || "exemplo";
			var why = (e.reasons || []).concat(e.margin != null ? ["margem " + Number(e.margin).toFixed(2)] : [], e.dE != null ? ["imagem ΔE " + Number(e.dE).toFixed(0)] : []);
			var pic = e.img ? '<img src="' + e.img + '" alt="">' : (e.from_img ? '<img src="' + e.from_img + '" alt="" style="opacity:.5">' : "sem imagem");
			return '<div class="card" data-i="' + i + '"><div class="pic">' + pic + "</div><div><h3>" + title + ' → célula ' + (e.cell ? lc(e.cell.join(",")) : "—") + "</h3>" +
				'<div class="meta">origem: ' + esc(e.origin_label) + ' · <span class="conf ' + esc(dec) + '">' + esc(dec) + "</span></div>" +
				'<div class="reasons">' + why.map(esc).join(" · ") + "</div>" +
				'<div class="actions"><button class="primary" data-act="ok">Coloquei</button><button data-act="no">Não encaixa</button><button data-act="keep">Guardar com posição conhecida</button></div><div class="toast"></div></div></div>';
		}).join("");
		list.addEventListener("click", function (ev) {
			var card = ev.target.closest(".card"); if (!card) return;
			document.querySelectorAll(".card.sel").forEach(function (c) { c.classList.remove("sel"); });
			card.classList.add("sel"); show(D.fetch[+card.getAttribute("data-i")]);
			if (ev.target.getAttribute("data-act")) card.querySelector(".toast").textContent = "Maquete: nada foi gravado.";
		});
		show(D.fetch[0]); list.firstChild.classList.add("sel");
	}

	/* ---- lotes ---- */
	function lotes() {
		var t = $("#lotes"); if (!t) return;
		t.innerHTML = "<tr><th>Lote</th><th>Peças</th><th>Colocadas</th><th>Pendentes</th><th>Folha</th></tr>" + D.lotes.map(function (l, i) {
			return "<tr><td>" + (l.lote == null ? "sem lote (legado)" : l.lote) + "</td><td>" + l.n + "</td><td>" + l.colocadas + "</td><td>" + l.pendentes +
				'</td><td><button data-i="' + i + '">ver folha</button></td></tr>';
		}).join("");
		t.addEventListener("click", function (e) {
			var i = e.target.getAttribute("data-i"); if (i == null) return;
			var l = D.lotes[+i], box = $("#sheet");
			box.innerHTML = '<h2>Folha — lote ' + (l.lote == null ? "sem lote" : l.lote) + "</h2>" + (l.overlay ? '<div class="overlay-box"><img src="' + l.overlay + '" alt="folha numerada"></div>' : '<div class="placeholder">Sem folha numerada para este lote (placeholder).</div>');
		});
	}

	/* ---- mesa ---- */
	function mesa() {
		var box = $("#groups"); if (!box) return;
		if (!D.grupos.length) { box.innerHTML = '<div class="placeholder">Sem grupos soltos por ancorar.</div>'; return; }
		box.innerHTML = D.grupos.map(function (g) {
			var cand = g.candidates.map(function (c) { return "<li>cell0 " + lc(c.cell0.join(",")) + " · rot " + c.rot + "°" + (c.mirror ? " · espelho" : "") + " · pontuação " + Number(c.score).toFixed(2) + " · margem " + Number(c.margin).toFixed(2) + "</li>"; }).join("");
			return '<div class="group"><div><img class="gimg" src="' + g.img + '" alt="' + g.id + '"></div><div><h2>Grupo ' + g.id + " (" + g.n + ' peças · ' + esc(g.kind) + ')</h2><div class="dim">top-3 de zona</div><ol>' + (cand || "<li>sem candidatas</li>") + '</ol><button data-act="anchor">Ancorar em (l, c)</button> <button>Ver na caixa</button><div class="toast"></div></div></div>';
		}).join("");
		box.addEventListener("click", function (e) { if (e.target.getAttribute("data-act")) e.target.parentNode.querySelector(".toast").textContent = "Maquete: nada foi gravado."; });
	}

	/* ---- célula standalone ---- */
	function celula() {
		var box = $("#cellbox"); if (!box) return;
		var k = (location.search.match(/c=([0-9]+,[0-9]+)/) || [])[1];
		if (!k) { k = Object.keys(D.ghosts)[0] || "1,1"; }
		cellPanel(k, box);
		$("#cellpick").value = k;
		$("#cellgo").onclick = function () { var v = $("#cellpick").value.replace(/\s/g, ""); if (D.cells[v]) cellPanel(v, box); else box.innerHTML = '<p class="empty">Célula fora da grelha.</p>'; };
	}

	nav(); board(); fetchPage(); lotes(); mesa(); celula();
})();
