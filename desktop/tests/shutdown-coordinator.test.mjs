import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/main/shutdown-coordinator.ts", import.meta.url),
  "utf-8",
);
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { coordinateManagedServiceShutdown } = await import(
  `data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`
);

test("desktop quit waits for the managed service and resumes exactly once", async () => {
  let beforeQuit;
  let quitCalls = 0;
  let resolveStop;
  let stopCalls = 0;
  const application = {
    on(event, listener) {
      assert.equal(event, "before-quit");
      beforeQuit = listener;
    },
    quit() {
      quitCalls += 1;
    },
  };
  const service = {
    stop() {
      stopCalls += 1;
      return new Promise((resolve) => {
        resolveStop = resolve;
      });
    },
  };
  coordinateManagedServiceShutdown(application, service, assert.fail);

  let prevented = 0;
  const event = {
    preventDefault() {
      prevented += 1;
    },
  };
  beforeQuit(event);
  beforeQuit(event);

  assert.equal(stopCalls, 1);
  assert.equal(quitCalls, 0);
  assert.equal(prevented, 2);

  resolveStop();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(quitCalls, 1);

  beforeQuit(event);
  assert.equal(prevented, 2);
  assert.equal(stopCalls, 1);
  assert.equal(quitCalls, 1);
});

test("desktop still finishes quitting when service shutdown reports an error", async () => {
  let beforeQuit;
  let quitCalls = 0;
  const errors = [];
  const application = {
    on(_event, listener) {
      beforeQuit = listener;
    },
    quit() {
      quitCalls += 1;
    },
  };
  coordinateManagedServiceShutdown(
    application,
    {
      async stop() {
        throw new Error("stop failed");
      },
    },
    (error) => errors.push(error),
  );

  beforeQuit({ preventDefault() {} });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(errors.length, 1);
  assert.equal(quitCalls, 1);
});

