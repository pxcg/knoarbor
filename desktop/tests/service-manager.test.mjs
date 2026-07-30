import assert from "node:assert/strict";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
  unlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:http";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/main/service-manager.ts", import.meta.url),
  "utf-8",
);
const maxBytes = Number(
  source.match(/SERVICE_LOG_MAX_BYTES = ([\d_]+);/)?.[1].replaceAll("_", ""),
);
const backupCount = Number(
  source.match(/SERVICE_LOG_BACKUP_COUNT = (\d+);/)?.[1],
);
const functionSource = source
  .slice(
    source.indexOf("function appendBoundedServiceLog"),
    source.indexOf("\n\nasync function findAvailablePort"),
  )
  .replace("path: string, text: string", "path, text")
  .replace("): void", ")");
const appendBoundedServiceLog = new Function(
  "Buffer",
  "appendFileSync",
  "existsSync",
  "renameSync",
  "statSync",
  "unlinkSync",
  "SERVICE_LOG_MAX_BYTES",
  "SERVICE_LOG_BACKUP_COUNT",
  `${functionSource}; return appendBoundedServiceLog;`,
)(
  Buffer,
  appendFileSync,
  existsSync,
  renameSync,
  statSync,
  unlinkSync,
  maxBytes,
  backupCount,
);

test("service output is bounded and rotated without dropping the newest chunk", async () => {
  const root = await mkdtemp(join(tmpdir(), "knoarbor-service-log-"));
  const logPath = join(root, "service.log");
  mkdirSync(root, { recursive: true });
  try {
    for (let index = 0; index < backupCount + 3; index += 1) {
      appendBoundedServiceLog(logPath, `${index}:`.padEnd(maxBytes, "x"));
    }

    assert.equal(statSync(logPath).size, maxBytes);
    assert.equal(readFileSync(logPath, "utf-8").slice(0, 2), `${backupCount + 2}:`);
    for (let index = 1; index <= backupCount; index += 1) {
      assert.ok(existsSync(`${logPath}.${index}`));
      assert.ok(statSync(`${logPath}.${index}`).size <= maxBytes);
    }
    assert.equal(existsSync(`${logPath}.${backupCount + 1}`), false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("health probing uses a direct socket even when global fetch is unusable", async () => {
  const healthProbeSource = readFileSync(
    new URL("../src/main/health-probe.ts", import.meta.url),
    "utf-8",
  );
  const transpiled = ts.transpileModule(healthProbeSource, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const module = await import(
    `data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`
  );
  const server = createServer((request, response) => {
    if (request.url === "/health") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end('{"status":"ok"}');
      return;
    }
    response.writeHead(404);
    response.end();
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("system proxy intercepted fetch");
  };
  try {
    const result = await module.waitForHealth(
      `http://127.0.0.1:${address.port}/health`,
      2_000,
    );
    assert.deepEqual(result, { healthy: true });
  } finally {
    globalThis.fetch = originalFetch;
    await new Promise((resolve, reject) =>
      server.close((error) => error ? reject(error) : resolve()),
    );
  }
});

