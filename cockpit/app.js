// Cockpit des Reel-Kanals – Oberfläche ohne Build-Schritt. Daten kommen von server.py (/api/…), Dateien über /datei/….
// Ansichten (Hash-Router): #/ Übersicht · #/pipeline · #/reel/<id> · #/themen · #/kommentare · #/dm-funnel · #/wissen/<pfad> · #/bibliothek

import { md, esc } from "/md.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const main = $("#inhalt");

const STUFEN = ["skript", "stimme", "storyboard", "assets", "schnitt", "pruefung", "caption", "freigabe", "geplant", "live"];
const SCHRITTE = STUFEN.slice(0, 7);             // was die Agenten bis zur Freigabe erledigen
const STUFE_NAME = { skript: "Skript", stimme: "Stimme", storyboard: "Storyboard", assets: "Assets", schnitt: "Schnitt",
  pruefung: "Prüfung", caption: "Caption", freigabe: "Freigabe", geplant: "Geplant", live: "Live", verworfen: "Verworfen" };
const SPALTEN = [["idee", "Idee"], ["arbeit", "In Arbeit"], ["pruefung", "Prüfung"], ["freigabe", "Freigabe"],
  ["geplant", "Geplant"], ["live", "Live"], ["verworfen", "Verworfen"]];
const SAEULE_FARBE = { phone: "#2f5bd3", money: "#1d8a59", mind: "#8a4fd3", habits: "#b26f12", people: "#c1352e", self: "#0f8a96" };
const PLATTFORM_NAME = { instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok", youtube: "YouTube" };
// Profil-Adresse je Plattform aus dem Kanal-Handle (kanal.json); Facebook ohne Link (nicht im Einsatz)
const PLATTFORM_URL = { instagram: h => `https://www.instagram.com/${h}/`,
  tiktok: h => `https://www.tiktok.com/@${h}`, youtube: h => `https://www.youtube.com/@${h}` };
// kleines App-Icon links vom Plattformnamen (Dateien in cockpit/icons/, dekorativ)
const pfIcon = id => PLATTFORM_NAME[id] ? `<img class="pf-icon" src="/icons/${id}.png" alt="" width="20" height="20" loading="lazy">` : "";
const PRIO_NAME = { 1: "Hoch", 2: "Mittel", 3: "Niedrig" };
const ENDE_NAME = { question: "Frage", follow: "Folgen", save: "Speichern", share: "Teilen", none: "ohne" };

const S = {
  kanal: {},
  themen: { q: "", saeule: "", status: "idee", prio: "" },
  bib: { q: "", art: "", quelle: "", saeule: "" },
  kom: { filter: null },
  dm: { filter: null },
  funnelReel: "",
  reiter: "skript",
  version: {},                                   // gewählte Video-Version je Reel
};

// ---------- Helfer ----------
async function api(pfad, body) {
  const r = await fetch(pfad, body === undefined ? {} :
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.ok === false) throw new Error(d.fehler || `HTTP ${r.status}`);
  return d;
}

const datei = p => "/datei/" + String(p).split("/").map(encodeURIComponent).join("/");
const zahl = n => n == null || n === "" ? "–" : Number(n).toLocaleString("de-DE", { maximumFractionDigits: 1 });

function zeit(iso, mitJahr = false) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", ...(mitJahr ? { year: "numeric" } : {}), hour: "2-digit", minute: "2-digit" });
}

function toast(text, fehler = false) {
  $(".toast")?.remove();
  const t = document.createElement("div");
  t.className = "toast" + (fehler ? " fehler" : "");
  t.setAttribute("role", fehler ? "alert" : "status");
  t.textContent = text;
  document.body.append(t);
  setTimeout(() => t.remove(), fehler ? 6000 : 2800);
}

function saeule(x) {
  const s = (S.kanal.saeulen || []).find(s => s.id === x || s.name === x);
  return s ? { id: s.id, name: s.name, farbe: SAEULE_FARBE[s.id] } : { id: x, name: x || "", farbe: null };
}
const saeuleChip = x => {
  if (!x) return "";
  const s = saeule(x);
  return `<span class="saeule"${s.farbe ? ` style="--s:${s.farbe}"` : ""}>${esc(s.name)}</span>`;
};

const leer = (titel, text = "") => `<div class="leer"><strong>${esc(titel)}</strong>${text}</div>`;
const offen = v => !v || String(v).startsWith("OFFEN");

function pfadVerbinden(basis, relativ) {
  const teile = basis ? basis.split("/") : [];
  for (const t of relativ.split("/")) {
    if (t === "..") teile.pop();
    else if (t && t !== ".") teile.push(t);
  }
  return teile.join("/");
}

// ---------- Bausteine ----------
function frame(r) {
  const wort = r.wort || r.titel || "?";
  const cls = wort.length > 13 ? " sehrlang" : wort.length > 8 ? " lang" : "";
  const ecke = r.saeule ? saeule(r.saeule).name : "";
  return `<div class="frame"><span class="ecke">${esc(ecke)}</span><div class="wort${cls}">${esc(wort)}</div>`
    + `<i class="strich"></i><span class="zeichen">${esc(S.kanal.theme?.mark || "◆")}</span></div>`;
}

function schrittZustand(r, s) {
  const z = r.schritte?.[s]?.status;
  if (z) return z;
  const i = STUFEN.indexOf(r.stufe);
  return i > STUFEN.indexOf(s) ? "fertig" : "";
}

const spur = r => `<div class="spur" role="img" aria-label="${SCHRITTE.filter(s => schrittZustand(r, s) === "fertig").length} von ${SCHRITTE.length} Schritten fertig">${SCHRITTE.map(s => {
  const z = schrittZustand(r, s);
  return `<i class="${z}" title="${STUFE_NAME[s]}${z ? ": " + z : ""}"></i>`;
}).join("")}</div>`;

function pruefChip(p) {
  if (!p) return "";
  return p.ergebnis === "FREIGABEREIF"
    ? `<span class="chip ok">Prüfung ✓ R${p.runde}</span>`
    : `<span class="chip warn">Nachbessern R${p.runde} · ${p.blocker} B</span>`;
}

function freigabeChip(f) {
  const s = f?.status;
  if (!s) return "";
  return { freigegeben: `<span class="chip ok">freigegeben</span>`, aendern: `<span class="chip warn">ändern</span>`,
    verworfen: `<span class="chip bad">verworfen</span>` }[s] || "";
}

function karte(r) {
  const post = r.post?.geplant_fuer ? `<span class="chip akzent">${zeit(r.post.geplant_fuer)}</span>` : "";
  return `<a class="karte" href="#/reel/${encodeURIComponent(r.id)}">${frame(r)}<div class="meta">${spur(r)}`
    + `<div class="titel">${esc(r.titel)}</div><div class="zeile"><span class="chip">${STUFE_NAME[r.stufe] || esc(r.stufe)}</span>`
    + `${pruefChip(r.pruefung)}${freigabeChip(r.freigabe)}${post}</div></div></a>`;
}

const mini = r => `<a href="#/reel/${encodeURIComponent(r.id)}"><span class="mini">${frame(r)}</span>`
  + `<span><b>${esc(r.titel)}</b><br><span class="klein muted">${STUFE_NAME[r.stufe] || esc(r.stufe)}`
  + `${r.post?.geplant_fuer ? " · " + zeit(r.post.geplant_fuer) : ""}</span></span></a>`;

