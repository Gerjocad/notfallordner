// Briefkasten lokal starten (zum Testen ohne Cloudflare), mit KV im Arbeitsspeicher.
//   node lokal.mjs [port] [admin-token]
import http from "node:http";
import { pathToFileURL } from "node:url";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const hier = dirname(fileURLToPath(import.meta.url));
const { default: worker } = await import(pathToFileURL(join(hier, "dist", "worker.js")).href);
const port = +(process.argv[2] || 8787);
const token = process.argv[3] || "test-token-0123456789abcdefghij";

const daten = new Map();
const KV = {
  async get(k, typ) { const e = daten.get(k); if (!e || (e.bis && e.bis < Date.now())) return null; return typ === "json" ? JSON.parse(e.v) : e.v; },
  async put(k, v, o = {}) { daten.set(k, { v, bis: o.expirationTtl ? Date.now() + o.expirationTtl * 1000 : 0 }); },
  async delete(k) { daten.delete(k); },
  async list({ prefix }) { return { keys: [...daten.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })) }; },
};
const env = { NFO: KV, ADMIN_TOKEN: token };

http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const body = chunks.length ? Buffer.concat(chunks) : undefined;
  const r = await worker.fetch(new Request(`http://localhost:${port}${req.url}`, { method: req.method, headers: req.headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : body }), env);
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
}).listen(port, "127.0.0.1", () => console.log(`Briefkasten lokal auf http://127.0.0.1:${port}`));
