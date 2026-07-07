import { gzipSync } from "node:zlib";
import { readdir, readFile, stat } from "node:fs/promises";
import { extname, join, relative, resolve } from "node:path";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const distDir = resolve(scriptDir, "../dist");
const assetsDir = join(distDir, "assets");
const trackedExtensions = new Set([".js", ".css"]);
const largeChunkBytes = 500 * 1024;

const files = await collectFiles(distDir);
const records = [];

for (const filePath of files) {
  const extension = extname(filePath);
  if (!trackedExtensions.has(extension)) continue;
  const [stats, content] = await Promise.all([stat(filePath), readFile(filePath)]);
  records.push({
    path: relative(distDir, filePath),
    extension,
    bytes: stats.size,
    gzipBytes: gzipSync(content, { level: 9 }).length,
  });
}

records.sort((left, right) => right.bytes - left.bytes);

const totals = records.reduce(
  (acc, record) => {
    acc.bytes += record.bytes;
    acc.gzipBytes += record.gzipBytes;
    return acc;
  },
  { bytes: 0, gzipBytes: 0 },
);

const jsTotal = sumByExtension(records, ".js");
const cssTotal = sumByExtension(records, ".css");
const largeChunks = records.filter((record) => record.extension === ".js" && record.bytes >= largeChunkBytes);

console.log("");
console.log("Bundle size report");
console.log(`- JS total: ${formatBytes(jsTotal.bytes)} / gzip ${formatBytes(jsTotal.gzipBytes)}`);
console.log(`- CSS total: ${formatBytes(cssTotal.bytes)} / gzip ${formatBytes(cssTotal.gzipBytes)}`);
console.log(`- JS+CSS total: ${formatBytes(totals.bytes)} / gzip ${formatBytes(totals.gzipBytes)}`);
console.log(`- Asset files: ${await countAssets(assetsDir)}`);
console.log("- Largest chunks:");
for (const record of records.slice(0, 10)) {
  console.log(`  ${record.path}: ${formatBytes(record.bytes)} / gzip ${formatBytes(record.gzipBytes)}`);
}
if (largeChunks.length > 0) {
  console.log("- Lazy feature chunks above 500 KiB:");
  for (const record of largeChunks) {
    console.log(`  ${record.path}: ${formatBytes(record.bytes)} / gzip ${formatBytes(record.gzipBytes)}`);
  }
}

async function collectFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const paths = [];
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      paths.push(...(await collectFiles(fullPath)));
    } else if (entry.isFile()) {
      paths.push(fullPath);
    }
  }
  return paths;
}

async function countAssets(dir) {
  try {
    return (await readdir(dir)).length;
  } catch {
    return 0;
  }
}

function sumByExtension(records, extension) {
  return records
    .filter((record) => record.extension === extension)
    .reduce(
      (acc, record) => {
        acc.bytes += record.bytes;
        acc.gzipBytes += record.gzipBytes;
        return acc;
      },
      { bytes: 0, gzipBytes: 0 },
    );
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${kib.toFixed(1)} KiB`;
  return `${(kib / 1024).toFixed(2)} MiB`;
}