function sparkline(werte) {
  if (werte.length < 2) return "";
  const min = Math.min(...werte), max = Math.max(...werte), w = 160, h = 34;
  const pts = werte.map((v, i) => `${(i / (werte.length - 1) * w).toFixed(1)},${(h - 3 - (max === min ? .5 : (v - min) / (max - min)) * (h - 6)).toFixed(1)}`);
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" role="img" aria-label="Follower-Verlauf: von ${zahl(werte[0])} auf ${zahl(werte.at(-1))}">`
    + `<polyline points="${pts.join(" ")}" fill="none" stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}

// Kennzahlen einer Plattform zusammenfassen (verlauf = Tageswerte)
function zusammenfassung(k) {
  if (!k) return null;
  const verlauf = k.konto?.verlauf || [];
  const seit = tage => {
    const grenze = new Date(Date.now() - tage * 864e5).toISOString().slice(0, 10);
    const t = verlauf.filter(v => (v.datum || "") >= grenze && v.views != null);
    return t.length ? t.reduce((a, v) => a + v.views, 0) : null;
  };
  const reels = Object.values(k.reels || {});
  const summe = f => reels.length ? reels.reduce((a, r) => a + (r[f] || 0), 0) : null;
  const mit = reels.filter(r => r.wiedergabe_s != null);
  return {
    follower: k.konto?.follower, verlauf: verlauf.map(v => v.follower).filter(v => v != null),
    views: summe("views"), views7: seit(7), views28: seit(28),
    proReel: reels.length ? summe("views") / reels.length : null,
    wiedergabe: mit.length ? mit.reduce((a, r) => a + r.wiedergabe_s, 0) / mit.length : null,
    kommentare: summe("kommentare"), shares: summe("shares"), saves: summe("saves"), stand: k.stand,
  };
}

const wert = (b, span) => `<div class="wert"><b>${b}</b><span>${span}</span></div>`;

// Symbole (Lucide-Formen, 24er-Raster, Strich) – statt Textzeichen, damit alle gleich aussehen
const ICON = {
  x: "M18 6 6 18M6 6l12 12", check: "M20 6 9 17l-5-5", plus: "M12 5v14M5 12h14", links: "m15 18-6-6 6-6", rechts: "m9 18 6-6-6-6",
  alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
  extern: "M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  bild: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
  sfx: "M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0v-4a2 2 0 0 1 2-2",
  musik: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  clip: '<rect x="2" y="2" width="20" height="20" rx="2.2"/><path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5"/>',
  pause: '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
};
const icon = (name, cls = "") => {
  const inhalt = ICON[name].startsWith("<") ? ICON[name] : `<path d="${ICON[name]}"/>`;
  return `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${inhalt}</svg>`;
};

// ---------- Übersicht ----------
function botFehlerHtml(status, prefix = "") {
  return Object.entries(status || {}).filter(([key, s]) => key.startsWith(prefix) && s.ok === false)
    .map(([key, s]) => `<p class="klein fehlertext" role="alert"><b>Bot-Fehler ${esc(key.replace(":", " · "))}</b> · ${zeit(s.stand)}: ${esc(s.fehler || "Abruf fehlgeschlagen")}</p>`).join("");
}

async function uebersicht() {
  const [u, dmDaten] = await Promise.all([api("/api/uebersicht"), api("/api/dms").catch(() => ({ konversationen: [] }))]);
  const dmOffen = (dmDaten.konversationen || []).filter(c => c.offen);
  S.kanal = u.kanal || {};
  abzeichen(u);
  const k = S.kanal;
  const name = offen(k.name) ? "Reel-Kanal" : k.name;
  const z = u.zaehler || {};
  const feldName = { name: "Name", handle: "Handle", zielgruppe: "Zielgruppe", eigene_sprache: "eigene Sprache", schlusssatz: "Schlusssatz" };

  const summen = u.plattformen.map(p => zusammenfassung(p.kennzahlen)).filter(Boolean);
  const plattformen = u.plattformen.map(p => {
    const s = zusammenfassung(p.kennzahlen);
    const handle = String((u.kanal || {}).handle || "");
    const label = `${pfIcon(p.id)}${PLATTFORM_NAME[p.id] || esc(p.id)}`;
    const profil = PLATTFORM_URL[p.id] && handle && !handle.startsWith("OFFEN")
      ? `<a class="pf-link" href="${PLATTFORM_URL[p.id](encodeURIComponent(handle))}" target="_blank" rel="noopener" title="Profil @${esc(handle)} auf ${PLATTFORM_NAME[p.id]} öffnen">${label}<span class="sr"> (öffnet in neuem Tab)</span></a>` : label;
    const chip = p.aktiv ? `<span class="chip ok">aktiv</span>` : `<span class="chip">später</span>`;
    const hol = p.aktiv && KENNZAHLEN_PF.includes(p.id)
      ? `<button type="button" class="knopf klein" data-kz="${p.id}" title="Zahlen von ${PLATTFORM_NAME[p.id]} neu abrufen">aktualisieren</button>` : "";
    const inhalt = s ? `<div class="werte">${wert(zahl(s.follower), "Follower")}${wert(zahl(s.views), "Views gesamt")}`
      + `${wert(zahl(s.views7), "Views 7 Tage")}${wert(zahl(s.views28), "Views 28 Tage")}${wert(zahl(s.proReel), "Ø Views/Reel")}`
      + `${wert(s.wiedergabe == null ? "–" : zahl(s.wiedergabe) + " s", "Ø Wiedergabe")}${wert(zahl(s.kommentare), "Kommentare")}`
      + `${wert(zahl(s.shares) + " / " + zahl(s.saves), "Shares / Saves")}</div>${sparkline(s.verlauf)}`
      + `<span class="klein muted">Stand ${zeit(s.stand)}</span>`
      : `<span class="klein muted">${p.aktiv ? "Noch keine Zahlen – holt `tools/instagram/kennzahlen.py`." : "Vorbereitet, noch nicht im Einsatz."}</span>`;
    const ab = p.id === "instagram" ? u.ig_abruf || {} : {};
    const abruf = ab.ok || ab.fehler ? `<p class="klein muted">${ab.ok ? `Letzter Abruf ok ${zeit(ab.ok.zeit)} (${esc(ab.ok.art)})` : ""}`
      + `${ab.fehler ? `${ab.ok ? " · " : ""}<span class="warn-zeichen">Fehler ${zeit(ab.fehler.zeit)}</span>: ${esc(ab.fehler.meldung)}` : ""}</p>` : "";
    return `<div class="plattform${p.aktiv ? "" : " aus"}"><header>${profil}${chip}</header>${inhalt}${abruf}${hol}</div>`;
  }).join("");
  const gesamt = summen.length > 1
    ? `<p class="klein muted">Alle Kanäle: ${zahl(summen.reduce((a, s) => a + (s.follower || 0), 0))} Follower · ${zahl(summen.reduce((a, s) => a + (s.views || 0), 0))} Views</p>` : "";

  const top = u.reels.filter(r => r.kennzahlen?.instagram?.views != null)
    .sort((a, b) => b.kennzahlen.instagram.views - a.kennzahlen.instagram.views).slice(0, 5);
  const bot = u.bot || {};

  main.innerHTML = `
    <div class="kopf"><div><h1>${esc(name)}</h1>
      <p class="unter">${esc(k.nische || "")}</p></div>
      <div class="rechts"><a class="knopf" href="#/pipeline">Pipeline</a><a class="knopf" href="#/kalender">Kalender</a></div></div>
    <div class="raster uebersicht">
      ${u.ig_gesperrt ? `<div class="panel hinweis"><div><p><b>Instagram gesperrt</b> <span class="klein muted">seit ${zeit(u.ig_gesperrt.zeit)}</span></p>
        <p class="klein muted">${esc(u.ig_gesperrt.hinweis || "")}. Posten, Kommentare, DMs und Kennzahlen pausieren. Der Server prüft alle 30 min selbst.</p>
        <button type="button" class="knopf klein" id="ig-pruefen">Erneut prüfen</button></div></div>` : ""}
      ${u.offen.length ? `<div class="panel hinweis"><div><p><b>Noch offen:</b> ${u.offen.map(f => feldName[f] || f).join(", ")}.</p>
        <p class="klein muted">Diese Felder legen wir gemeinsam fest (gedaechtnis/Kanal/kanal.json). Bis dahin arbeiten die Agenten mit Platzhaltern.</p></div></div>` : ""}
      ${u.warten.length ? `<div class="panel freigabe-panel"><h2>Wartet auf deine Freigabe <span class="rechts chip akzent">${u.warten.length}</span></h2>
        <div class="liste">${u.warten.map(mini).join("")}</div></div>` : ""}
      ${dmOffen.length ? `<div class="panel dm-panel"><h2>DMs warten auf Antwort <span class="rechts chip akzent">${dmOffen.length}</span></h2>
        ${dmOffen.slice(0, 3).map(dmHtml).join("")}${dmOffen.length > 3 ? `<a class="knopf klein" href="#/dms">alle ${dmOffen.length} DMs →</a>` : ""}</div>` : ""}
      <div class="panel"><h2>Pipeline</h2><div class="zaehler">
        ${[["idee", "Ideen", "#/themen"], ["arbeit", "In Arbeit"], ["pruefung", "Prüfung"], ["freigabe", "Freigabe"], ["geplant", "Geplant"], ["live", "Live"]]
          .map(([key, label, href]) => `<a href="${href || "#/pipeline"}" class="${key === "freigabe" && z[key] ? "heiss" : ""}"><b>${z[key] || 0}</b><span>${label}</span></a>`).join("")}
      </div></div>
      <div class="panel w8"><h2>Plattformen <button type="button" class="knopf klein rechts" id="kz-alle">alle aktualisieren</button></h2><div class="plattformen">${plattformen}</div>${gesamt}</div>
      <div class="panel w4 credits" id="credits"><h2>ElevenLabs</h2><p class="muted klein">Lade Credits …</p></div>
      <div class="panel w6"><h2>Nächste Posts</h2>${u.naechste.length ? `<div class="liste">${u.naechste.map(mini).join("")}</div>`
        : leer("Nichts geplant", "Freigegebene Reels erscheinen hier mit Uhrzeit.")}</div>
      <div class="panel w6"><h2>Kommentar-Bot <span class="rechts chip${bot.modus === "live" ? " ok" : bot.modus === "probelauf" ? " warn" : ""}">${esc(bot.modus || "aus")}</span></h2>
        ${botFehlerHtml(bot.status)}
        <div class="werte">${wert(zahl(bot.gesamt), "Kommentare")}${wert(zahl(bot.beantwortet), "beantwortet")}
          ${wert(zahl(bot.ausgeblendet), "ausgeblendet")}${wert(`<a href="#/kommentare">${zahl(bot.eskalationen)}</a>`, "an dich eskaliert")}
          ${wert(zahl((bot.keyword_dms || {}).gesamt), "Keyword-DMs")}</div>
        ${((bot.keyword_dms || {}).link_fehlt || []).map(x => `<p class="klein"><span class="chip warn">Ressourcen-Link fehlt</span> <a href="#/reel/${encodeURIComponent(x.reel_id)}">${esc(x.reel_id)}</a>: ${zahl(x.anzahl)} Kommentar(e) warten, DM geht erst mit Link raus</p>`).join("")}
        ${bot.letzter_lauf ? `<p class="klein muted">Letzter Lauf ${zeit(bot.letzter_lauf)}</p>` : `<p class="klein muted">Startet in Phase 2 (tools/instagram/).</p>`}</div>
      <div class="panel"><h2>Top-Reels</h2>${top.length ? `<div class="liste">${top.map(r => {
        const kz = r.kennzahlen.instagram;
        return `<a href="#/reel/${encodeURIComponent(r.id)}"><span class="mini">${frame(r)}</span><span style="flex:1"><b>${esc(r.titel)}</b></span>`
          + `<span class="mono klein">${zahl(kz.views)} Views · ${zahl(kz.saves)} Saves · ${zahl(kz.shares)} Shares</span></a>`;
      }).join("")}</div>` : leer("Noch keine Zahlen", "Sobald Reels live sind, stehen hier die stärksten.")}</div>
    </div>`;
  dmVerdrahten(main, uebersicht);
  const igp = $("#ig-pruefen");
  if (igp) igp.onclick = async () => {
    igp.disabled = true; igp.textContent = "prüft …";
    try {
      const r = await api("/api/instagram/pruefen", {});
      toast(r.ok ? "Instagram freigegeben, Zahlen werden neu geholt." : `Weiter gesperrt: ${r.fehler}`, !r.ok);
    } catch (e) { toast(e.message, true); }
    uebersicht();
  };
  main.querySelectorAll("[data-kz]").forEach(b => b.onclick = () => kennzahlenHolen([b.dataset.kz], b));
  $("#kz-alle").onclick = e => kennzahlenHolen([...main.querySelectorAll("[data-kz]")].map(b => b.dataset.kz), e.currentTarget);
  credits();
}

const KENNZAHLEN_PF = ["instagram", "tiktok", "youtube"];
async function kennzahlenHolen(ids, knopf) {
  if (!ids.length) return toast("Keine Plattform mit Abruf aktiv.", true);
  main.querySelectorAll("[data-kz], #kz-alle").forEach(b => { b.disabled = true; });
  knopf.textContent = "holt …";
  const fehler = [];
  for (const id of ids) {
    try {
      const r = await api("/api/kennzahlen/" + id, {});
      if (!r.ok) fehler.push(`${PLATTFORM_NAME[id]}: ${r.fehler}`);
    } catch (e) { fehler.push(`${PLATTFORM_NAME[id]}: ${e.message}`); }
  }
  toast(fehler.length ? fehler.join(" · ") : "Zahlen aktualisiert.", !!fehler.length);
  uebersicht();
}

// Übersicht lädt sich selbst nach, damit neue Plattform-Zahlen (holt der Server regelmäßig) ohne Neuladen erscheinen
setInterval(() => { if (document.body.dataset.ansicht === "uebersicht" && !document.hidden && !document.querySelector("[data-kz]:disabled")
  && ![...document.querySelectorAll(".dm-antwort textarea")].some(t => t.value.trim())) uebersicht();   // nie eine angefangene Antwort wegwerfen
}, 120000);

async function credits(neu = false) {
  const el = $("#credits");
  if (!el) return;
  try {
    const c = await api("/api/credits" + (neu ? "?neu=1" : ""));
    const d = c.daten;
    const knopf = `<button class="knopf klein" id="credits-neu">aktualisieren</button>`;
    if (!d) { el.innerHTML = `<h2>ElevenLabs</h2><p class="klein muted">Nicht abrufbar: ${esc(c.fehler || "unbekannt")}</p>${knopf}`; }
    else {
      const anteil = d.limit ? Math.max(0, Math.min(100, d.rest / d.limit * 100)) : 0;
      el.innerHTML = `<h2>ElevenLabs <span class="rechts chip">${esc(d.plan || "")}</span></h2>
        <div style="display:grid;gap:10px"><div><b class="gross">${zahl(d.rest)}</b> <span class="muted">von ${zahl(d.limit)} Credits</span></div>
        <div class="balken"><i style="width:${anteil.toFixed(1)}%"></i></div>
        <div class="werte">${wert("≈ " + zahl(d.reels_moeglich), "Reels möglich")}${wert(zahl(d.credits_pro_reel), "Credits pro Reel")}</div>
        ${(d.konten || []).length > 1 ? `<span class="klein muted">${d.konten.map(k => `${esc(k.name)}: ${k.fehler ? esc(k.fehler) : zahl(k.rest) + " / " + zahl(k.limit)}`).join(" · ")}</span>` : ""}
        <span class="klein muted">Reset ${zeit(d.reset, true)} · ${esc(d.modell)}${c.fehler ? ` · <span class="warn-zeichen">letzter Abruf fehlgeschlagen</span>` : ""}</span>
        <div>${knopf}</div></div>`;
    }
    $("#credits-neu", el).onclick = () => credits(true);
  } catch (e) {
    el.innerHTML = `<h2>ElevenLabs</h2><p class="klein muted">${esc(e.message)}</p>`;
  }
}

// ---------- Pipeline ----------
async function pipeline() {
  const [r, t] = await Promise.all([api("/api/reels"), api("/api/themen")]);
  const ideen = t.themen.filter(x => x.status === "idee")
    .sort((a, b) => (a.prio ?? 9) - (b.prio ?? 9) || a.id.localeCompare(b.id));
  const spalten = SPALTEN.map(([key, label]) => {
    if (key === "idee") {
      const zeige = ideen.slice(0, 8);
      return `<section class="spalte"><header><b>${label}</b><span>${ideen.length}</span></header><div class="karten">${zeige.map(x =>
        `<div class="idee"><div class="titel">${esc(x.titel_en || x.titel_de)}</div><div class="zeile">${saeuleChip(x.saeule)}`
        + `${x.prio ? `<span class="chip akzent">${PRIO_NAME[x.prio]}</span>` : ""}<span class="mono">${esc(x.id)}</span></div></div>`).join("")}
        ${ideen.length > zeige.length ? `<a class="knopf klein" href="#/themen">alle ${ideen.length} Themen →</a>` : ""}
        ${ideen.length ? "" : leer("Keine Ideen", "")}</div></section>`;
    }
    const liste = r.reels.filter(x => x.spalte === key);
    return `<section class="spalte ${key}"><header><b>${label}</b><span>${liste.length}</span></header>`
      + `<div class="karten">${liste.length ? liste.map(karte).join("") : `<div class="leer klein">–</div>`}</div></section>`;
  }).join("");
  main.innerHTML = `<div class="kopf"><div><h1>Pipe<span class="akzent">line</span></h1>
    <p class="unter">Von der Idee bis live. Reels legt der Hauptagent mit /reel an.</p></div></div>
    ${r.reels.length ? "" : `<div class="panel hinweis" style="margin-bottom:18px"><p>Noch kein Reel angelegt. Starte das Pilot-Reel im Chat mit <span class="mono">/reel</span>.</p></div>`}
    <div class="pipeline">${spalten}</div>`;
}

// ---------- Reel-Seite ----------
function naechstePostzeit(wunsch) {
  const [h, m] = (S.kanal.takt?.postzeit || "19:00").split(":").map(Number);
  const frueheste = new Date(Date.now() + 30 * 60e3);
  let d = wunsch ? new Date(wunsch + "T12:00") : new Date();
  d.setHours(h, m || 0, 0, 0);
  if (d < frueheste) {                       // Wunschtermin vorbei → nächster Abend, der noch erreichbar ist
    d = new Date();
    d.setHours(h, m || 0, 0, 0);
    if (d < frueheste) d.setDate(d.getDate() + 1);
  }
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function freigabePanel(r) {
  const f = r.freigabe || {};
  const gepostet = r.post?.gepostet_am || r.stufe === "live";
  if (f.status === "aendern" && r.stufe !== "freigabe") {
    return `<div class="panel hinweis"><div><p><b>Dein Änderungswunsch</b> <span class="klein muted">${zeit(f.zeit)}</span></p>
      <p>${esc(f.feedback)}</p><p class="klein muted">Der Hauptagent arbeitet ihn beim nächsten /reel-Lauf ein.</p></div></div>`;
  }
  if (gepostet || !["freigabe", "geplant"].includes(r.stufe)) return "";
  const checks = [
    [!!r.final, "Final-Render"],
    [r.caption, "Caption"],
  ].map(([ok, t]) => `<span class="chip ${ok ? "ok" : "warn"}">${icon(ok ? "check" : "alert")} ${ok ? t : t + " fehlt"}</span>`).join("");
  const stand = f.status ? `<p class="klein">Aktuell: ${freigabeChip(f)} ${zeit(f.zeit)}${r.post?.geplant_fuer ? ` · posten ${zeit(r.post.geplant_fuer)}` : f.status === "freigegeben" ? " · sofort posten" : ""}</p>` : "";
  return `<div class="panel freigabe-panel" id="freigabe"><h2>Deine Freigabe</h2>
    <div class="checks">${checks}</div>${stand}
    <p class="klein muted" style="margin:12px 0 6px">Was soll anders werden? (Pflicht bei „Ändern“, sonst optional)</p>
    <textarea id="fb-text" aria-label="Was soll anders werden?" placeholder="z. B. Hook kürzer, Shot 7 anderes Bild …"></textarea>
    <div class="aktionen">
      <label class="klein">Posten am <input type="datetime-local" id="fb-um" value="${f.status === "freigegeben" && r.post?.geplant_fuer ? esc(r.post.geplant_fuer) : naechstePostzeit(r.plan?.datum)}"></label>
      <button class="knopf primaer" data-entscheid="freigegeben">Freigeben</button>
      <button class="knopf" data-entscheid="aendern">Ändern</button>
      <button class="knopf gefahr" data-entscheid="verworfen">Verwerfen</button>
    </div>
    ${r.plan?.datum ? `<p class="klein">Wunschtermin aus dem <a href="#/kalender/${esc(r.plan.datum.slice(0, 7))}">Kalender</a>: ${tagLang(r.plan.datum)}${r.plan.datum < new Date().toLocaleDateString("sv-SE") ? " – schon vorbei, deshalb der nächste freie Abend" : ""}</p>` : ""}
    <p class="klein muted">Feld „Posten am“ leeren = der Publisher postet beim nächsten Lauf. Gepostet wird nur, was hier freigegeben ist.</p></div>`;
}

function reelText(r, quelle, sprechtext = false) {
  if (!quelle) return null;
  const basis = `reels/${r.id}`;
  let html = md(quelle, {
    bild: src => /^https?:/.test(src) ? src : datei(pfadVerbinden(basis, src)),
    link: href => datei(pfadVerbinden(basis, href)),
  });
  if (sprechtext) html = html.replace(/\{pause(?:\s+([\d.]+))?\}/gi, (_, s) => `<span class="pause">${icon("pause")} ${s ? s + " s" : "Pause"}</span>`);
  return `<div class="text${sprechtext ? " sprechtext" : ""}">${html}</div>`;
}

function befundBild(r, b) {
  if (!b) return "";
  const p = b.startsWith("reels/") ? b : `reels/${r.id}/${b}`;
  return `<img src="${datei(p)}" alt="" loading="lazy" data-gross>`;
}

function kommentarHtml(c) {
  const chips = [
    c.kategorie ? `<span class="chip">${esc(c.kategorie)}</span>` : "",
    c.eskalieren ? `<span class="chip ${c.erledigt ? "" : "bad"}">${c.erledigt ? "erledigt" : "eskaliert"}</span>` : "",
    c.ausblenden ? `<span class="chip warn">ausgeblendet</span>` : "",
    c.beantwortet ? `<span class="chip ok">beantwortet</span>` : "",
    c.dm_gesendet ? `<span class="chip ok">DM gesendet · ${esc(c.keyword || "")}</span>` : "",
  ].join("");
  return `<div class="kommentar"><div class="zeile klein muted" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
      <b style="color:var(--ink)">@${esc(c.user)}</b> ${zeit(c.zeit)} · ${esc(PLATTFORM_NAME[c.plattform] || c.plattform || "")}
      ${c.reel_id ? ` · <a href="#/reel/${encodeURIComponent(c.reel_id)}">${esc(c.reel_id)}</a>` : ""} ${chips}</div>
    <div>${esc(c.text)}</div>
    ${c.antwort ? `<div class="antwort">${esc(c.antwort)}</div>` : ""}
    ${c.grund ? `<div class="klein muted">${esc(c.grund)}</div>` : ""}
    ${c.eskalieren && !c.erledigt ? `<div><button class="knopf klein" data-erledigt="${esc(c.id)}">erledigt</button></div>` : ""}</div>`;
}

async function reelSeite(id) {
  const r = await api("/api/reel/" + encodeURIComponent(id));
  if (!S.kanal.saeulen) S.kanal = (await api("/api/uebersicht")).kanal || {};

  // Video: gewählte Version, sonst Final, sonst neueste
  const versionen = r.versionen.filter(v => v.pfad);
  if (r.final && !versionen.some(v => v.pfad === r.final)) versionen.push({ datei: "renders/final_master.mp4", pfad: r.final, notiz: "Final" });
  const wahl = S.version[r.id] && versionen.find(v => v.pfad === S.version[r.id]) ? S.version[r.id] : (r.final || versionen.at(-1)?.pfad);
  const video = wahl ? `<div class="frame"><video src="${datei(wahl)}" controls playsinline preload="metadata"></video></div>` : frame(r);
  const kz = r.kennzahlen?.instagram;
  const tts = r.tts;

  const reiter = [
    ["skript", "Skript", () => reelText(r, r.skript, true)],
    ["storyboard", "Storyboard", () => reelText(r, r.storyboard)],
    ["brief", "Brief", () => reelText(r, r.brief)],
    ["pruefung", `Prüfung${r.reviews.length ? ` (${r.reviews.length})` : ""}`, () => pruefungTab(r)],
    ["caption", "Caption", () => captionTab(r)],
    ["kommentare", `Kommentare${r.kommentare.length ? ` (${r.kommentare.length})` : ""}`, () => r.kommentare.length ? r.kommentare.map(kommentarHtml).join("") : null],
    ["log", "Log", () => r.log.length ? `<div class="log">${[...r.log].reverse().map(l =>
      `<div><span class="mono muted">${zeit(l.zeit)}</span><span class="muted">${esc(l.wer)}</span><span>${esc(l.text)}</span></div>`).join("")}</div>` : null],
    ["kosten", "Kosten", () => kostenTab(r)],
  ];
  if (!reiter.some(([k]) => k === S.reiter)) S.reiter = "skript";
  const aktiv = reiter.find(([k]) => k === S.reiter);

  const schritte = SCHRITTE.map(s => {
    const info = r.schritte?.[s] || {};
    const z = schrittZustand(r, s);
    const wann = info.ende || info.start;
    const extra = s === "pruefung" && r.pruefrunde ? ` <span class="klein muted">Runde ${r.pruefrunde}</span>` : "";
    return `<div class="schritt ${z}"><i class="punkt"></i><div><b>${STUFE_NAME[s]}</b>${extra}
      ${info.agent ? ` <span class="klein muted">${esc(info.agent)}</span>` : ""}
      ${info.notiz ? `<div class="klein muted">${esc(info.notiz)}</div>` : ""}</div>
      <span class="klein mono muted">${wann ? zeit(wann) : ""}</span></div>`;
  }).join("");

  main.innerHTML = `
    <a class="zurueck" href="#/pipeline">← Pipeline</a>
    <div class="kopf"><div><h1 style="font-size:clamp(28px,3.4vw,44px)">${esc(r.titel)}</h1>
      <p class="unter"><span class="mono">${esc(r.id)}</span> ${r.saeule ? " · " + saeuleChip(r.saeule) : ""}
        ${r.thema_id ? ` · <span class="mono">${esc(r.thema_id)}</span>` : ""} · Ende: ${esc(ENDE_NAME[r.ende] || r.ende || "–")}</p></div>
      <div class="rechts"><span class="chip">${STUFE_NAME[r.stufe] || esc(r.stufe)}</span>${pruefChip(r.pruefung)}${freigabeChip(r.freigabe)}</div></div>
    <div class="reel">
      <div class="links">
        ${video}
        ${versionen.length > 1 ? `<div class="versionen">${versionen.map(v =>
          `<button data-version="${esc(v.pfad)}" aria-pressed="${v.pfad === wahl}" title="${esc([v.notiz, zeit(v.zeit)].filter(Boolean).join(" · "))}">${esc(v.datei.split("/").pop().replace(/\.mp4$/, ""))}</button>`).join("")}</div>` : ""}
        ${r.stimme ? `<div class="panel" style="padding:12px 14px"><h2>Stimme</h2><audio controls preload="none" src="${datei(r.stimme)}" style="width:100%"></audio>
          ${tts ? `<p class="klein muted" style="margin:6px 0 0">${esc(tts.stimme)} · ${zahl(tts.dauer)} s · ${zahl(tts.woerter)} Wörter${tts.pausen?.length ? ` · ${tts.pausen.length} Pausen` : ""}</p>` : ""}</div>` : ""}
        ${r.post?.permalink ? `<a class="knopf" href="${esc(r.post.permalink)}" target="_blank" rel="noopener">Auf Instagram ansehen ${icon("extern")}</a>` : ""}
        ${kz ? `<div class="panel" style="padding:12px 14px"><h2>Instagram <span class="rechts klein muted">${zeit(kz.stand)}</span></h2><div class="werte">
          ${wert(zahl(kz.views), "Views")}${wert(zahl(kz.reichweite), "Reichweite")}${wert(kz.wiedergabe_s == null ? "–" : zahl(kz.wiedergabe_s) + " s", "Ø Wiedergabe")}
          ${wert(zahl(kz.likes), "Likes")}${wert(zahl(kz.kommentare), "Kommentare")}${wert(zahl(kz.shares), "Shares")}${wert(zahl(kz.saves), "Saves")}</div></div>` : ""}
      </div>
      <div class="rechts">
        ${freigabePanel(r)}
        <div class="panel"><h2>Schritte</h2><div class="schritte">${schritte}</div></div>
        <div class="panel"><div class="reiter" role="tablist">${reiter.map(([k, label]) =>
          `<button role="tab" data-reiter="${k}" aria-selected="${k === S.reiter}">${label}</button>`).join("")}</div>
          <div id="reiter-inhalt">${aktiv[2]() || leer("Noch nichts da", "Entsteht im jeweiligen Schritt.")}</div></div>
      </div>
    </div>`;

  $$("[data-version]").forEach(b => b.onclick = () => { S.version[r.id] = b.dataset.version; reelSeite(id); });
  $$("[data-reiter]").forEach(b => b.onclick = () => {
    S.reiter = b.dataset.reiter;
    $$("[data-reiter]").forEach(x => x.setAttribute("aria-selected", x === b));
    const t = reiter.find(([k]) => k === S.reiter);
    $("#reiter-inhalt").innerHTML = t[2]() || leer("Noch nichts da", "Entsteht im jeweiligen Schritt.");
    verdrahteReiter(r, id);
  });
  verdrahteReiter(r, id);

  $$("[data-entscheid]").forEach(b => b.onclick = async () => {
    const entscheid = b.dataset.entscheid;
    const feedback = $("#fb-text").value.trim();
    const um = $("#fb-um").value;
    if (entscheid === "aendern" && !feedback) { toast("Bitte kurz beschreiben, was anders werden soll.", true); $("#fb-text").focus(); return; }
    if (entscheid === "verworfen" && !confirm("Reel wirklich verwerfen?")) return;
    $$("[data-entscheid]").forEach(x => x.disabled = true);
    try {
      await api(`/api/reel/${encodeURIComponent(r.id)}/freigabe`, { entscheid, feedback, um: entscheid === "freigegeben" ? um : "" });
      toast({ freigegeben: um ? `Freigegeben – posten ${zeit(um)}` : "Freigegeben – wird beim nächsten Lauf gepostet",
        aendern: "Änderungswunsch gespeichert", verworfen: "Reel verworfen" }[entscheid]);
      abzeichen();
      reelSeite(id);
    } catch (e) {
      toast(e.message, true);
      $$("[data-entscheid]").forEach(x => x.disabled = false);
    }
  });
}

function verdrahteReiter(r, id) {
  const kopie = $("#caption-kopie");
  if (kopie) kopie.onclick = async () => {
    try { await navigator.clipboard.writeText(r.caption_json.instagram.caption); toast("Caption kopiert"); }
    catch { toast("Kopieren nicht möglich – Text bitte markieren", true); }
  };
  $$("[data-erledigt]", $("#reiter-inhalt")).forEach(b => b.onclick = () => erledigt(b.dataset.erledigt, () => reelSeite(id)));
}

function pruefungTab(r) {
  if (!r.reviews.length && !r.pruefboegen.length) return null;
  const berichte = [...r.reviews].reverse().map((v, i) => {
    const d = v.daten || {};
    const befunde = (d.befunde || []).map(b => {
      const blocker = /^b/i.test(b.schwere || "");
      return `<div class="befund"><span class="chip ${blocker ? "bad" : "warn"}">${esc(b.nr ?? "")} · ${esc(b.schwere || "")}</span>
        <div><b>${b.shot != null ? `Shot ${esc(b.shot)}` : ""}${b.zeit != null ? ` · ${esc(b.zeit)} s` : ""}</b> ${esc(b.problem)}
        ${b.loesung ? `<div class="muted">→ ${esc(b.loesung)}</div>` : ""}${b.agent ? `<span class="chip">${esc(b.agent)}</span>` : ""}</div>
        ${befundBild(r, b.bild)}</div>`;
    }).join("");
    return `<details${i === 0 ? " open" : ""} style="margin-bottom:14px"><summary style="cursor:pointer;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <b>Runde ${esc(d.runde ?? "?")}</b> <span class="chip ${d.ergebnis === "FREIGABEREIF" ? "ok" : "warn"}">${esc(d.ergebnis || "?")}</span>
        <span class="klein muted">${zahl(d.blocker)} Blocker · ${zahl(d.maengel)} Mängel</span></summary>
      <div style="margin-top:10px">${befunde || `<p class="muted klein">Keine Befunde.</p>`}
      ${v.md ? `<details style="margin-top:10px"><summary class="klein" style="cursor:pointer">Ganzer Bericht</summary>${reelText(r, v.md)}</details>` : ""}</div></details>`;
  }).join("");
  const boegen = r.pruefboegen.length ? `<h3 style="font:600 12px var(--body);letter-spacing:.09em;text-transform:uppercase;color:var(--muted)">Prüfbögen (Sperrzonen)</h3>
    <div class="raster pruefbogen" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">${r.pruefboegen.map(p =>
      `<img src="${datei(p)}" alt="Prüfbogen" loading="lazy" data-gross>`).join("")}</div>` : "";
  return berichte + boegen;
}

function captionTab(r) {
  const ig = r.caption_json?.instagram;
  if (!ig) return r.caption_md ? reelText(r, r.caption_md) : null;
  return `<div style="display:grid;gap:12px">
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><button class="knopf primaer klein" id="caption-kopie">Caption kopieren</button>
      <span class="klein muted">${zahl((ig.caption || "").length)} Zeichen (Ziel 150–300) · ${zahl((ig.hashtags || []).length)} Hashtags</span>
      ${ig.ki_label ? `<span class="chip warn">KI-Label beim Upload setzen</span>` : ""}</div>
    <div class="caption-text">${esc(ig.caption)}</div>
    <div class="werte">${wert(ig.cover_zeit == null ? "–" : zahl(ig.cover_zeit) + " s", "Cover-Zeitpunkt")}${wert(esc(ENDE_NAME[r.caption_json.ende_baustein] || r.caption_json.ende_baustein || "–"), "Ende-Baustein")}</div>
    ${ig.alt_text ? `<div><b class="klein">Alt-Text</b><p style="margin:2px 0 0">${esc(ig.alt_text)}</p></div>` : ""}
    ${ig.erster_kommentar ? `<div><b class="klein">Erster Kommentar</b><p style="margin:2px 0 0">${esc(ig.erster_kommentar)}</p></div>` : ""}
  </div>`;
}

function kostenTab(r) {
  const k = r.kosten || {};
  const t = r.tts;
  if (!t && !k.elevenlabs_zeichen) return null;
  return `<div class="werte" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr))">
    ${wert(zahl(k.elevenlabs_zeichen), "ElevenLabs-Credits")}${wert(zahl(k.elevenlabs_rest), "Rest danach")}
    ${t ? wert(zahl(t.zeichen), "Zeichen im Skript") + wert(t.wiederverwendet ? "ja" : "nein", "wiederverwendet") : ""}</div>
    ${t ? `<p class="klein muted">${esc(t.stimme)} · ${esc(t.model_id)} · Tempo ×${esc(t.atempo)} · Pausen ${esc(t.keep)} s · ${zeit(t.zeit)}</p>
      ${t.pausen?.length ? `<p class="klein">Dramaturgie-Pausen: ${t.pausen.map(p => `nach „${esc(p.nach)}“ ${zahl(p.sekunden)} s`).join(", ")}</p>` : ""}` : ""}`;
}

// ---------- Themen ----------
let themenDaten = null;

async function themenSeite() {
  themenDaten = await api("/api/themen");
  if (!S.kanal.saeulen) S.kanal = (await api("/api/uebersicht")).kanal || {};
  const f = S.themen;
  const seg = (feld, werte) => `<div class="seg" data-feld="${feld}">${werte.map(([w, l]) =>
    `<button data-wert="${w}" aria-pressed="${f[feld] === w}">${l}</button>`).join("")}</div>`;
  main.innerHTML = `
    <div class="kopf"><div><h1>The<span class="akzent">men</span></h1><p class="unter">Backlog mit Säule, Prinzip und Priorität. Hohe Priorität kommt bei /reel zuerst dran.</p></div>
      <div class="rechts">${themenDaten.wochenlisten.map(w => `<a class="knopf klein" href="#/wissen/Themen/${encodeURIComponent(w)}">${esc(w.replace(/\.md$/, ""))}</a>`).join("")}</div></div>
    <div class="filter">
      <input type="search" id="th-q" aria-label="Themen durchsuchen" placeholder="Suchen: Titel, Prinzip, Kategorie …" value="${esc(f.q)}">
      <select id="th-saeule" aria-label="Säule"><option value="">Alle Säulen</option>${(S.kanal.saeulen || []).map(s =>
        `<option value="${esc(s.id)}"${f.saeule === s.id ? " selected" : ""}>${esc(s.name)}</option>`).join("")}</select>
      ${seg("status", [["", "Alle"], ["idee", "Idee"], ["in_arbeit", "In Arbeit"], ["erledigt", "Erledigt"], ["verworfen", "Verworfen"]])}
      ${seg("prio", [["", "Jede Priorität"], ["1", "Hoch"], ["2", "Mittel"], ["3", "Niedrig"], ["ohne", "Ohne"]])}
      <span class="klein muted" id="th-zahl"></span>
    </div>
    <div class="themen" id="th-liste"></div>`;
  $("#th-q").oninput = e => { f.q = e.target.value; themenListe(); };
  $("#th-saeule").onchange = e => { f.saeule = e.target.value; themenListe(); };
  $$(".seg[data-feld]").forEach(s => s.onclick = e => {
    const b = e.target.closest("button");
    if (!b) return;
    f[s.dataset.feld] = b.dataset.wert;
    $$("button", s).forEach(x => x.setAttribute("aria-pressed", x === b));
    themenListe();
  });
  themenListe();
}

function themenListe() {
  const f = S.themen;
  const q = f.q.trim().toLowerCase();
  const liste = themenDaten.themen.filter(t =>
    (!f.status || t.status === f.status) && (!f.saeule || t.saeule === f.saeule)
    && (!f.prio || (f.prio === "ohne" ? t.prio == null : String(t.prio) === f.prio))
    && (!q || [t.id, t.titel_en, t.titel_de, t.prinzip, t.kategorie, t.hook].some(x => (x || "").toLowerCase().includes(q))))
    .sort((a, b) => (a.prio ?? 9) - (b.prio ?? 9) || a.id.localeCompare(b.id));
  $("#th-zahl").textContent = `${liste.length} von ${themenDaten.themen.length}`;
  $("#th-liste").innerHTML = liste.length ? liste.map(t => `
    <div class="thema${t.status === "verworfen" ? " verworfen" : ""}">
      <span class="tid">${esc(t.id)}</span>
      <div><div class="en">${esc(t.titel_en)}</div><div class="de">${esc(t.titel_de)}</div>
        ${t.hook ? `<div class="klein" style="margin-top:4px">Hook: „${esc(t.hook)}“</div>` : ""}
        <div class="zeile">${saeuleChip(t.saeule)}<span class="muted">${esc(t.prinzip || "")}</span>
          ${t.umstritten ? `<span class="chip warn" title="${esc(typeof t.umstritten === "string" ? t.umstritten : "")}">⚠ umstritten</span>` : ""}
          ${t.quellen?.length ? `<span class="chip">${t.quellen.length} Quelle${t.quellen.length > 1 ? "n" : ""}</span>` : ""}
          ${t.status !== "idee" && t.status !== "verworfen" ? `<span class="chip">${esc(t.status.replace("_", " "))}</span>` : ""}
          ${t.reel ? `<a class="chip akzent" href="#/reel/${encodeURIComponent(t.reel)}">Reel →</a>` : ""}</div></div>
      <div class="prio" data-thema="${esc(t.id)}">${[1, 2, 3].map(p =>
        `<button data-prio="${p}" aria-pressed="${t.prio === p}" aria-label="Priorität ${PRIO_NAME[p]}">${PRIO_NAME[p]}</button>`).join("")}
        <button class="weg" data-weg aria-pressed="${t.status === "verworfen"}" title="${t.status === "verworfen" ? "wieder aufnehmen" : "verwerfen"}" aria-label="${t.status === "verworfen" ? "Wieder aufnehmen" : "Verwerfen"}">${icon("x")}</button></div>
    </div>`).join("") : `<div style="padding:16px">${leer("Keine Themen", "Filter lockern oder /themen laufen lassen.")}</div>`;
  $$("#th-liste [data-thema]").forEach(box => box.onclick = async e => {
    const b = e.target.closest("button");
    if (!b) return;
    const t = themenDaten.themen.find(x => x.id === box.dataset.thema);
    const neu = b.hasAttribute("data-weg")
      ? { status: t.status === "verworfen" ? "idee" : "verworfen" }
      : { prio: t.prio === Number(b.dataset.prio) ? null : Number(b.dataset.prio) };
    try {
      Object.assign(t, await api(`/api/thema/${encodeURIComponent(t.id)}`, neu));
      themenListe();
    } catch (err) { toast(err.message, true); }
  });
}

// ---------- Kommentare ----------
const FUNNEL_TEXT = [
  ["intro_text", "Erste DM", "Der Send-link-Button und SEND LINK am PC starten den Ablauf."],
  ["follow_text", "Follow-Nachricht", "Buttonnamen im Text genauso schreiben wie unten."],
  ["follow_again_text", "Noch kein Follow", "Steht vor der Follow-Nachricht, wenn jemand zu früh I followed tippt."],
  ["email_text", "E-Mail-Frage", "Die Adresse wird nur für spätere Ressourcen-Anfragen gespeichert, nicht für Newsletter."],
  ["email_again_text", "Ungültige E-Mail", "Erscheint vor der E-Mail-Frage."],
  ["link_text", "Link-Nachricht", "{link} als Platzhalter muss enthalten sein."],
];
const FUNNEL_BUTTONS = [["start_button", "Start-Button"], ["follow_now_button", "Follow-Button"], ["follow_button", "Bestätigungs-Button"]];

// Eingabefeld mit Einträgen als Chips (öffentliche Antworten, Keywords): Enter oder „Hinzufügen“, × entfernt.
const chipBlock = (id, label, placeholder, note) => `<div class="funnel-feld"><span>${label}</span><div class="funnel-chips" id="${id}-chips"></div>
  <div class="funnel-neu"><input id="${id}-neu" maxlength="180" placeholder="${placeholder}" autocomplete="off"><button class="knopf" type="button" id="${id}-add">Hinzufügen</button></div>
  <small>${note}</small></div>`;
let funnelRefresh = () => {};
function chipEditor(id, start, { max, norm = x => x, check = () => "" }) {
  const list = [...start];
  const draw = () => {
    funnelRefresh();
    $(`#${id}-chips`).innerHTML = list.map((a, i) => `<span class="funnel-chip">${esc(a)}<button type="button" data-i="${i}" aria-label="Entfernen">×</button></span>`).join("")
      || `<span class="muted klein">Noch nichts eingetragen.</span>`;
    $$(`#${id}-chips button`).forEach(b => b.onclick = () => { list.splice(+b.dataset.i, 1); draw(); });
  };
  const add = () => {
    const feld = $(`#${id}-neu`), wert = norm(feld.value.trim());
    if (!wert) return true;
    const fehler = check(wert);
    if (fehler) { toast(fehler, true); return false; }
    if (list.length >= max) { toast(`Höchstens ${max} Einträge.`, true); return false; }
    if (!list.includes(wert)) list.push(wert);
    feld.value = ""; draw(); feld.focus();
    return true;
  };
  $(`#${id}-add`).onclick = add;
  $(`#${id}-neu`).onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); add(); } };
  draw();
  return { list, add };
}

