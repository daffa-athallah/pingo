// Recall's thin HTTP face for the unmodified H-MEM reference implementation in ./src.
//
//   node engines/hmem/server.ts                (Node 22.18+ runs TypeScript directly; no install is needed to run it)
//
// It adds no memory logic: every route calls the engine (add, query, feedback, ledger) and returns its own output.
// Listens on 127.0.0.1 only. Environment: HMEM_PORT (8300), HMEM_PERSIST_DIR (JSON + ledger.jsonl; in-memory when unset),
// HMEM_ALLOW_RESET=1 enables POST /reset (used only by the resettable demo workspace).

import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { HMEM } from "./src/index.ts";
import type { AddInput } from "./src/memoryStore.ts";
import type { FeedbackKind, MemoryRecord } from "./src/types.ts";

const PORT = Number(process.env.HMEM_PORT ?? 8300);
const HOST = "127.0.0.1";
const PERSIST = process.env.HMEM_PERSIST_DIR || undefined;
const ALLOW_RESET = process.env.HMEM_ALLOW_RESET === "1";
const MAX_BODY = 1_000_000;

let hmem = new HMEM({ actor: "recall", persistDir: PERSIST });

function view(m: MemoryRecord) {
  return {
    id: m.id, content: m.content, type: m.type, layer: m.layer, confidence: m.confidence, source: m.source, provenance: m.provenance,
    domain: m.domain, namespace: m.namespace, entities: m.entities, tags: m.tags, accessCount: m.accessCount,
    supersedes: m.supersedes ?? null, supersededBy: m.supersededBy ?? null, derivedFrom: m.derivedFrom ?? [],
  };
}

function send(res: http.ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(text) });
  res.end(text);
}

async function readJson(req: http.IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY) throw Object.assign(new Error("request body too large"), { status: 413 });
    chunks.push(chunk as Buffer);
  }
  try {
    const value = JSON.parse(Buffer.concat(chunks).toString("utf-8") || "{}");
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error();
    return value as Record<string, unknown>;
  } catch {
    throw Object.assign(new Error("body must be a JSON object"), { status: 400 });
  }
}

const str = (v: unknown, name: string): string => {
  if (typeof v !== "string" || !v.trim()) throw Object.assign(new Error(`${name} must be a non-empty string`), { status: 422 });
  return v;
};
const strings = (v: unknown): string[] | undefined => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : undefined);

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${HOST}`);
  try {
    if (req.method === "GET" && url.pathname === "/health") {
      return send(res, 200, { ok: true, engine: "h-mem", records: hmem.store.all().length, ledger: hmem.ledger.all().length, persistent: Boolean(PERSIST) });
    }
    if (req.method === "GET" && url.pathname === "/refs") {
      // Every provenance reference already stored, so a caller can seed idempotently.
      return send(res, 200, { refs: hmem.store.all().flatMap((m) => m.provenance.refs ?? []) });
    }
    if (req.method === "GET" && url.pathname === "/ledger") {
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") ?? 50) || 50, 1), 500);
      const memoryId = url.searchParams.get("memoryId");
      const entries = memoryId ? hmem.ledger.history(memoryId) : hmem.ledger.all();
      return send(res, 200, { total: entries.length, stats: hmem.ledger.stats(), entries: entries.slice(-limit) });
    }
    if (req.method === "POST" && url.pathname === "/memories") {
      const b = await readJson(req);
      const input: AddInput = {
        content: str(b.content, "content"), source: str(b.source, "source"), type: b.type as AddInput["type"], layer: b.layer as AddInput["layer"],
        tags: strings(b.tags), confidence: typeof b.confidence === "number" ? b.confidence : undefined,
        provenance: b.provenance as AddInput["provenance"], supersedes: typeof b.supersedes === "string" ? b.supersedes : undefined,
        derivedFrom: strings(b.derivedFrom), goalRunId: typeof b.goalRunId === "string" ? b.goalRunId : undefined,
      };
      return send(res, 201, view(hmem.add(input)));
    }
    if (req.method === "POST" && url.pathname === "/query") {
      const b = await readJson(req);
      const result = hmem.query(str(b.query, "query"), {
        topN: typeof b.topN === "number" ? b.topN : undefined, threshold: typeof b.threshold === "number" ? b.threshold : undefined,
      });
      return send(res, 200, { memories: result.memories.map((r) => ({ ...view(r.memory), relevance: r.relevance })), trace: result.trace, context: result.context });
    }
    if (req.method === "POST" && url.pathname === "/feedback") {
      const b = await readJson(req);
      hmem.feedback(str(b.memoryId, "memoryId"), str(b.kind, "kind") as FeedbackKind);
      return send(res, 200, { ok: true });
    }
    if (req.method === "POST" && url.pathname === "/reset") {
      if (!ALLOW_RESET) return send(res, 403, { error: "reset is disabled; start with HMEM_ALLOW_RESET=1" });
      if (PERSIST) for (const f of ["state.json", "ledger.jsonl"]) fs.rmSync(path.join(PERSIST, f), { force: true });
      hmem = new HMEM({ actor: "recall", persistDir: PERSIST });
      return send(res, 200, { ok: true, records: 0 });
    }
    return send(res, 404, { error: "not found" });
  } catch (error) {
    const e = error as Error & { status?: number };
    return send(res, e.status ?? 500, { error: e.message });
  }
});

server.listen(PORT, HOST, () => console.log(`h-mem listening on http://${HOST}:${PORT} (${PERSIST ? "persistent" : "in-memory"})`));
