// Notfallordner-Briefkasten (Cloudflare Worker + KV)
//
// Speichert nur verschlüsselte Einsendungen. Lesen kann sie ausschließlich das Programm des Beraters
// mit seinem privaten Schlüssel. Nach dem Abholen werden sie gelöscht, spätestens nach 30 Tagen.
//
// Benötigt:  KV-Namespace gebunden als  NFO
//            Geheimnis (Secret)          ADMIN_TOKEN  (Zugangsschlüssel für das Programm)

import FORMULAR_HTML from "./formular.html";

const TAG = 24 * 3600;
const EINLADUNG_TTL = 60 * TAG; // unbenutzte Links verfallen nach 60 Tagen
const EINGANG_TTL = 30 * TAG; // nicht abgeholte Einsendungen verfallen nach 30 Tagen
const MAX_GROESSE = 64 * 1024;
const ID = /^[A-Za-z0-9_-]{16,64}$/;

const SICHERHEIT = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Cache-Control": "no-store",
};

const json = (daten, status = 200) =>
  new Response(JSON.stringify(daten), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...SICHERHEIT } });

async function gleich(a, b) {
  // Vergleich in konstanter Zeit über Hashes
  const enc = new TextEncoder();
  const [x, y] = await Promise.all([crypto.subtle.digest("SHA-256", enc.encode(a)), crypto.subtle.digest("SHA-256", enc.encode(b))]);
  const ax = new Uint8Array(x), ay = new Uint8Array(y);
  let d = 0;
  for (let i = 0; i < ax.length; i++) d |= ax[i] ^ ay[i];
  return d === 0;
}

async function istAdmin(req, env) {
  const h = req.headers.get("Authorization") || "";
  const token = h.startsWith("Bearer ") ? h.slice(7) : "";
  if (!env.ADMIN_TOKEN || env.ADMIN_TOKEN.length < 24 || !token) return false;
  return gleich(token, env.ADMIN_TOKEN);
}

// Verzeichnis der wartenden Einsendungen (spart teure list()-Abfragen im kostenlosen Tarif)
async function verzeichnis(env) { return (await env.NFO.get("inbox-index", "json")) || []; }
async function verzeichnisSetzen(env, ids) { await env.NFO.put("inbox-index", JSON.stringify([...new Set(ids)])); }