async function keywordFunnelSeite() {
  const data = await api("/api/dm-funnel");
  funnelRefresh = () => {};
  const selected = S.funnelReel;
  const own = selected ? (data.reels[selected] || {}) : data.default;
  const base = data.default;
  const asText = value => Array.isArray(value) ? value.join("\n") : (value || "");
  // Bei einem Reel zeigen Texte und Buttons den Standard als Vorgabe; nur Abweichungen werden als eigene Regel gespeichert.
  const vorgabe = key => (own[key] ?? (selected && !["link", "profile_link"].includes(key) ? base[key] : "")) ?? "";
  const input = (key, label, note = "", multi = false) => `<label class="funnel-feld"><span>${esc(label)}</span>
    ${multi ? `<textarea name="${key}" rows="1" placeholder="${selected ? esc(asText(base[key]) || "Standard") : ""}">${esc(asText(vorgabe(key)))}</textarea>`
      : `<input name="${key}" value="${esc(asText(vorgabe(key)))}" placeholder="${selected ? esc(asText(base[key]) || "Standard") : ""}">`}
    ${note ? `<small>${esc(note)}</small>` : ""}</label>`;
  const txt = key => { const [label, note] = FUNNEL_TEXT.find(x => x[0] === key).slice(1); return input(key, label, note, true); };
  const btn = (key, label) => input(key, label, "Höchstens 20 Zeichen.");
  const titel = selected ? (data.reel_list.find(r => r.id === selected)?.titel || selected) : "Standard für alle Reels";
  main.innerHTML = `<div class="funnel-seite"><div class="funnel-haupt"><div class="kopf"><div><h1>DM-Kommentar-<span class="akzent">Funnel</span></h1>
    <p class="unter">Kommentar-zu-DM-Ablauf: Standard für alle Reels oder eigene Regeln je Reel – auch für Reels, die noch nicht online sind. Jedes Reel hat sein eigenes Keyword und seinen eigenen Link; wer unter mehreren Reels kommentiert, bekommt zu jedem den passenden Link. Änderungen gelten für neue Kommentare.</p></div></div>
    ${data.test_active ? `<div class="panel"><span class="chip warn">TEST aktiv</span> Der laufende TEST-Kommentarversuch hat Vorrang. Die regulären Reel-Einstellungen wirken nach dem Test.</div>` : ""}
    <div class="panel"><div class="funnel-feld"><span>Bearbeiten</span>
      <div class="funnel-wahl" role="radiogroup" aria-label="Reel wählen">
        <button type="button" role="radio" aria-checked="${!selected}" class="funnel-karte" data-funnel=""><span class="funnel-bild funnel-alle">Alle</span><b>Standard für alle Reels</b><small>Gilt, wenn ein Reel nichts Eigenes hat</small></button>
        ${data.reel_list.map(r => `<button type="button" role="radio" aria-checked="${selected === r.id}" class="funnel-karte" data-funnel="${esc(r.id)}">
          <span class="funnel-bild">${r.render ? `<video src="${datei(r.render)}#t=0.5" muted playsinline preload="metadata"></video>` : frame(r)}</span>
          <b>${esc(r.titel)}</b><small>${(r.keywords || []).length ? "Keyword " + esc(r.keywords.join(", ")) : "kein Keyword"} · ${r.link ? "Link gesetzt" : "Link fehlt"}</small></button>`).join("")}
      </div></div></div>
    <form id="funnel-form" class="funnel-form">
      <div class="funnel-kopf"><h2>${esc(titel)}</h2>${selected ? `<label class="funnel-check"><input type="checkbox" name="active"${own.active !== false ? " checked" : ""}> Funnel für dieses Reel aktiv</label>` : ""}</div>
      <section class="funnel-schritt"><h3><span>1</span>Ablauf</h3>
        <fieldset class="funnel-feld funnel-ablauf"><legend class="sr">Ablauf</legend>
        ${[["adaptive", "Standard: jeweils fehlende Angabe (Follow oder E-Mail) abfragen", "Weder Follow noch E-Mail → Follow, dann Link. Follow vorhanden → E-Mail. E-Mail vorhanden → Follow. Beides vorhanden → Link."],
           ["both", "Beides abfragen", "Immer Follow und E-Mail: erst Follow, dann E-Mail (falls noch unbekannt), dann Link."],
           ["follow", "Nur Follow abfragen", "Nur der Follow wird geprüft, E-Mail nie."],
           ["email", "Nur E-Mail abfragen", "Nur die E-Mail wird abgefragt, Follow nie."]].map(([v, l, n]) => `<label class="funnel-option"><input type="radio" name="mode" value="${v}"${(own.mode || base.mode) === v ? " checked" : ""}><span><b>${l}</b><small>${n}</small></span></label>`).join("")}
        </fieldset>
        <fieldset class="funnel-feld funnel-ablauf" id="funnel-reihenfolge" hidden><legend>Reihenfolge bei „Beides abfragen“</legend>
        ${[["follow_first", "Erst Follow, dann E-Mail"], ["email_first", "Erst E-Mail, dann Follow"]].map(([v, l]) => `<label class="funnel-option"><input type="radio" name="order" value="${v}"${(own.order || base.order || "follow_first") === v ? " checked" : ""}><span><b>${l}</b></span></label>`).join("")}
        </fieldset>
      </section>
      <section class="funnel-schritt"><h3><span>2</span>Auslöser: Kommentar</h3>
        ${chipBlock("kw", "Keywords", "Keyword tippen, dann Enter", selected
          ? "Mehrere möglich. Groß- und Kleinschreibung ist egal; bei Wörtern ab fünf Buchstaben wird ein Tippfehler toleriert. Der Kommentar darf nur aus dem Keyword bestehen (3–32 Buchstaben oder Ziffern). Zusätzlich gelten die Standard-Keywords. Leer: Keyword aus der Reel-Caption."
          : "Gelten für alle Reels, zusätzlich zu den Keywords des einzelnen Reels. Groß- und Kleinschreibung ist egal; bei Wörtern ab fünf Buchstaben wird ein Tippfehler toleriert. Der Kommentar darf nur aus dem Keyword bestehen (3–32 Buchstaben oder Ziffern).")}
        ${chipBlock("antwort", "Öffentliche Antworten", "Neue Antwort tippen, dann Enter", `Der Bot antwortet unter dem Kommentar. Eine Variante pro Feld, höchstens acht; er wählt zufällig eine aus.${selected ? " Leer: Standard." : ""}`)}
      </section>
      <section class="funnel-schritt"><h3><span>3</span>Erste DM</h3>
        <p class="funnel-hinweis">${selected ? "Vorgabe ist der Standard. Änderst du einen Text, gilt er nur für dieses Reel; unveränderte Texte folgen weiter dem Standard." : "Diese Texte gelten als Standard für alle Reels."}</p>
        ${txt("intro_text")}${btn("start_button", "Start-Button")}
      </section>
      <section class="funnel-schritt" id="funnel-follow"><h3><span>4</span>Follow-Abfrage</h3>
        ${txt("follow_text")}
        <div class="funnel-grid">${btn("follow_now_button", "Follow-Button")}${btn("follow_button", "Bestätigungs-Button")}</div>
        ${txt("follow_again_text")}
        ${selected ? input("profile_link", "Profil-Link", "Wohin „Follow Now“ führt. Leer: Instagram-Profil des Kanals.") : ""}
      </section>
      <section class="funnel-schritt" id="funnel-email"><h3><span>5</span>E-Mail-Abfrage</h3>
        ${txt("email_text")}${txt("email_again_text")}
      </section>
      <section class="funnel-schritt"><h3><span>6</span>Link-Nachricht</h3>
        <div class="funnel-feld"><span>Link-Nachricht</span>
          <input type="hidden" name="link_text" value="${esc(vorgabe("link_text"))}">
          <div class="funnel-linkzeile"><textarea name="link_vor" rows="1" aria-label="Text vor dem Link">${esc(String(vorgabe("link_text")).split("{link}")[0])}</textarea>
            <span class="funnel-token" title="Platzhalter für den Link, fest eingebaut">{link}</span>
            <textarea name="link_nach" rows="1" aria-label="Text nach dem Link">${esc(String(vorgabe("link_text")).split("{link}").slice(1).join(""))}</textarea></div>
          <small>Der Link wird automatisch bei {link} eingesetzt. {link} bleibt fest; Text davor und danach kannst du frei ändern.</small></div>
        <div class="funnel-link"><div class="funnel-aktionen"><button class="knopf klein" type="button" id="funnel-linkweg">Link entfernen</button></div>
           ${input("link", selected ? "Link für {link}" : "Standard-Link für {link}", selected
             ? "Wird in der Link-Nachricht automatisch anstelle von {link} eingesetzt. HTTPS; leer: Link aus der Reel-Caption, sonst Standard-Link."
             : "Gilt für Reels ohne eigenen Link und ohne Link in der Caption. HTTPS. Meist trägst du den Link je Reel ein (oben ein Reel auswählen).")}</div>
      </section>
      <div class="funnel-actions"><button class="knopf primaer" type="submit">Speichern</button>
        ${selected ? `<button class="knopf" type="button" id="funnel-reset">Reel-Regeln zurücksetzen</button>` : ""}</div>
    </form></div>
    <aside class="funnel-vorschau" aria-label="Vorschau">
      <div class="ig-handy"><div class="ig-kopf">Vorschau · Kommentare</div><div class="ig-chat" id="funnel-kommentare"></div></div>
      <div class="ig-handy"><div class="ig-kopf">Vorschau · DMs</div><div class="ig-chat" id="funnel-dms"></div></div></aside></div>`;
  $$("#funnel-form textarea").forEach(x => { const fit = () => { x.style.height = "auto"; x.style.height = x.scrollHeight + 2 + "px"; }; x.oninput = fit; fit(); });
  $$("button[data-funnel]").forEach(b => b.onclick = () => { S.funnelReel = b.dataset.funnel; keywordFunnelSeite(); });
  $$("a[data-funnel]").forEach(a => a.onclick = e => { e.preventDefault(); S.funnelReel = a.dataset.funnel; keywordFunnelSeite(); window.scrollTo(0, 0); });
  const antworten = chipEditor("antwort", own.public_replies || (selected ? base.public_replies || [] : []), { max: 8 });
  const stichworte = chipEditor("kw", own.keywords || (own.keyword ? [own.keyword] : []), {
    max: 10, norm: x => x.toUpperCase(), check: x => /^[A-Z0-9]{3,32}$/.test(x) ? "" : "Keyword: 3–32 Buchstaben oder Ziffern, ohne Leerzeichen" });
  const zeigeAbschnitte = () => {
    const modus = $("#funnel-form").elements.mode.value;
    $("#funnel-follow").hidden = modus === "email";
    $("#funnel-email").hidden = modus === "follow";
    $("#funnel-reihenfolge").hidden = modus !== "both";
  };
  $$("#funnel-form input[name=mode]").forEach(r => r.onchange = zeigeAbschnitte);
  zeigeAbschnitte();
  const vorschau = () => {
    const f = $("#funnel-form").elements, modus = f.mode.value;
    const wert = (k, fallback = "") => (f[k]?.value || "").trim() || fallback;
    const kw = stichworte.list[0] || (base.keywords || [])[0] || "KEYWORD";
    const antwort = antworten.list[0] || "Check your DMs 📩";
    const link = wert("link") || (selected ? "" : base.link || "") || "https://dein-link.de";
    const bot = (text, knoepfe = []) => `<div class="ig-zeile"><div class="ig-blase ig-bot">${esc(text)}${knoepfe.length ? `<div class="ig-knoepfe">${knoepfe.map(k => `<span>${esc(k)}</span>`).join("")}</div>` : ""}</div></div>`;
    const ich = text => `<div class="ig-zeile ig-rechts"><div class="ig-blase ig-ich">${esc(text)}</div></div>`;
    const marke = text => `<div class="ig-marke">${esc(text)}</div>`;
    const linkText = wert("link_text", "{link}").split("{link}").map(esc).join(`<span class="ig-link">${esc(link)}</span>`);
    const mailZuerst = modus === "both" && f.order.value === "email_first";
    const follow = modus === "email" ? "" : marke(modus === "adaptive" ? "Folgt noch nicht" : modus === "both" ? `Schritt ${mailZuerst ? 2 : 1}: Follow` : "Ablauf: Follow") + bot(wert("follow_text"), [wert("follow_now_button"), wert("follow_button")]) + ich(wert("follow_button"));
    const mail = modus === "follow" ? "" : marke(modus === "adaptive" ? "Folgt schon, aber keine E-Mail bekannt" : modus === "both" ? `Schritt ${mailZuerst ? 1 : 2}: E-Mail` : "Ablauf: E-Mail") + bot(wert("email_text")) + ich("name@example.com");
    const ava = `<img class="ig-ava" src="/datei/gedaechtnis/Kanal/marke/profilbild.png" alt="" onerror="this.onerror=null;this.src='/icons/logo.png'">`;
    const anon = `<span class="ig-ava ig-anon" aria-hidden="true"></span>`;
    $("#funnel-kommentare").innerHTML = `<div class="ig-kommentar">${anon}<div><b>Anonym</b><br>${esc(kw)}</div></div><div class="ig-kommentar ig-antwort">${ava}<div><b>${esc(S.kanal.name || "Kanal")}</b><br>${esc(antwort)}</div></div>`;
    $("#funnel-dms").innerHTML = bot(wert("intro_text"), [wert("start_button")]) + ich(wert("start_button")) + (mailZuerst ? mail + follow : follow + mail)
      + marke("Zum Schluss") + `<div class="ig-zeile"><div class="ig-blase ig-bot">${linkText}</div></div>`;
  };
  funnelRefresh = vorschau;
  $("#funnel-form").addEventListener("input", vorschau);
  $("#funnel-form").addEventListener("change", vorschau);
  vorschau();
  $("#funnel-linkweg").onclick = () => { const f = $("#funnel-form").elements.link; f.value = ""; f.focus(); vorschau(); };
  const baueLinkText = () => { const f = $("#funnel-form").elements; f.link_text.value = f.link_vor.value + "{link}" + f.link_nach.value; };
  $("#funnel-form").addEventListener("input", e => { if (e.target.name === "link_vor" || e.target.name === "link_nach") { baueLinkText(); vorschau(); } });
  $("#funnel-form").onsubmit = async e => {
    e.preventDefault();
    const form = e.currentTarget;
    const settings = { mode: form.elements.mode.value, order: form.elements.order.value };
    if (selected) {
      settings.active = form.elements.active.checked;
      if (form.elements.profile_link.value.trim()) settings.profile_link = form.elements.profile_link.value.trim();
    }
    if (form.elements.link.value.trim()) settings.link = form.elements.link.value.trim();
    else if (!selected) settings.link = null;                               // Standard-Link entfernen
    if (!stichworte.add()) return;
    if (stichworte.list.length) settings.keywords = stichworte.list;
    else if (!selected) settings.keywords = null;                           // Standard-Keywords entfernen
    for (const [key] of [...FUNNEL_TEXT, ...FUNNEL_BUTTONS.map(([k]) => [k])]) {
      const wert = form.elements[key].value.trim();
      if (!selected || (wert && wert !== String(base[key] ?? "").trim())) settings[key] = wert;     // Reel: nur Abweichungen vom Standard
    }
    if (!antworten.add()) return;
    if (antworten.list.length && (!selected || JSON.stringify(antworten.list) !== JSON.stringify(base.public_replies || []))) settings.public_replies = antworten.list;
    try {
      await api(selected ? `/api/dm-funnel/reel/${encodeURIComponent(selected)}` : "/api/dm-funnel/default", settings);
      toast("Funnel-Einstellungen gespeichert."); keywordFunnelSeite();
    } catch (err) { toast(err.message, true); }
  };
  if (selected) $("#funnel-reset").onclick = async () => {
    try { await api(`/api/dm-funnel/reset/${encodeURIComponent(selected)}`, {}); toast("Reel-Regeln zurückgesetzt."); keywordFunnelSeite(); }
    catch (err) { toast(err.message, true); }
  };
}

