// Kleiner Markdown-Renderer fürs Cockpit (Gedächtnis-Notizen, Skript, Storyboard, Prüfberichte) – ohne Bibliothek.
// Kann: Frontmatter, Überschriften, Absätze, Listen (auch verschachtelt, Aufgaben), Tabellen, Code, Zitate, Linien,
// fett/kursiv/Code/Links, [[Wikilinks]] (→ #/wissen/<pfad>), Bilder. Der Text wird immer zuerst escaped.

const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function inline(s, opt) {
  const code = [];
  s = esc(s).replace(/`([^`]+)`/g, (_, c) => `\u0000${code.push(c) - 1}\u0000`);
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, src) => `<img alt="${alt}" src="${opt.bild ? opt.bild(src) : src}" loading="lazy">`)
    .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, ziel, txt) => `<a class="wiki" href="#/wissen/${encodeURI((opt.wiki ? opt.wiki(ziel) : ziel))}">${txt || ziel.split("/").pop()}</a>`)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, txt, href) => /^https?:/.test(href)
      ? `<a href="${href}" target="_blank" rel="noopener">${txt}</a>` : `<a href="${opt.link ? opt.link(href) : href}">${txt}</a>`)
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, "$1<em>$2</em>").replace(/(^|[^_\w])_([^_\s][^_]*?)_(?!\w)/g, "$1<em>$2</em>")
    .replace(/⚠/g, '<span class="warn-zeichen" title="umstritten">⚠</span>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${code[i]}</code>`);
}

function zellen(z) {
  return z.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, "|"));
}

export function md(src, opt = {}) {
  let text = String(src ?? "").replace(/\r/g, "");
  let front = "";
  const fm = text.match(/^---\n([\s\S]*?)\n---\n?/);
  if (fm) {
    text = text.slice(fm[0].length);
    const zeilen = fm[1].split("\n").filter(l => /^\w[\w-]*:/.test(l)).map(l => {
      const i = l.indexOf(":");
      return `<dt>${esc(l.slice(0, i))}</dt><dd>${esc(l.slice(i + 1).trim())}</dd>`;
    });
    if (zeilen.length) front = `<dl class="frontmatter">${zeilen.join("")}</dl>`;
  }
  const L = text.split("\n");
  const out = [];
  let i = 0;
  while (i < L.length) {
    const l = L[i];
    if (!l.trim()) { i++; continue; }
    let m;
    if ((m = l.match(/^```(\w*)/))) {
      const buf = [];
      for (i++; i < L.length && !L[i].startsWith("```"); i++) buf.push(L[i]);
      i++;
      out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`);
    } else if ((m = l.match(/^(#{1,6})\s+(.*)$/))) {
      const n = m[1].length, t = m[2].replace(/\s*#+\s*$/, "");
      const id = t.toLowerCase().replace(/[^\wäöüß]+/g, "-").replace(/^-|-$/g, "");
      out.push(`<h${n} id="h-${id}">${inline(t, opt)}</h${n}>`);
      i++;
    } else if (/^(\s*[-*_]){3,}\s*$/.test(l)) {
      out.push("<hr>"); i++;
    } else if (l.trim().startsWith("|") && i + 1 < L.length && /^\s*\|?\s*:?-{2,}/.test(L[i + 1])) {
      const kopf = zellen(l);
      const ausr = zellen(L[i + 1]).map(c => c.endsWith(":") ? (c.startsWith(":") ? "center" : "right") : "");
      i += 2;
      const rows = [];
      while (i < L.length && L[i].trim().startsWith("|")) rows.push(zellen(L[i++]));
      const td = (c, k, tag) => `<${tag}${ausr[k] ? ` style="text-align:${ausr[k]}"` : ""}>${inline(c, opt)}</${tag}>`;
      out.push(`<div class="tabelle"><table><thead><tr>${kopf.map((c, k) => td(c, k, "th")).join("")}</tr></thead><tbody>${
        rows.map(r => `<tr>${kopf.map((_, k) => td(r[k] ?? "", k, "td")).join("")}</tr>`).join("")}</tbody></table></div>`);
    } else if (/^>\s?/.test(l)) {
      const buf = [];
      while (i < L.length && /^>\s?/.test(L[i])) buf.push(L[i++].replace(/^>\s?/, ""));
      out.push(`<blockquote>${md(buf.join("\n"), opt)}</blockquote>`);
    } else if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
      const items = [];
      while (i < L.length && (/^\s*([-*+]|\d+[.)])\s+/.test(L[i]) || (/^\s{2,}\S/.test(L[i]) && items.length))) {
        const z = L[i++];
        const t = z.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if (t) items.push({ tief: Math.floor(t[1].replace(/\t/g, "  ").length / 2), ol: /\d/.test(t[2]), text: t[3] });
        else items[items.length - 1].text += " " + z.trim();
      }
      out.push(liste(items, 0, opt));
    } else {
      const buf = [];
      while (i < L.length && L[i].trim() && !/^(#{1,6}\s|```|>|\s*([-*+]|\d+[.)])\s+|\|)/.test(L[i])) buf.push(L[i++]);
      if (!buf.length) buf.push(L[i++]);
      out.push(`<p>${buf.map(b => inline(b, opt)).join("<br>")}</p>`);
    }
  }
  return front + out.join("\n");
}

function liste(items, tief, opt) {
  if (!items.length) return "";
  const tag = items[0].ol ? "ol" : "ul";
  let html = `<${tag}>`;
  for (let k = 0; k < items.length; k++) {
    const it = items[k];
    if (it.tief > tief) continue;
    const kinder = [];
    for (let j = k + 1; j < items.length && items[j].tief > tief; j++) kinder.push(items[j]);
    let t = it.text, box = "";
    const cb = t.match(/^\[( |x|X)\]\s+/);
    if (cb) { box = `<input type="checkbox" disabled${cb[1] !== " " ? " checked" : ""}> `; t = t.slice(cb[0].length); }
    html += `<li${cb ? ' class="aufgabe"' : ""}>${box}${inline(t, opt)}${kinder.length ? liste(kinder, tief + 1, opt) : ""}</li>`;
  }
  return html + `</${tag}>`;
}

export { esc, inline };
