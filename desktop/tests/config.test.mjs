import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const builderConfig = require("../electron-builder.config.cjs");

test("freezes the first supported desktop installer identity", () => {
  assert.equal(builderConfig.productName, "KnoArbor");
  assert.equal(builderConfig.appId, "ai.knoarbor.desktop");
  assert.deepEqual(
    {
      allowElevation: builderConfig.nsis.allowElevation,
      deleteAppDataOnUninstall: builderConfig.nsis.deleteAppDataOnUninstall,
      guid: builderConfig.nsis.guid,
      include: builderConfig.nsis.include,
      oneClick: builderConfig.nsis.oneClick,
      perMachine: builderConfig.nsis.perMachine,
    },
    {
      allowElevation: false,
      deleteAppDataOnUninstall: false,
      guid: "ai.knoarbor.desktop",
      include: "installer.nsh",
      oneClick: true,
      perMachine: false,
    },
  );
});

test("Windows uninstall stops only the managed service owned by this installation", () => {
  const installer = readFileSync(
    new URL("../installer.nsh", import.meta.url),
    "utf-8",
  );
  assert.match(installer, /!macro customCheckAppRunning/);
  assert.match(installer, /KNOARBOR_INSTALL_APP_PATH/);
  assert.match(installer, /KNOARBOR_INSTALL_SERVICE_PATH/);
  assert.match(installer, /\\resources\\service\\knoar-service\.exe/);
  assert.match(installer, /\$\$_\.ExecutablePath/);
  assert.match(installer, /\[StringComparison\]::OrdinalIgnoreCase/);
  assert.doesNotMatch(installer, /taskkill\s+\/IM/i);
  assert.equal(builderConfig.nsis.deleteAppDataOnUninstall, false);
});

test("interactive uninstall offers local-data removal without touching external vaults", () => {
  const installer = readFileSync(
    new URL("../installer.nsh", import.meta.url),
    "utf-8",
  );
  assert.match(installer, /\$\{IfNot\} \$\{isUpdated\}/);
  assert.match(
    installer,
    /!ifdef BUILD_UNINSTALLER\s+Var \/GLOBAL KnoArborDeleteLocalData\s+!endif/,
  );
  assert.match(installer, /\/SD IDNO/);
  assert.match(installer, /RMDir \/r "\$LOCALAPPDATA\\KnoArbor"/);
  assert.doesNotMatch(installer, /external.*RMDir|RMDir.*external/i);
});