async function erledigt(cid, danach) {
  try { await api(`/api/kommentar/${encodeURIComponent(cid)}/erledigt`, {}); toast("Als erledigt markiert"); abzeichen(); danach(); }
  catch (e) { toast(e.message, true); }
}

async function kommentareSeite() {
  const d = await api("/api/kommentare");
  const alle = d.kommentare || [];
  const offenEsk = alle.filter(c => c.eskalieren && !c.erledigt);
  const f = S.kom.filter ?? (offenEsk.length ? "eskaliert" : "alle");
  const filter = { eskaliert: c => c.eskalieren && !c.erledigt, alle: () => true, beantwortet: c => c.beantwortet,
    ausgeblendet: c => c.ausblenden, keyword: c => c.dm_gesendet, offen: c => !c.beantwortet && !c.ausblenden && !c.eskalieren };
  const pf = S.kom.plattform || "";
  const proPlattform = Object.fromEntries(Object.keys(PLATTFORM_NAME).map(p => [p, alle.filter(c => c.plattform === p).length]));
  const liste = alle.filter(c => (!pf || c.plattform === pf) && filter[f](c)).sort((a, b) => (b.zeit || "").localeCompare(a.zeit || ""));
  const bot = d.bot || {};
  main.innerHTML = `
    <div class="kopf"><div><h1>Kom<span class="akzent">mentare</span></h1><p class="unter">Was der Bot beantwortet oder ausgeblendet hat und was du selbst entscheiden musst.</p></div>
      <div class="rechts"><a class="knopf" href="#/dm-funnel">DM-Kommentar-Funnel einstellen</a><span class="chip${bot.modus === "live" ? " ok" : bot.modus === "probelauf" ? " warn" : ""}">Bot: ${esc(bot.modus || "aus")}</span>
        ${bot.letzter_lauf ? `<span class="klein muted">letzter Lauf ${zeit(bot.letzter_lauf)}</span>` : ""}</div></div>
    ${botFehlerHtml(d.bot_status, "kommentare:")}${botFehlerHtml(d.bot_status, "keyword_dm:")}
    <div class="filter"><div class="seg" id="kom-seg">${[["eskaliert", `An dich (${offenEsk.length})`], ["alle", "Alle"], ["beantwortet", "Beantwortet"],
      ["ausgeblendet", "Ausgeblendet"], ["keyword", "Keyword-DMs"], ["offen", "Offen"]].map(([w, l]) => `<button data-wert="${w}" aria-pressed="${f === w}">${l}</button>`).join("")}</div>
      <div class="seg" id="kom-pf">${[["", "Alle Plattformen"], ...Object.entries(PLATTFORM_NAME)].map(([w, l]) =>
        `<button data-wert="${w}" aria-pressed="${pf === w}">${pfIcon(w)}${l}${w ? ` <span class="muted">${proPlattform[w]}</span>` : ""}</button>`).join("")}</div></div>
    <div class="panel">${liste.length ? liste.map(kommentarHtml).join("") : alle.length ? leer("Nichts in diesem Filter")
      : leer("Noch keine Kommentare", "Der Kommentar-Bot kommt in Phase 2 (tools/instagram/kommentare.py). Regeln: Wissen → Kanal/Kommentar-Regeln.")}</div>`;
  $("#kom-seg").onclick = e => { const b = e.target.closest("button"); if (b) { S.kom.filter = b.dataset.wert; kommentareSeite(); } };
  $("#kom-pf").onclick = e => { const b = e.target.closest("button"); if (b) { S.kom.plattform = b.dataset.wert; kommentareSeite(); } };
  $$("[data-erledigt]").forEach(b => b.onclick = () => erledigt(b.dataset.erledigt, kommentareSeite));
}

