const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const { join } = require("node:path");

const execFileAsync = promisify(execFile);

module.exports = async function afterPack(context) {
  if (
    context.electronPlatformName !== "darwin" ||
    process.env.CSC_IDENTITY_AUTO_DISCOVERY !== "false"
  ) {
    return;
  }

  const appPath = join(
    context.appOutDir,
    `${context.packager.appInfo.productFilename}.app`,
  );
  await execFileAsync("/usr/bin/codesign", [
    "--force",
    "--deep",
    "--sign",
    "-",
    appPath,
  ]);
};
