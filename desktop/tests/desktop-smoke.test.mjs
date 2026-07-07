import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import {
  buildDesktopDiagnostics,
  getDesktopEnvironment,
} from "../out/main/diagnostics.js";

const desktopRoot = dirname(dirname(fileURLToPath(import.meta.url)));

function assertFile(path) {
  assert.equal(existsSync(path), true, `${path} should exist`);
  assert.equal(statSync(path).isFile(), true, `${path} should be a file`);
}

describe("desktop startup smoke", () => {
  it("emits the main, preload, shell, and copied renderer resources", () => {
    const mainBundle = join(desktopRoot, "out/main/index.js");
    assertFile(mainBundle);
    assertFile(join(desktopRoot, "out/preload/index.mjs"));
    assertFile(join(desktopRoot, "out/renderer/index.html"));
    assertFile(join(desktopRoot, "resources/renderer/index.html"));

    const mainSource = readFileSync(mainBundle, "utf-8");
    assert.match(mainSource, /registerRendererProtocol/);
    assert.match(mainSource, /serviceManager\.start/);
    assert.match(mainSource, /createMainWindow/);
  });
});

describe("desktop diagnostics smoke", () => {
  it("builds managed diagnostics with app data and service log paths", () => {
    const environment = {
      isDesktopApp: true,
      platform: "darwin",
      versions: {
        chrome: "1",
        electron: "2",
        node: "3",
      },
    };
    const serviceState = {
      endpoint: "http://127.0.0.1:8765",
      logPath: "/tmp/KnoArbor/logs/service.log",
      mode: "managed",
      status: "healthy",
    };
    const diagnostics = buildDesktopDiagnostics({
      config: {
        appServer: {
          appDataRoot: "/tmp/KnoArbor",
          configPath: "/tmp/KnoArbor/config.yaml",
          host: "127.0.0.1",
          mode: "managed",
          port: 8765,
          rendererAssetsRoot: join(desktopRoot, "resources/renderer"),
          serviceArgs: [],
          serviceCommand: "uv",
          serviceCwd: desktopRoot,
        },
        appUserModelId: "com.knoarbor.desktop",
        rendererAssetsRoot: join(desktopRoot, "resources/renderer"),
      },
      desktopLogPath: "/tmp/KnoArbor/logs/desktop.log",
      environment,
      serviceState,
    });

    assert.deepEqual(diagnostics.appData, {
      configPath: "/tmp/KnoArbor/config.yaml",
      root: "/tmp/KnoArbor",
    });
    assert.equal(diagnostics.environment, environment);
    assert.equal(diagnostics.logs.desktopLogPath, "/tmp/KnoArbor/logs/desktop.log");
    assert.equal(diagnostics.logs.serviceLogPath, "/tmp/KnoArbor/logs/service.log");
    assert.equal(diagnostics.service, serviceState);
  });

  it("omits app data for external service mode", () => {
    const diagnostics = buildDesktopDiagnostics({
      config: {
        appServer: {
          mode: "external",
          url: "http://127.0.0.1:8000",
        },
        appUserModelId: "com.knoarbor.desktop",
        rendererAssetsRoot: join(desktopRoot, "resources/renderer"),
      },
      serviceState: {
        endpoint: "http://127.0.0.1:8000",
        mode: "external",
        status: "healthy",
      },
    });

    assert.equal(diagnostics.appData, undefined);
    assert.equal(diagnostics.environment.isDesktopApp, true);
    assert.equal(diagnostics.service.mode, "external");
  });

  it("reports the current Node runtime in the desktop environment payload", () => {
    const environment = getDesktopEnvironment();

    assert.equal(environment.isDesktopApp, true);
    assert.equal(environment.platform, process.platform);
    assert.equal(environment.versions.node, process.versions.node);
    assert.equal(typeof environment.versions.electron, "string");
  });
});