// ---------- DMs ----------
const dmZeit = iso => iso ? zeit(iso) : "";

function dmHtml(c) {
  const nachrichten = (c.nachrichten || []).map(m => `<div class="dm-blase ${m.von === "wir" ? "wir" : "sie"}"><span>${esc(m.text || "(Anhang)")}</span><time class="klein muted">${dmZeit(m.zeit)}</time></div>`).join("");
  return `<article class="dm${c.offen ? " offen" : ""}"><header>
      <b>@${esc(c.user)}</b><span class="klein muted">${pfIcon(c.plattform)}${esc(PLATTFORM_NAME[c.plattform] || c.plattform)}${c.konto ? " · " + esc(c.konto) : ""} · ${dmZeit(c.zeit)}</span>
      ${c.offen ? `<span class="chip akzent">wartet auf Antwort</span>` : c.erledigt ? `<span class="chip">erledigt</span>` : `<span class="chip ok">beantwortet</span>`}
      ${c.offen ? `<button type="button" class="knopf klein rechts" data-dm-erledigt="${esc(c.id)}">erledigt</button>` : ""}</header>
    <div class="dm-verlauf">${nachrichten || `<span class="klein muted">Kein Text abrufbar.</span>`}</div>
    ${c.offen ? dmAntwort(c) : ""}</article>`;
}

// Antwortfeld: Entwurf des Bots vorausgefüllt, gesendet wird erst auf Knopfdruck
function dmAntwort(c) {
  if (c.plattform !== "instagram") return `<p class="klein muted">Bitte direkt in der ${esc(PLATTFORM_NAME[c.plattform] || c.plattform)}-App antworten.</p>`;
  const letzte = [...(c.nachrichten || [])].reverse().find(m => m.von === "user");
  const alt = !letzte || Date.now() - new Date(String(letzte.zeit).replace(/([+-]\d\d)(\d\d)$/, "$1:$2")).getTime() > 24 * 36e5;
  if (alt) return `<p class="klein muted">Das 24-Stunden-Antwortfenster von Instagram ist abgelaufen – bitte in der Instagram-App antworten.</p>`;
  const v = c.vorschlag || {};
  return `<form class="dm-antwort" data-dm-form="${esc(c.id)}">
    ${v.eskalieren ? `<p class="klein"><span class="chip warn">selbst entscheiden</span> ${esc(v.grund || "Kein Entwurf – bitte selbst antworten.")}</p>`
      : v.entwurf ? `<p class="klein muted">Entwurf vom Bot${v.kategorie ? " · " + esc(v.kategorie) : ""} – prüfen, ändern, senden.</p>` : ""}
    <textarea rows="3" maxlength="1000" placeholder="Antwort schreiben …" aria-label="Antwort an @${esc(c.user)}">${esc(v.eskalieren ? "" : v.entwurf || "")}</textarea>
    <div class="dm-aktionen"><button type="submit" class="knopf primaer">Senden</button>
      <button type="button" class="knopf" data-dm-erledigt="${esc(c.id)}">erledigt ohne Antwort</button></div></form>`;
}

function dmVerdrahten(root, danach) {
  root.querySelectorAll("[data-dm-erledigt]").forEach(b => b.onclick = () => dmErledigt(b.dataset.dmErledigt, danach));
  root.querySelectorAll("[data-dm-form]").forEach(f => f.onsubmit = async e => {
    e.preventDefault();
    const text = f.querySelector("textarea").value.trim();
    if (!text) return toast("Bitte erst eine Antwort schreiben.", true);
    f.querySelectorAll("button").forEach(b => { b.disabled = true; });
    try { await api(`/api/dm/${encodeURIComponent(f.dataset.dmForm)}/antworten`, { text }); toast("Antwort gesendet."); abzeichen(); }
    catch (err) { toast(err.message, true); }
    danach();
  });
}

async function dmErledigt(id, danach) {
  try { await api(`/api/dm/${encodeURIComponent(id)}/erledigt`, {}); toast("Als erledigt markiert"); abzeichen(); }
  catch (e) { toast(e.message, true); }
  danach();
}

async function dmsSeite() {
  const d = await api("/api/dms");
  const alle = d.konversationen || [];
  const f = S.dm.filter ?? (alle.some(c => c.offen) ? "offen" : "alle");
  const filter = { offen: c => c.offen, alle: () => true, beantwortet: c => !c.offen };
  const pf = S.dm.plattform || "";
  const proPlattform = Object.fromEntries(Object.keys(PLATTFORM_NAME).map(p => [p, alle.filter(c => c.plattform === p).length]));
  const liste = alle.filter(c => (!pf || c.plattform === pf) && filter[f](c)).sort((a, b) => (b.zeit || "").localeCompare(a.zeit || ""));
  const offenAnz = alle.filter(c => c.offen).length;
  const quellen = Object.entries(d.quellen || {}).filter(([p]) => !pf || p === pf);
  const status = quellen.map(([p, q]) => `<div class="dm-quelle${q.ok ? "" : " aus"}">${pfIcon(p)}<b>${esc(PLATTFORM_NAME[p] || p)}</b>
      ${q.ok ? `<span class="chip ok">verbunden</span><span class="klein muted">Stand ${dmZeit(q.stand)}</span>`
        : `<span class="chip ${q.nicht_angebunden ? "" : "bad"}">${q.nicht_angebunden ? "nicht angebunden" : "Fehler"}</span><span class="klein muted">${esc(q.hinweis || "")}</span>`}</div>`).join("");
  main.innerHTML = `
    <div class="kopf"><div><h1>D<span class="akzent">Ms</span></h1><p class="unter">Instagram-DMs mit Entwürfen; andere Plattformen zeigen ihren Anbindungsstatus. Du prüfst und sendest jede Antwort selbst.</p></div>
      <div class="rechts"><button type="button" class="knopf" id="dm-neu">aktualisieren</button>
        ${d.stand ? `<span class="klein muted">Stand ${dmZeit(d.stand)}</span>` : ""}</div></div>
    ${botFehlerHtml(d.bot_status, "dms:")}
    <div class="filter"><div class="seg" id="dm-seg">${[["offen", `Warten auf Antwort (${offenAnz})`], ["alle", "Alle"], ["beantwortet", "Beantwortet"]]
      .map(([w, l]) => `<button data-wert="${w}" aria-pressed="${f === w}">${l}</button>`).join("")}</div>
      <div class="seg" id="dm-pf">${[["", "Alle Plattformen"], ...Object.entries(PLATTFORM_NAME).filter(([p]) => ["instagram", "tiktok", "youtube", "facebook"].includes(p))].map(([w, l]) =>
        `<button data-wert="${w}" aria-pressed="${pf === w}">${pfIcon(w)}${l}${w ? ` <span class="muted">${proPlattform[w]}</span>` : ""}</button>`).join("")}</div></div>
    ${status ? `<div class="panel dm-quellen">${status}</div>` : ""}
    <div class="panel">${liste.length ? liste.map(dmHtml).join("") : alle.length ? leer("Nichts in diesem Filter")
      : leer("Noch keine Nachrichten", "Sobald dir jemand schreibt, erscheint es hier (wird alle 15 Minuten geholt).")}</div>`;
  $("#dm-seg").onclick = e => { const b = e.target.closest("button"); if (b) { S.dm.filter = b.dataset.wert; dmsSeite(); } };
  $("#dm-pf").onclick = e => { const b = e.target.closest("button"); if (b) { S.dm.plattform = b.dataset.wert; dmsSeite(); } };
  dmVerdrahten(main, dmsSeite);
  $("#dm-neu").onclick = async e => {
    e.currentTarget.disabled = true; e.currentTarget.textContent = "holt …";
    try { await api("/api/dms/aktualisieren", {}); toast("DMs aktualisiert."); abzeichen(); } catch (err) { toast(err.message, true); }
    dmsSeite();
  };
}