async function leseJson(req) {
  const text = await req.text();
  if (text.length > MAX_GROESSE) throw new Error("zu groß");
  return JSON.parse(text);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    const m = req.method;
    try {
      // ---------- Kundenformular ----------
      let r;
      if (m === "GET" && (r = p.match(/^\/f\/([^/]+)$/))) {
        return new Response(FORMULAR_HTML, {
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            ...SICHERHEIT,
          },
        });
      }
      if (m === "GET" && p === "/") {
        return new Response("Notfallordner-Briefkasten", { headers: { "Content-Type": "text/plain; charset=utf-8", ...SICHERHEIT } });
      }

      // ---------- Öffentliche API für das Formular ----------
      if (m === "GET" && p === "/api/key") {
        const key = await env.NFO.get("key", "json");
        return key ? json({ pub: key.pub, kid: key.kid, berater: key.berater || {} }) : json({ error: "kein Schlüssel" }, 503);
      }
      if (m === "GET" && (r = p.match(/^\/api\/invite\/([^/]+)$/))) {
        if (!ID.test(r[1])) return json({ status: "unbekannt" });
        const inv = await env.NFO.get("invite:" + r[1], "json");
        return json({ status: inv ? inv.status : "unbekannt" });
      }
      if (m === "POST" && (r = p.match(/^\/api\/submit\/([^/]+)$/))) {
        const id = r[1];
        if (!ID.test(id)) return json({ error: "Link ungültig" }, 404);
        const inv = await env.NFO.get("invite:" + id, "json");
        if (!inv) return json({ error: "Link ungültig oder abgelaufen" }, 404);
        if (inv.status !== "offen") return json({ error: "Dieser Link wurde bereits verwendet" }, 409);
        let u;
        try { u = await leseJson(req); } catch (e) { return json({ error: "Daten unlesbar" }, 400); }
        if (!u || u.v !== 1 || typeof u.key !== "string" || typeof u.iv !== "string" || typeof u.data !== "string") {
          return json({ error: "Daten unvollständig" }, 400);
        }
        const eintrag = { id, received: Date.now(), envelope: { v: 1, kid: String(u.kid || ""), key: u.key, iv: u.iv, data: u.data } };
        await env.NFO.put("inbox:" + id, JSON.stringify(eintrag), { expirationTtl: EINGANG_TTL });
        await env.NFO.put("invite:" + id, JSON.stringify({ ...inv, status: "verwendet", used: Date.now() }), { expirationTtl: EINGANG_TTL });
        await verzeichnisSetzen(env, [...(await verzeichnis(env)), id]);
        return json({ ok: true });
      }

      // ---------- Verwaltung (nur mit Zugangsschlüssel) ----------
      if (p.startsWith("/api/admin/")) {
        if (!(await istAdmin(req, env))) return json({ error: "nicht berechtigt" }, 401);
        if (m === "GET" && p === "/api/admin/ping") {
          const key = await env.NFO.get("key", "json");
          return json({ ok: true, kid: key ? key.kid : null });
        }
        if (m === "PUT" && p === "/api/admin/key") {
          const d = await leseJson(req);
          if (typeof d.pub !== "string" || d.pub.length < 100 || typeof d.kid !== "string") return json({ error: "Schlüssel ungültig" }, 400);
          const s = (v, n) => String(v || "").slice(0, n);
          const ber = d.berater || {};
          const berater = { name: s(ber.name, 120), mail: s(ber.mail, 120), tel: s(ber.tel, 60), datenschutz: s(ber.datenschutz, 2000) };
          await env.NFO.put("key", JSON.stringify({ pub: d.pub, kid: d.kid, berater, set: Date.now() }));
          return json({ ok: true });
        }
        if (m === "POST" && p === "/api/admin/invite") {
          const d = await leseJson(req);
          if (!ID.test(d.id || "")) return json({ error: "ID ungültig" }, 400);
          await env.NFO.put("invite:" + d.id, JSON.stringify({ status: "offen", created: Date.now() }), { expirationTtl: EINLADUNG_TTL });
          return json({ ok: true });
        }
        if (m === "DELETE" && (r = p.match(/^\/api\/admin\/invite\/([^/]+)$/))) {
          await env.NFO.delete("invite:" + r[1]);
          return json({ ok: true });
        }
        if (m === "GET" && p === "/api/admin/inbox") {
          const idx = await verzeichnis(env);
          let ids = idx;
          if (url.searchParams.get("voll") === "1") {
            // gelegentlich vollständig nachsehen, falls das Verzeichnis etwas verpasst hat
            const list = await env.NFO.list({ prefix: "inbox:" });
            ids = [...new Set([...idx, ...list.keys.map((k) => k.name.slice(6))])];
          }
          const items = [], da = [];
          for (const id of ids) {
            const v = await env.NFO.get("inbox:" + id, "json");
            if (v) { items.push(v); da.push(id); }
          }
          if (da.length !== idx.length || da.some((x) => !idx.includes(x))) await verzeichnisSetzen(env, da);
          return json({ items });
        }
        if (m === "DELETE" && (r = p.match(/^\/api\/admin\/inbox\/([^/]+)$/))) {
          await env.NFO.delete("inbox:" + r[1]);
          await verzeichnisSetzen(env, (await verzeichnis(env)).filter((x) => x !== r[1]));
          return json({ ok: true });
        }
      }
      return json({ error: "nicht gefunden" }, 404);
    } catch (e) {
      return json({ error: "Fehler im Briefkasten" }, 500);
    }
  },
};
