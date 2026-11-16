/* Utilitários comuns às interfaces web (sem regras do puzzle nem estado): seletores, localStorage tolerante,
 * construtores de elementos HTML/SVG, formatação de números, pedidos à API, avisos (toast) e lightbox.
 * Carregado antes de board.js e da casca (app.js); scripts clássicos, por isso as declarações são globais.
 */
"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* the page works without storage */ } }

// ------------------------------------------------------------ utilities
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined) continue;
    el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid) el.append(kid);
  return el;
}
const fmt = (v, nd = 1) => (v === null || v === undefined) ? "—" : Number(v).toFixed(nd).replace(".", ",");
/** Faixa «Ligação perdida, a tentar religar…» (F2b): o EventSource religa-se sozinho (``retry: 2000`` do servidor);
 * enquanto a ligação está em baixo a faixa fica visível e, quando volta, chama ``onBack`` (recarregar o estado, que
 * pode ter mudado ou o servidor ter reiniciado). Não depende de CSS da página. */
function watchConnection(es, onBack) {
  let lost = false, el = null;
  const show = (on) => {
    if (!el) {
      el = h("div", { id: "ligacao", role: "status", "aria-live": "polite" }, "Ligação perdida, a tentar religar…");
      el.style.cssText = "position:fixed;top:0;left:0;right:0;margin:0 auto;width:fit-content;text-align:center;z-index:200;background:#8a2f27;color:#fff;"
        + "padding:8px 18px;border-radius:0 0 10px 10px;font:600 14px system-ui,sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.45);max-width:96vw";
      document.body.append(el);
    }
    el.style.display = on ? "block" : "none";
  };
  es.addEventListener("error", () => { lost = true; show(true); });
  es.addEventListener("open", () => {
    show(false);
    if (lost) { lost = false; if (onBack) onBack(); }
  });
}
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  if (!r.ok) {
    const d = body && (body.detail || body.error);
    const msg = typeof d === "string" ? d : (d && d.a_preparar ? "a preparar o projeto…" : `erro ${r.status}`);
    const err = new Error(msg); err.status = r.status; err.body = body; throw err;
  }
  return body;
}

function toast(msg, err = false) {
  const el = h("div", { class: err ? "err" : "" }, msg);
  $("#toast").append(el);
  setTimeout(() => el.remove(), err ? 7000 : 4500);
}

function lightbox(src, cap) {
  $("#lb-img").src = src;
  $("#lb-cap").textContent = cap || "";
  $("#lightbox").hidden = false;
}

// ------------------------------------------------------------ registo de erros do browser (F2c)
/** Os erros da página (``error``, ``unhandledrejection``, ``console.error``) vão para o registo de atividade do servidor
 * (``POST /api/cliente/erro`` → linha ``erro_cliente``, nível aviso), nas duas GUIs. Um JSON curto (tipo, mensagem,
 * fonte:linha:coluna, stack cortada, página, user agent) de ≤ 4 KB por ``navigator.sendBeacon`` (``fetch`` com
 * ``keepalive`` como alternativa). Limites aqui: 1 erro igual (mesma mensagem e fonte) por minuto e 20 por página; no
 * servidor há outro por cliente. Nunca bloqueia nem rebenta a página: tudo em ``try``, o envio não é esperado, o erro de um
 * envio não se volta a enviar (``cliErr.busy``) e o ``console.error`` original continua a ser chamado. */
const cliErr = { max: 4096, repete: 60000, sessao: 20, n: 0, vistos: new Map(), busy: false };
function cliErrSend(tipo, mensagem, fonte, stack) {
  if (cliErr.busy) return;
  cliErr.busy = true;
  try {
    mensagem = String(mensagem == null ? "" : mensagem);
    fonte = String(fonte || "");
    const key = mensagem + "|" + fonte, agora = Date.now(), ant = cliErr.vistos.get(key);
    if ((ant !== undefined && agora - ant < cliErr.repete) || cliErr.n >= cliErr.sessao) return;
    cliErr.vistos.set(key, agora); cliErr.n += 1;
    const o = { tipo, mensagem: mensagem.slice(0, 400), fonte: fonte.slice(0, 300), stack: String(stack || "").slice(0, 1500),
      pagina: location.pathname, ua: (navigator.userAgent || "").slice(0, 200) };
    const bytes = (t) => new TextEncoder().encode(t).length;
    let corpo = JSON.stringify(o);
    while (bytes(corpo) > cliErr.max && o.stack.length > 0) { o.stack = o.stack.slice(0, Math.max(0, o.stack.length - 300)); corpo = JSON.stringify(o); }
    if (bytes(corpo) > cliErr.max) { o.mensagem = o.mensagem.slice(0, 100); o.ua = ""; corpo = JSON.stringify(o); }
    let ok = false;
    try { ok = !!(navigator.sendBeacon && navigator.sendBeacon("/api/cliente/erro", new Blob([corpo], { type: "text/plain;charset=UTF-8" }))); } catch (e) { ok = false; }
    if (!ok) {
      try { fetch("/api/cliente/erro", { method: "POST", body: corpo, keepalive: true, headers: { "Content-Type": "text/plain;charset=UTF-8" } }).catch(() => {}); } catch (e) { /* sem registo */ }
    }
  } catch (e) { /* o registo nunca rebenta a página */ } finally { cliErr.busy = false; }
}
(function cliErrHooks() {
  if (window.__cliErrHooks) return;
  window.__cliErrHooks = true;
  window.addEventListener("error", (ev) => {
    if (!ev || (ev.target && ev.target !== window)) return;                  // recursos que não carregam não são erros de código
    cliErrSend("error", ev.message || (ev.error && ev.error.message), `${ev.filename || ""}:${ev.lineno || 0}:${ev.colno || 0}`, ev.error && ev.error.stack);
  });
  window.addEventListener("unhandledrejection", (ev) => {
    const r = ev && ev.reason, st = r && r.stack ? String(r.stack) : "";
    const m = st.match(/(?:\(|at |@)(\S+?:\d+:\d+)\)?\s*$/m);
    cliErrSend("unhandledrejection", r && r.message ? r.message : String(r), m ? m[1] : "", st);
  });
  const orig = console.error;
  console.error = function (...args) {
    try {
      const txt = args.map((a) => (a instanceof Error ? (a.stack || a.message) : (typeof a === "object" && a ? (() => { try { return JSON.stringify(a); } catch (e) { return String(a); } })() : String(a)))).join(" ");
      cliErrSend("console.error", txt, "", "");
    } catch (e) { /* ignora */ }
    return orig.apply(this, args);
  };
})();