// ---------- Wissen ----------
async function wissenSeite(pfad) {
  const { notizen } = await api("/api/gedaechtnis");
  pfad = pfad || "README.md";
  const notiz = await api("/api/gedaechtnis/datei?pfad=" + encodeURIComponent(pfad));
  const ordner = pfad.includes("/") ? pfad.slice(0, pfad.lastIndexOf("/")) : "";
  const gruppen = {};
  for (const n of notizen) (gruppen[n.ordner === "." ? "" : n.ordner] ??= []).push(n);
  const baum = Object.keys(gruppen).sort().map(g => `<h3>${esc(g || "Start")}</h3>${gruppen[g].map(n =>
    `<a href="#/wissen/${encodeURI(n.pfad)}"${n.pfad === pfad ? ' aria-current="page"' : ""}>${esc(n.name === "README" ? "Übersicht" : n.name)}</a>`).join("")}`).join("");
  const html = md(notiz.text, {
    wiki: ziel => {
      const z = ziel.split("#")[0].replace(/\.md$/, "");
      const treffer = notizen.find(n => n.pfad === z + ".md") || notizen.find(n => n.name === z.split("/").pop());
      return treffer ? treffer.pfad : z + ".md";
    },
    link: href => {
      if (href.startsWith("#")) return href;
      const p = pfadVerbinden(ordner, href.split("#")[0]);
      return p.endsWith(".md") ? "#/wissen/" + encodeURI(p) : datei("gedaechtnis/" + p);
    },
    bild: src => /^https?:/.test(src) ? src : datei("gedaechtnis/" + pfadVerbinden(ordner, src)),
  });
  const n = notizen.find(x => x.pfad === pfad);
  main.innerHTML = `
    <div class="kopf"><div><h1>Wis<span class="akzent">sen</span></h1><p class="unter">Gedächtnis des Kanals, dazu die Abläufe (Skills) und Agenten. Agenten pflegen es, hier liest du mit.</p></div></div>
    <div class="wissen"><nav class="baum">${baum}</nav>
      <article class="panel notiz"><p class="klein muted mono" style="margin:0 0 12px">${esc(notiz.quelle || pfad)}${notiz.quelle ? " · nur lesen – Änderungen sagst du mir im Chat" : ""}${n ? " · geändert " + zeit(n.geaendert) : ""}</p>
        <div class="text">${html}</div></article></div>`;
}

// ---------- Bibliothek ----------
let bibDaten = null;

const ARTEN = [
  { id: "bild", key: "images", name: "Bild", info: "Foto, Freisteller oder Grafik", endungen: ["png", "jpg", "jpeg"] },
  { id: "sfx", key: "sfx", name: "Soundeffekt", info: "kurzer Klang: Whoosh, Klick, Pop", endungen: ["wav", "mp3", "m4a", "ogg"] },
  { id: "musik", key: "musik", name: "Musik", info: "Musikbett oder Loop", endungen: ["mp3", "wav", "m4a", "ogg"] },
  { id: "clip", key: "clips", name: "Clip", info: "kurzes Video", endungen: ["mp4", "mov", "webm"] },
];
const ROLLEN = [
  { id: "object", name: "Objekt, freigestellt", info: "Gegenstand ohne Hintergrund", frei: true },
  { id: "photo", name: "Vollbild-Foto", info: "füllt das ganze Bild", frei: false },
  { id: "feed", name: "Feed-Foto", info: "im Handy-Feed oder an der Wand", frei: false },
  { id: "portrait", name: "Person, freigestellt", info: "nie als Kanalgesicht", frei: true },
];
const HERKUNFT = [
  { id: "eigen", name: "Eigene Aufnahme", quelle: "eigene Aufnahme (Nutzer)", lizenz: "eigenes Werk – alle Rechte beim Kanal" },
  { id: "flow", name: "KI · Google Flow", quelle: "Google Flow (Konto des Nutzers)", lizenz: "KI-generiert – Google-Flow-Nutzungsbedingungen", prompt: true },
  { id: "pixabay", name: "Pixabay", quelle: "Pixabay", lizenz: "Pixabay Content License", credit: true },
  { id: "pexels", name: "Pexels", quelle: "Pexels", lizenz: "Pexels License", credit: true },
  { id: "freesound", name: "Freesound (CC0)", quelle: "Freesound", lizenz: "CC0 1.0", credit: true },
  { id: "ccby", name: "CC BY (Nachweis nötig)", quelle: "", lizenz: "CC BY 4.0", credit: true, pflicht: true,
    hinweis: "Urheber + Lizenz auf Englisch eintragen, z. B. „Photo: Jane Doe, CC BY 2.0“ – wird im Video klein unten eingeblendet." },
  { id: "andere", name: "Andere …", quelle: "", lizenz: "", credit: true, hinweis: "Braucht das Bild einen Nachweis, trage ihn bei Urheber ein – er erscheint dann klein unten im Video." },
];
const endungVon = name => name.split(".").pop().toLowerCase();
const artVorschlag = name => {
  const e = endungVon(name);
  return e === "wav" ? "sfx" : (ARTEN.find(a => a.endungen.includes(e)) || {}).id;
};
const idAus = name => name.replace(/\.[^.]+$/, "").toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue")
  .replace(/ß/g, "ss").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "datei";

async function bibliothekSeite() {
  bibDaten = await api("/api/bibliothek");
  if (!S.kanal.saeulen) S.kanal = (await api("/api/uebersicht")).kanal || {};
  const f = S.bib;
  const seg = (feld, werte) => `<div class="seg" data-feld="${feld}" role="group">${werte.map(([w, l]) =>
    `<button type="button" data-wert="${w}" aria-pressed="${f[feld] === w}">${l}</button>`).join("")}</div>`;
  main.innerHTML = `
    <div class="kopf"><div><h1>Biblio<span class="akzent">thek</span></h1><p class="unter">Wiederverwendbare Bilder, SFX, Musik und Clips – Kanal (bibliothek/) und Format (The-PsychNote-Kit).</p></div>
      <div class="rechts"><button class="knopf primaer" id="up-auf">${icon("upload")} Hochladen</button></div></div>
    <div class="filter">
      <input type="search" id="bib-q" placeholder="Suchen: ID, Schlagwort, Prompt …" aria-label="Bibliothek durchsuchen" value="${esc(f.q)}">
      ${seg("art", [["", "Alles"], ["images", "Bilder"], ["sfx", "SFX"], ["musik", "Musik"], ["clips", "Clips"]])}
      ${seg("quelle", [["", "Beide"], ["kanal", "Kanal"], ["format", "Format"]])}
      <select id="bib-saeule" aria-label="Säule"><option value="">Alle Säulen</option>${(S.kanal.saeulen || []).map(s =>
        `<option value="${esc(s.id)}"${f.saeule === s.id ? " selected" : ""}>${esc(s.name)}</option>`).join("")}</select>
      <span class="klein muted" id="bib-zahl" aria-live="polite"></span>
    </div>
    <div class="kacheln" id="bib-liste"></div>
    <dialog class="dlg upload-dlg" id="up" aria-labelledby="up-titel"></dialog>`;
  $("#up-auf").onclick = uploadOeffnen;
  $("#bib-q").oninput = e => { f.q = e.target.value; bibListe(); };
  $("#bib-saeule").onchange = e => { f.saeule = e.target.value; bibListe(); };
  $$(".seg[data-feld]").forEach(s => s.onclick = e => {
    const b = e.target.closest("button");
    if (!b) return;
    f[s.dataset.feld] = b.dataset.wert;
    $$("button", s).forEach(x => x.setAttribute("aria-pressed", x === b));
    bibListe();
  });
  bibListe();
}

function bibListe() {
  const f = S.bib;
  const q = f.q.trim().toLowerCase();
  const liste = bibDaten.eintraege.filter(e => (!f.art || e.art === f.art) && (!f.quelle || e.quelle_lib === f.quelle)
    && (!f.saeule || (e.saeulen || []).includes(f.saeule))
    && (!q || [e.id, e.prompt, ...(e.tags || [])].some(x => (x || "").toLowerCase().includes(q))))
    .sort((a, b) => (b.added || "").localeCompare(a.added || ""));
  $("#bib-zahl").textContent = `${liste.length} von ${bibDaten.eintraege.length}`;
  $("#bib-liste").innerHTML = liste.length ? liste.map(e => {
    const medium = !e.pfad ? `<span class="klein muted">Datei fehlt</span>`
      : e.art === "images" ? `<img src="${datei(e.pfad)}" alt="${esc(e.id)}" loading="lazy" data-gross>`
      : e.art === "clips" ? `<video src="${datei(e.pfad)}" preload="none" controls muted></video>`
      : `<span class="art-symbol">${icon(e.art === "sfx" ? "sfx" : "musik")}<span class="mono klein">${e.duration ? zahl(e.duration) + " s" : ""}</span></span>`;
    const ton = e.pfad && (e.art === "sfx" || e.art === "musik") ? `<audio controls preload="none" src="${datei(e.pfad)}" aria-label="${esc(e.id)} anhören"></audio>` : "";
    const used = e.used_in?.length ? `<span>verwendet in ${e.used_in.map(r => `<a href="#/reel/${encodeURIComponent(r)}">${esc(r.slice(11) || r)}</a>`).join(", ")}</span>` : "";
    return `<div class="kachel"><div class="bild">${medium}</div><div class="info"><b>${esc(e.id)}</b>${ton}
      ${e.saeulen?.length ? `<div class="tags">${e.saeulen.map(saeuleChip).join(" ")}</div>` : ""}
      <div class="tags">${(e.tags || []).map(t => `<span>${esc(t)}</span>`).join("")}</div>
      <span class="muted">${esc(e.quelle_lib === "kanal" ? "Kanal" : "Format")}${e.role ? " · " + esc(e.role) : ""}${e.cutout ? " · Freisteller" : ""}</span>${used}</div></div>`;
  }).join("") : leer("Nichts gefunden", "");
}

// Upload: Dateien sammeln, je Datei Art, Einsatz, Beschreibung und Herkunft wählen, dann über bibliothek.py aufnehmen
const U = { dateien: [], i: -1, art: null, rolle: "object", herkunft: "eigen", quelle: HERKUNFT[0].quelle, lizenz: HERKUNFT[0].lizenz,
  credit: "", prompt: "", id: "", tags: [], saeulen: [], fertig: 0 };

function uploadOeffnen() {
  const dlg = $("#up");
  U.dateien = []; U.i = -1; U.fertig = 0;
  dlg.innerHTML = `
    <form id="up-form" novalidate>
      <header class="dlg-kopf"><h2 id="up-titel">In die Bibliothek aufnehmen</h2><span class="klein muted" id="up-zaehler"></span>
        <button type="button" class="knopf-icon" id="up-zu" aria-label="Fenster schließen">${icon("x")}</button></header>
      <div class="up-raster" id="up-raster">
        <aside class="up-links">
          <label class="ablage" id="up-ablage"><input type="file" id="up-datei" multiple accept=".png,.jpg,.jpeg,.wav,.mp3,.m4a,.ogg,.mp4,.mov,.webm">
            ${icon("upload", "gross")}<span><b>Dateien hierher ziehen</b><br>oder klicken zum Auswählen</span>
            <span class="klein muted">Bilder PNG/JPG · Audio WAV/MP3/M4A/OGG · Video MP4/MOV/WEBM · mehrere auf einmal</span></label>
          <ol class="up-liste" id="up-liste" aria-label="Ausgewählte Dateien"></ol>
        </aside>
        <section class="up-rechts" id="up-rechts" aria-live="polite"></section>
      </div>
      <footer class="dlg-fuss" id="up-fuss" hidden>
        <button type="button" class="knopf" id="up-skip">Überspringen</button>
        <button type="submit" class="knopf primaer" id="up-los">${icon("check")} Aufnehmen</button>
      </footer>
    </form>`;
  const datei = $("#up-datei"), ablage = $("#up-ablage");
  datei.onchange = () => { dateienDazu([...datei.files]); datei.value = ""; };
  ablage.ondragover = e => { e.preventDefault(); ablage.classList.add("drueber"); };
  ablage.ondragleave = () => ablage.classList.remove("drueber");
  ablage.ondrop = e => { e.preventDefault(); ablage.classList.remove("drueber"); dateienDazu([...e.dataTransfer.files]); };
  $("#up-zu").onclick = () => uploadSchliessen();
  dlg.oncancel = e => { e.preventDefault(); uploadSchliessen(); };
  $("#up-skip").onclick = () => { U.dateien[U.i].status = "uebersprungen"; naechsteDatei(); };
  $("#up-form").onsubmit = e => { e.preventDefault(); aufnehmen(); };
  upListe();
  upRechts();
  dlg.showModal();
}

function uploadSchliessen() {
  const offenN = U.dateien.filter(d => d.status === "offen").length;
  if (offenN && !confirm(`${offenN} Datei${offenN > 1 ? "en sind" : " ist"} noch nicht aufgenommen. Trotzdem schließen?`)) return;
  U.dateien.forEach(d => URL.revokeObjectURL(d.url));
  $("#up").close();
  if (U.fertig) bibListe();
}

function dateienDazu(files) {
  const neu = files.filter(f => artVorschlag(f.name));
  const falsch = files.length - neu.length;
  if (falsch) toast(`${falsch} Datei${falsch > 1 ? "en" : ""} übergangen – Typ wird nicht unterstützt`, true);
  for (const f of neu) U.dateien.push({ file: f, url: URL.createObjectURL(f), status: "offen" });
  if (U.i < 0 || U.dateien[U.i]?.status !== "offen") naechsteDatei();
  else upListe();
}

function dateiWaehlen(i) {
  U.i = i;
  const d = U.dateien[i];
  U.art = artVorschlag(d.file.name);
  U.id = idAus(d.file.name);
  U.tags = [];
  U.prompt = "";
  if (U.art === "bild") U.rolle = endungVon(d.file.name) === "png" ? "object" : "photo";
  upListe();
  upRechts();
}

function naechsteDatei() {
  const i = U.dateien.findIndex(d => d.status === "offen");
  if (i >= 0) return dateiWaehlen(i);
  U.i = -1;
  upListe();
  upRechts();
}

