import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const builderConfig = require(resolve(desktopRoot, "electron-builder.config.cjs"));
const ico = await readFile(resolve(desktopRoot, "resources/icons/icon.ico"));
const windowsPng = await readFile(resolve(desktopRoot, "resources/icons/icon-windows.png"));

assert.equal(builderConfig.win.icon, "resources/icons/icon.ico");
assert.ok(
  builderConfig.extraResources.some(
    (entry) => entry.from === "resources/icons" && entry.to === "icons",
  ),
  "Windows runtime icons must be copied into the packaged resources directory.",
);

assert.deepEqual(ico.subarray(0, 4), Buffer.from([0, 0, 1, 0]), "Invalid ICO header.");
const imageCount = ico.readUInt16LE(4);
assert.equal(imageCount, 7, "The Windows ICO must contain seven image sizes.");

const actualSizes = [];
for (let index = 0; index < imageCount; index += 1) {
  const entryOffset = 6 + index * 16;
  const width = ico[entryOffset] || 256;
  const height = ico[entryOffset + 1] || 256;
  const payloadSize = ico.readUInt32LE(entryOffset + 8);
  const payloadOffset = ico.readUInt32LE(entryOffset + 12);
  assert.equal(width, height, `ICO layer ${index} must be square.`);
  assert.deepEqual(
    ico.subarray(payloadOffset, payloadOffset + 8),
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    `ICO layer ${width}x${height} must contain PNG data.`,
  );
  assert.ok(payloadOffset + payloadSize <= ico.length, `ICO layer ${width}x${height} is truncated.`);
  actualSizes.push(width);
}
assert.deepEqual(actualSizes, [16, 24, 32, 48, 64, 128, 256]);

assert.deepEqual(
  windowsPng.subarray(0, 8),
  Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  "The Windows runtime icon must be a PNG.",
);
assert.equal(windowsPng.readUInt32BE(16), 512, "The Windows runtime icon must be 512px wide.");
assert.equal(windowsPng.readUInt32BE(20), 512, "The Windows runtime icon must be 512px high.");
assert.equal(windowsPng[25], 6, "The Windows runtime icon must use RGBA color data.");

console.log("Verified KnoArbor Windows icon assets and packaging configuration.");