function upListe() {
  const symbol = { offen: "", fertig: icon("check", "ok"), fehler: icon("alert", "bad"), uebersprungen: `<span class="klein muted">übersprungen</span>` };
  $("#up-liste").innerHTML = U.dateien.map((d, i) => {
    const vorschau = artVorschlag(d.file.name) === "bild" ? `<img src="${d.url}" alt="">` : icon(artVorschlag(d.file.name) === "clip" ? "clip" : "musik");
    return `<li><button type="button" data-i="${i}" aria-current="${i === U.i}" ${d.status === "fertig" ? "disabled" : ""}>
      <span class="mini-vorschau">${vorschau}</span><span class="name">${esc(d.file.name)}</span>${symbol[d.status] || ""}</button></li>`;
  }).join("");
  $$("#up-liste [data-i]").forEach(b => b.onclick = () => dateiWaehlen(Number(b.dataset.i)));
  const n = U.dateien.length;
  $("#up-zaehler").textContent = n ? `${U.dateien.filter(d => d.status !== "offen").length} von ${n} erledigt` : "";
  $("#up-raster").classList.toggle("ohne", !n);
}

function upRechts() {
  const box = $("#up-rechts"), fuss = $("#up-fuss");
  if (U.i < 0) {
    fuss.hidden = true;
    box.innerHTML = U.fertig ? `<div class="up-fertig">${icon("check", "gross ok")}<h3>${U.fertig} Datei${U.fertig > 1 ? "en" : ""} in der Bibliothek</h3>
        <p class="muted">Sie sind sofort in shots.json nutzbar. Weitere Dateien links hinzufügen oder fertig.</p>
        <button type="button" class="knopf primaer" id="up-fertig">Fertig</button></div>` : "";
    $("#up-fertig")?.addEventListener("click", uploadSchliessen);
    return;
  }
  fuss.hidden = false;
  const d = U.dateien[U.i];
  const endung = endungVon(d.file.name);
  const art = ARTEN.find(a => a.id === U.art);
  const her = HERKUNFT.find(h => h.id === U.herkunft);
  const vorschau = U.art === "bild" ? `<img src="${d.url}" alt="Vorschau">`
    : U.art === "clip" ? `<video src="${d.url}" controls muted></video>` : `<audio src="${d.url}" controls></audio>`;
  const karten = (name, liste, wert, aus = () => false) => liste.map(x => `
    <label class="wahl${aus(x) ? " aus" : ""}"><input type="radio" name="${name}" value="${x.id}"${x.id === wert ? " checked" : ""}${aus(x) ? " disabled" : ""}>
      ${x.icon ? icon(x.icon) : ""}<b>${esc(x.name)}</b><span>${esc(aus(x) ? `passt nicht zu .${endung}` : x.info)}</span></label>`).join("");
  const haeufig = {};
  for (const e of bibDaten.eintraege) if (!art || e.art === art.key) for (const t of e.tags || []) haeufig[t] = (haeufig[t] || 0) + 1;
  const vorschlaege = Object.entries(haeufig).filter(([t]) => !U.tags.includes(t)).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([t]) => t);

  box.innerHTML = `
    <div class="up-vorschau">${vorschau}<div><b>${esc(d.file.name)}</b><span class="klein muted">${d.file.size < 1048576 ? zahl(Math.max(1, d.file.size / 1024)) + " KB" : zahl(d.file.size / 1048576) + " MB"}</span>
      ${d.fehler ? `<p class="fehlertext" role="alert">${icon("alert")} ${esc(d.fehler)}</p>` : ""}</div></div>
    <fieldset><legend><span class="schritt-nr">1</span> Was ist das?</legend>
      <div class="wahlen vier">${karten("art", ARTEN.map(a => ({ ...a, icon: { bild: "bild", sfx: "sfx", musik: "musik", clip: "clip" }[a.id] })), U.art, a => !a.endungen.includes(endung))}</div></fieldset>
    ${U.art === "bild" ? `<fieldset><legend><span class="schritt-nr">2</span> Wie wird es im Video eingesetzt?</legend>
      <div class="wahlen vier">${karten("rolle", ROLLEN, U.rolle)}</div></fieldset>` : ""}
    <fieldset><legend><span class="schritt-nr">${U.art === "bild" ? 3 : 2}</span> Beschreiben</legend>
      <div class="feld"><label for="up-id">Name (ID)</label>
        <input id="up-id" value="${esc(U.id)}" autocomplete="off" spellcheck="false" aria-describedby="up-id-hilfe">
        <span class="hilfe" id="up-id-hilfe">So heißt die Datei in shots.json. Nur a–z, 0–9 und _.</span></div>
      <div class="feld"><label for="up-tag">Schlagworte</label>
        <div class="tag-feld" id="up-tagfeld">${U.tags.map(t => `<span class="tag-chip">${esc(t)}<button type="button" data-weg-tag="${esc(t)}" aria-label="${esc(t)} entfernen">${icon("x")}</button></span>`).join("")}
          <input id="up-tag" placeholder="${U.tags.length ? "" : "z. B. handy, nacht"}" autocomplete="off" aria-describedby="up-tag-hilfe"></div>
        <span class="hilfe" id="up-tag-hilfe">Enter oder Komma fügt ein Wort hinzu. Danach suchen die Agenten.</span>
        ${vorschlaege.length ? `<div class="vorschlaege"><span class="klein muted">Häufig:</span>${vorschlaege.map(t => `<button type="button" class="chip-knopf" data-tag="${esc(t)}">${icon("plus")}${esc(t)}</button>`).join("")}</div>` : ""}</div>
      <div class="feld"><span class="label" id="up-saeulen-l">Passt zu Säule <span class="muted">(optional)</span></span>
        <div class="vorschlaege" role="group" aria-labelledby="up-saeulen-l">${(S.kanal.saeulen || []).map(s =>
          `<button type="button" class="chip-knopf saeule-knopf" data-saeule="${esc(s.id)}" aria-pressed="${U.saeulen.includes(s.id)}" style="--s:${SAEULE_FARBE[s.id] || "var(--muted)"}">${esc(s.name)}</button>`).join("")}</div></div>
    </fieldset>
    <fieldset><legend><span class="schritt-nr">${U.art === "bild" ? 4 : 3}</span> Herkunft</legend>
      <div class="vorschlaege" role="radiogroup" aria-label="Herkunft">${HERKUNFT.map(h =>
        `<button type="button" class="chip-knopf" role="radio" data-herkunft="${h.id}" aria-checked="${h.id === U.herkunft}">${esc(h.name)}</button>`).join("")}</div>
      ${her.hinweis ? `<p class="hilfe" style="margin:0">${esc(her.hinweis)}</p>` : ""}
      <div class="felder-2">
        <div class="feld"><label for="up-quelle">Quelle</label><input id="up-quelle" value="${esc(U.quelle)}"></div>
        <div class="feld"><label for="up-lizenz">Lizenz</label><input id="up-lizenz" value="${esc(U.lizenz)}"></div>
        ${her.credit ? `<div class="feld breit"><label for="up-credit">Bildnachweis <span class="muted">${her.pflicht ? "(Pflicht – erscheint klein unten im Video)" : "(nur bei Lizenzpflicht – erscheint dann klein unten im Video)"}</span></label><input id="up-credit" value="${esc(U.credit)}"></div>` : ""}
        ${her.prompt ? `<div class="feld breit"><label for="up-prompt">Prompt <span class="muted">(optional – hilft, ähnliche Bilder neu zu erzeugen)</span></label><textarea id="up-prompt" rows="2">${esc(U.prompt)}</textarea></div>` : ""}
      </div>
    </fieldset>`;

  $$('input[name="art"]', box).forEach(r => r.onchange = () => { U.art = r.value; upRechts(); });
  $$('input[name="rolle"]', box).forEach(r => r.onchange = () => { U.rolle = r.value; });
  $("#up-id").oninput = e => { U.id = e.target.value.trim(); idPruefen(); };
  const tag = $("#up-tag");
  const tagDazu = text => {
    for (const t of text.split(",").map(x => x.trim().toLowerCase()).filter(Boolean)) if (!U.tags.includes(t)) U.tags.push(t);
    upRechts();
    $("#up-tag").focus();
  };
  tag.onkeydown = e => {
    if ((e.key === "Enter" || e.key === ",") && tag.value.trim()) { e.preventDefault(); tagDazu(tag.value); }
    else if (e.key === "Enter") e.preventDefault();
    else if (e.key === "Backspace" && !tag.value && U.tags.length) { U.tags.pop(); upRechts(); $("#up-tag").focus(); }
  };
  tag.onblur = () => { if (tag.value.trim()) { U.tags.push(...tag.value.split(",").map(x => x.trim().toLowerCase()).filter(t => t && !U.tags.includes(t))); tag.value = ""; } };
  $("#up-tagfeld").onclick = e => { if (e.target.id === "up-tagfeld") tag.focus(); };
  $$("[data-weg-tag]", box).forEach(b => b.onclick = () => { U.tags = U.tags.filter(t => t !== b.dataset.wegTag); upRechts(); });
  $$("[data-tag]", box).forEach(b => b.onclick = () => tagDazu(b.dataset.tag));
  $$("[data-saeule]", box).forEach(b => b.onclick = () => {
    const s = b.dataset.saeule;
    U.saeulen = U.saeulen.includes(s) ? U.saeulen.filter(x => x !== s) : [...U.saeulen, s];
    b.setAttribute("aria-pressed", U.saeulen.includes(s));
  });
  $$("[data-herkunft]", box).forEach(b => b.onclick = () => {
    const h = HERKUNFT.find(x => x.id === b.dataset.herkunft);
    U.herkunft = h.id; U.quelle = h.quelle; U.lizenz = h.lizenz;
    upRechts();
    $(h.id === "andere" ? "#up-quelle" : `[data-herkunft="${h.id}"]`).focus();
  });
  for (const [sel, feld] of [["#up-quelle", "quelle"], ["#up-lizenz", "lizenz"], ["#up-credit", "credit"], ["#up-prompt", "prompt"]])
    if ($(sel, box)) $(sel, box).oninput = e => { U[feld] = e.target.value; };
  idPruefen();
}

function idPruefen() {
  const el = $("#up-id"), hilfe = $("#up-id-hilfe");
  if (!el) return true;
  const vergeben = bibDaten.eintraege.some(e => e.id === U.id);
  const fehler = !U.id ? "Bitte einen Namen eingeben." : !/^[a-z0-9_]+$/.test(U.id) ? "Nur a–z, 0–9 und _ – keine Leerzeichen oder Umlaute."
    : vergeben ? `„${U.id}“ gibt es schon – bitte anders nennen.` : "";
  el.setAttribute("aria-invalid", !!fehler);
  hilfe.textContent = fehler || "So heißt die Datei in shots.json. Nur a–z, 0–9 und _.";
  hilfe.classList.toggle("fehlertext", !!fehler);
  return !fehler;
}

async function aufnehmen() {
  const d = U.dateien[U.i];
  const tagRest = $("#up-tag")?.value.trim();
  if (tagRest) { U.tags.push(...tagRest.split(",").map(x => x.trim().toLowerCase()).filter(t => t && !U.tags.includes(t))); }
  const pruef = [
    [!U.art, "#up-rechts input[name=art]", "Bitte wählen, was die Datei ist."],
    [!idPruefen(), "#up-id", null],
    [!U.tags.length, "#up-tag", "Mindestens ein Schlagwort, damit die Agenten die Datei finden."],
    [!U.quelle.trim(), "#up-quelle", "Quelle fehlt."],
    [!U.lizenz.trim(), "#up-lizenz", "Lizenz fehlt – ohne Lizenz darf die Datei nicht ins Video."],
    [HERKUNFT.find(h => h.id === U.herkunft)?.pflicht && !U.credit.trim(), "#up-credit", "Bei CC BY ist der Bildnachweis Pflicht."],
  ].find(([bad]) => bad);
  if (pruef) {
    if (pruef[2]) toast(pruef[2], true);
    if (pruef[1] === "#up-tag") upRechts();
    $(pruef[1])?.focus();
    return;
  }
  const rolle = ROLLEN.find(r => r.id === U.rolle);
  const q = new URLSearchParams({ name: d.file.name, art: U.art, id: U.id, tags: U.tags.join(","), quelle: U.quelle.trim(),
    lizenz: U.lizenz.trim(), prompt: U.prompt.trim(), credit: U.credit.trim(), saeulen: U.saeulen.join(","),
    rolle: U.art === "bild" ? U.rolle : "", freisteller: U.art === "bild" && rolle?.frei ? "1" : "" });
  const knopf = $("#up-los");
  knopf.disabled = true;
  knopf.innerHTML = `<span class="spinner" aria-hidden="true"></span> Wird aufgenommen …`;
  try {
    const r = await fetch("/api/bibliothek/upload?" + q, { method: "POST", body: d.file });
    const antwort = await r.json().catch(() => ({}));
    if (!r.ok || antwort.ok === false) throw new Error(antwort.fehler || `HTTP ${r.status}`);
    bibDaten = antwort.bibliothek;
    d.status = "fertig";
    d.fehler = null;
    U.fertig++;
    toast(`${U.id} ist in der Bibliothek`);
    naechsteDatei();
  } catch (err) {
    d.fehler = err.message.replace(/^FEHLER:\s*/, "");
    upRechts();
    $(".up-vorschau .fehlertext")?.scrollIntoView({ block: "nearest" });
  } finally {
    knopf.disabled = false;
    knopf.innerHTML = `${icon("check")} Aufnehmen`;
  }
}

// ---------- Kalender ----------
const p2 = n => String(n).padStart(2, "0");
const tagIso = d => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
const kw = d => {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  return Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
};
const tagLang = iso => new Date(iso + "T12:00").toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
let kal = null;

async function kalenderSeite(monat) {
  const [pl, rs, th] = await Promise.all([api("/api/plan"), api("/api/reels"), api("/api/themen")]);
  const cr = await Promise.race([api("/api/credits").catch(() => null), new Promise(r => setTimeout(() => r(null), 1500))]);
  if (!S.kanal.saeulen) S.kanal = (await api("/api/uebersicht")).kanal || {};
  const heute = new Date();
  const [jahr, mon] = /^\d{4}-\d\d$/.test(monat || "") ? monat.split("-").map(Number) : [heute.getFullYear(), heute.getMonth() + 1];
  kal = { plan: pl.eintraege, reels: rs.reels, themen: th.themen, monat: `${jahr}-${p2(mon)}` };
  const themaVon = id => kal.themen.find(t => t.id === id);
  const reelVon = id => kal.reels.find(r => r.id === id);
  const ziel = S.kanal.takt?.videos_pro_woche || 3;
  const postzeit = S.kanal.takt?.postzeit || "19:00";

  const proTag = {};
  const dazu = (tag, html, art) => (proTag[tag] ??= []).push({ html, art });
  for (const r of kal.reels) {
    const wann = r.post?.gepostet_am || r.post?.geplant_fuer;
    if (!wann) continue;
    const live = !!r.post?.gepostet_am;
    dazu(wann.slice(0, 10), `<a class="ev ${live ? "live" : "post"}" href="#/reel/${encodeURIComponent(r.id)}" title="${esc(r.titel)} – ${live ? "gepostet" : "geplant"} ${zeit(wann)}">${live ? icon("check") : `<span class="mono">${esc(wann.slice(11, 16))}</span>`}<span>${esc(r.titel)}</span></a>`, "post");
  }
  for (const e of kal.plan) {
    const t = themaVon(e.thema_id), r = reelVon(e.reel_id || t?.reel);
    if (r?.post?.geplant_fuer || r?.post?.gepostet_am) continue;          // steht schon als Post im Kalender
    const titel = r?.titel || t?.titel_en || e.notiz || e.thema_id;
    const farbe = SAEULE_FARBE[saeule(t?.saeule || r?.saeule).id] || "var(--muted)";
    dazu(e.datum, `<button type="button" class="ev plan" draggable="true" data-plan="${esc(e.id)}" style="--s:${farbe}"
      title="${esc(titel)}${r ? " · " + esc(STUFE_NAME[r.stufe] || r.stufe) : ""}" aria-label="${esc(titel)} – bearbeiten oder verschieben"><span>${esc(titel)}</span></button>`, "plan");
  }
  if (cr?.daten?.reset) dazu(cr.daten.reset.slice(0, 10), `<span class="ev hinweis" title="ElevenLabs-Credits werden zurückgesetzt">Credits-Reset</span>`, "info");

  const erster = new Date(jahr, mon - 1, 1);
  const start = new Date(erster);
  start.setDate(1 - ((erster.getDay() + 6) % 7));
  const letzter = new Date(jahr, mon, 0);
  const wochen = [];
  for (let d = new Date(start); d <= letzter || d.getDay() !== 1; ) {
    const tage = [];
    for (let k = 0; k < 7; k++, d.setDate(d.getDate() + 1)) tage.push(new Date(d));
    wochen.push(tage);
  }
  const heuteIso = tagIso(heute);
  const vorher = new Date(jahr, mon - 2, 1), nachher = new Date(jahr, mon, 1);
  const monatName = erster.toLocaleDateString("de-DE", { month: "long", year: "numeric" });
  const geplant = new Set(kal.plan.map(e => e.thema_id).filter(Boolean));

  main.innerHTML = `
    <div class="kopf"><div><h1>Kalen<span class="akzent">der</span></h1>
      <p class="unter">Was wann rausgeht. Ziel: ${ziel} Reels pro Woche um ${esc(postzeit)}. Ein Tag im Kalender ist der Wunschtermin bei der Freigabe, /reel nimmt den nächsten Eintrag.</p></div>
      <div class="rechts monat-nav">
        <a class="knopf-icon" href="#/kalender/${vorher.getFullYear()}-${p2(vorher.getMonth() + 1)}" aria-label="Vorheriger Monat">${icon("links")}</a>
        <b class="monat" aria-live="polite">${esc(monatName)}</b>
        <a class="knopf-icon" href="#/kalender/${nachher.getFullYear()}-${p2(nachher.getMonth() + 1)}" aria-label="Nächster Monat">${icon("rechts")}</a>
        <a class="knopf" href="#/kalender">Heute</a></div></div>
    <div class="kal-layout">
      <section class="kal" aria-label="${esc(monatName)}" style="--wochen:${wochen.length}">
        <div class="kal-kopf" aria-hidden="true"><span>KW</span>${["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map(t => `<span>${t}</span>`).join("")}</div>
        ${wochen.map(tage => {
          const n = tage.reduce((a, d) => a + (proTag[tagIso(d)] || []).filter(x => x.art !== "info").length, 0);
          return `<div class="kal-woche"><div class="kw"><b>KW ${kw(tage[0])}</b><span class="chip klein ${n >= ziel ? "ok" : n ? "warn" : ""}" title="${n} von ${ziel} Reels geplant">${n}/${ziel}</span></div>
            ${tage.map(d => {
              const iso = tagIso(d);
              const cls = [d.getMonth() !== mon - 1 && "fremd", iso === heuteIso && "heute", iso < heuteIso && "vorbei", !(proTag[iso] || []).length && "frei"].filter(Boolean).join(" ");
              return `<div class="tag ${cls}" data-datum="${iso}"><div class="tag-kopf"><span class="nr">${iso === heuteIso ? '<span class="sr">Heute, </span>' : ""}<span class="wt">${d.toLocaleDateString("de-DE", { weekday: "short" })}</span>${d.getDate()}${d.getDate() === 1 ? ` <span class="mon">${d.toLocaleDateString("de-DE", { month: "short" }).replace(".", "")}</span>` : ""}</span>
                ${iso >= heuteIso ? `<button type="button" class="tag-plus" data-plus="${iso}" aria-label="Am ${tagLang(iso)} etwas einplanen">${icon("plus")}</button>` : ""}</div>
                <div class="tag-inhalt">${(proTag[iso] || []).map(x => x.html).join("")}</div></div>`;
            }).join("")}</div>`;
        }).join("")}
      </section>
      <aside class="panel kal-seite"><h2>Einplanen</h2>
        <p class="klein muted">Thema auf einen Tag ziehen – oder beim Tag auf ${icon("plus")} klicken. Eingeplantes lässt sich verschieben.</p>
        <input type="search" id="kal-q" placeholder="Thema suchen …" aria-label="Thema suchen">
        <div class="kal-ideen" id="kal-ideen"></div></aside>
    </div>
    <dialog class="dlg kal-dlg" id="kal-dlg" aria-labelledby="kal-dlg-titel"></dialog>`;

  const ideenListe = () => {
    const q = ($("#kal-q").value || "").trim().toLowerCase();
    const liste = kal.themen.filter(t => t.status === "idee" && !geplant.has(t.id)
      && (!q || [t.id, t.titel_en, t.titel_de, t.prinzip].some(x => (x || "").toLowerCase().includes(q))))
      .sort((a, b) => (a.prio ?? 9) - (b.prio ?? 9) || a.id.localeCompare(b.id)).slice(0, 40);
    $("#kal-ideen").innerHTML = liste.map(t => `<div class="idee" draggable="true" data-thema="${esc(t.id)}">
      <div class="titel">${esc(t.titel_en)}</div><div class="zeile">${saeuleChip(t.saeule)}${t.prio ? `<span class="chip akzent">${PRIO_NAME[t.prio]}</span>` : ""}<span class="mono">${esc(t.id)}</span></div></div>`).join("")
      || leer("Keine offenen Themen", "");
    $$("#kal-ideen [data-thema]").forEach(el => el.ondragstart = e => e.dataTransfer.setData("text/plain", "thema:" + el.dataset.thema));
  };
  $("#kal-q").oninput = ideenListe;
  ideenListe();

  $$(".ev.plan").forEach(el => {
    el.ondragstart = e => e.dataTransfer.setData("text/plain", "plan:" + el.dataset.plan);
    el.onclick = () => planDialog(el.dataset.plan);
  });
  $$("[data-plus]").forEach(b => b.onclick = () => einplanDialog(b.dataset.plus));
  $$(".tag").forEach(t => {
    t.ondragover = e => { if (t.dataset.datum >= heuteIso) { e.preventDefault(); t.classList.add("ziel"); } };
    t.ondragleave = () => t.classList.remove("ziel");
    t.ondrop = async e => {
      e.preventDefault();
      t.classList.remove("ziel");
      const [art, id] = e.dataTransfer.getData("text/plain").split(":");
      try {
        if (art === "thema") await api("/api/plan", { datum: t.dataset.datum, thema_id: id });
        else if (art === "plan") await api(`/api/plan/${encodeURIComponent(id)}`, { datum: t.dataset.datum });
        else return;
        toast(`${art === "plan" ? "Verschoben" : "Eingeplant"}: ${tagLang(t.dataset.datum)}`);
        kalenderSeite(kal.monat);
      } catch (err) { toast(err.message, true); }
    };
  });
}

function einplanDialog(iso) {
  const dlg = $("#kal-dlg");
  const geplant = new Set(kal.plan.map(e => e.thema_id).filter(Boolean));
  dlg.innerHTML = `<form id="kal-form">
    <header class="dlg-kopf"><h2 id="kal-dlg-titel">Einplanen am ${esc(tagLang(iso))}</h2>
      <button type="button" class="knopf-icon" data-zu aria-label="Schließen">${icon("x")}</button></header>
    <div class="dlg-inhalt">
      <input type="search" id="kal-dlg-q" placeholder="Thema suchen …" aria-label="Thema suchen">
      <div class="wahl-liste" id="kal-dlg-liste" role="listbox" aria-label="Themen"></div>
      <div class="feld"><label for="kal-notiz">… oder eine freie Notiz</label>
        <div class="zeile-feld"><input id="kal-notiz" placeholder="z. B. Serie Teil 2, Reaktion auf Kommentar"><button type="submit" class="knopf">Notiz einplanen</button></div></div>
    </div></form>`;
  const liste = () => {
    const q = $("#kal-dlg-q").value.trim().toLowerCase();
    const th = kal.themen.filter(t => t.status === "idee" && !geplant.has(t.id)
      && (!q || [t.id, t.titel_en, t.titel_de, t.prinzip].some(x => (x || "").toLowerCase().includes(q))))
      .sort((a, b) => (a.prio ?? 9) - (b.prio ?? 9) || a.id.localeCompare(b.id)).slice(0, 30);
    $("#kal-dlg-liste").innerHTML = th.map(t => `<button type="button" role="option" data-thema="${esc(t.id)}">
      <span><b>${esc(t.titel_en)}</b><br><span class="klein muted">${esc(t.titel_de)}</span></span>${saeuleChip(t.saeule)}</button>`).join("") || leer("Nichts gefunden", "");
    $$("#kal-dlg-liste [data-thema]").forEach(b => b.onclick = () => speichern({ thema_id: b.dataset.thema }));
  };
  const speichern = async daten => {
    try { await api("/api/plan", { datum: iso, ...daten }); dlg.close(); toast(`Eingeplant: ${tagLang(iso)}`); kalenderSeite(kal.monat); }
    catch (err) { toast(err.message, true); }
  };
  $("#kal-dlg-q").oninput = liste;
  $("#kal-form").onsubmit = e => { e.preventDefault(); const n = $("#kal-notiz").value.trim(); if (n) speichern({ notiz: n }); else $("#kal-notiz").focus(); };
  $("[data-zu]", dlg).onclick = () => dlg.close();
  liste();
  dlg.showModal();
  $("#kal-dlg-q").focus();
}

function planDialog(pid) {
  const dlg = $("#kal-dlg");
  const e = kal.plan.find(x => x.id === pid);
  const t = kal.themen.find(x => x.id === e.thema_id);
  const rid = e.reel_id || t?.reel;
  dlg.innerHTML = `<form id="kal-form">
    <header class="dlg-kopf"><h2 id="kal-dlg-titel">${esc(t?.titel_en || e.notiz || e.id)}</h2>
      <button type="button" class="knopf-icon" data-zu aria-label="Schließen">${icon("x")}</button></header>
    <div class="dlg-inhalt">
      ${t ? `<p class="muted" style="margin:0">${esc(t.titel_de)}</p><div class="zeile-chips">${saeuleChip(t.saeule)}<span class="muted klein">${esc(t.prinzip || "")}</span><span class="mono klein">${esc(t.id)}</span></div>` : ""}
      <div class="felder-2">
        <div class="feld"><label for="kal-datum">Tag</label><input type="date" id="kal-datum" value="${esc(e.datum)}" min="${tagIso(new Date())}"></div>
        <div class="feld"><label for="kal-notiz">Notiz</label><input id="kal-notiz" value="${esc(e.notiz || "")}"></div>
      </div>
      ${rid ? `<a class="knopf" href="#/reel/${encodeURIComponent(rid)}">Zum Reel ${icon("rechts")}</a>` : ""}
    </div>
    <footer class="dlg-fuss"><button type="button" class="knopf gefahr" id="kal-weg">${icon("x")} Aus dem Kalender nehmen</button>
      <button type="submit" class="knopf primaer">Speichern</button></footer></form>`;
  $("[data-zu]", dlg).onclick = () => dlg.close();
  $("#kal-weg").onclick = async () => {
    try { await api(`/api/plan/${encodeURIComponent(pid)}`, { loeschen: true }); dlg.close(); toast("Aus dem Kalender genommen"); kalenderSeite(kal.monat); }
    catch (err) { toast(err.message, true); }
  };
  $("#kal-form").onsubmit = async ev => {
    ev.preventDefault();
    try {
      await api(`/api/plan/${encodeURIComponent(pid)}`, { datum: $("#kal-datum").value, notiz: $("#kal-notiz").value });
      dlg.close(); toast("Gespeichert"); kalenderSeite(kal.monat);
    } catch (err) { toast(err.message, true); }
  };
  dlg.showModal();
}

// ---------- Router, Abzeichen, Lightbox ----------
async function abzeichen(u) {
  try {
    u ??= await api("/api/uebersicht");
    S.kanal = u.kanal || S.kanal;
    if (S.kanal.theme?.accent) document.documentElement.style.setProperty("--accent", S.kanal.theme.accent);
    const setze = (sel, n) => { const el = $(sel); el.hidden = !n; el.textContent = n || ""; };
    setze("#zahl-freigabe", u.warten.length);
    setze("#zahl-eskalation", u.bot?.eskalationen);
    setze("#zahl-dm", u.dms?.offen);
    setze("#zahl-mehr", (u.bot?.eskalationen || 0) + (u.dms?.offen || 0));
    document.title = offen(S.kanal.name) ? "Cockpit" : `${S.kanal.name} · Cockpit`;
  } catch { /* Abzeichen sind nur Beiwerk */ }
}

const ANSICHTEN = { "": uebersicht, pipeline, reel: reelSeite, kalender: kalenderSeite, themen: themenSeite, kommentare: kommentareSeite,
  "dm-funnel": keywordFunnelSeite, dms: dmsSeite,
  wissen: wissenSeite, bibliothek: bibliothekSeite };

async function route(fokus = false) {
  const h = decodeURI(location.hash.slice(1) || "/");
  const [, bereich = "", ...rest] = h.split("/");
  const nav = bereich === "" ? "uebersicht" : bereich === "reel" ? "pipeline" : bereich;
  document.body.dataset.ansicht = bereich || "uebersicht";
  $$(".rail a.nav").forEach(a => a.dataset.bereich === nav ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  $("#mehr").classList.toggle("aktiv", ["kommentare", "dms", "wissen", "bibliothek", "dm-funnel"].includes(nav));
  $("#mehr-menue").hidden = true;
  $("#mehr").setAttribute("aria-expanded", "false");
  const ansicht = ANSICHTEN[bereich];
  main.setAttribute("aria-busy", "true");
  const langsam = setTimeout(() => main.classList.add("laedt"), 150);
  try {
    if (!ansicht) throw new Error(`Seite „${bereich}“ gibt es nicht`);
    await ansicht(rest.join("/"));
  } catch (e) {
    main.innerHTML = `<a class="zurueck" href="#/">← Übersicht</a>${leer("Das ging schief", esc(e.message))}`;
  } finally {
    clearTimeout(langsam);
    main.classList.remove("laedt");
    main.removeAttribute("aria-busy");
    if (fokus) main.focus({ preventScroll: true });
  }
}

document.addEventListener("click", e => {
  const img = e.target.closest("img[data-gross]");
  if (img) {
    const box = document.createElement("div");
    box.className = "lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", "Bild groß – Klick oder Esc schließt");
    box.innerHTML = `<img src="${img.src}" alt="">`;
    box.onclick = () => box.remove();
    document.body.append(box);
  }
  if (!e.target.closest("#mehr, #mehr-menue")) { $("#mehr-menue").hidden = true; $("#mehr").setAttribute("aria-expanded", "false"); }
});
document.addEventListener("keydown", e => { if (e.key === "Escape") { $(".lightbox")?.remove(); $("#mehr-menue").hidden = true; } });
document.addEventListener("visibilitychange", () => { if (!document.hidden) abzeichen(); });
$(".sprunglink").onclick = e => { e.preventDefault(); main.focus(); };
$("#mehr").onclick = () => {
  const m = $("#mehr-menue");
  m.hidden = !m.hidden;
  $("#mehr").setAttribute("aria-expanded", String(!m.hidden));
};

window.addEventListener("hashchange", () => { route(true); window.scrollTo(0, 0); });
abzeichen().then(() => route());
