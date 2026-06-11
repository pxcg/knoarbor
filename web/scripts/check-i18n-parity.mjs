import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(resolve(root, "src/i18n/data.ts"), "utf8");

const dictBody = extractObjectBody(source, "const dictionaries");
const enBody = extractPropertyBody(dictBody, "en");
const zhBody = extractPropertyBody(dictBody, "zh");

const enKeys = extractKeys(enBody);
const zhKeys = extractKeys(zhBody);

const missingInZh = difference(enKeys, zhKeys);
const missingInEn = difference(zhKeys, enKeys);

if (missingInZh.length || missingInEn.length) {
  console.error("i18n key parity failed.");
  if (missingInZh.length) console.error(`Missing in zh:\n${missingInZh.map((key) => `- ${key}`).join("\n")}`);
  if (missingInEn.length) console.error(`Missing in en:\n${missingInEn.map((key) => `- ${key}`).join("\n")}`);
  process.exit(1);
}

console.log(`i18n parity ok: ${enKeys.length} keys`);

function extractObjectBody(text, marker) {
  const start = text.indexOf(marker);
  if (start < 0) throw new Error(`Cannot find marker: ${marker}`);
  const brace = text.indexOf("{", start);
  return readBalancedBraces(text, brace);
}

function extractPropertyBody(text, propertyName) {
  const match = new RegExp(`\\b${propertyName}\\s*:`).exec(text);
  if (!match) throw new Error(`Cannot find property: ${propertyName}`);
  const brace = text.indexOf("{", match.index);
  return readBalancedBraces(text, brace);
}

function readBalancedBraces(text, braceStart) {
  if (braceStart < 0 || text[braceStart] !== "{") throw new Error("Expected object brace");
  let depth = 0;
  let inString = false;
  let quote = "";
  let escaped = false;
  for (let index = braceStart; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        inString = false;
      }
      continue;
    }
    if (char === '"' || char === "'" || char === "`") {
      inString = true;
      quote = char;
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(braceStart + 1, index);
    }
  }
  throw new Error("Unbalanced object braces");
}

function extractKeys(body) {
  const keys = [];
  const keyPattern = /(?:^|[\n,])\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$]*))\s*:/g;
  let match;
  while ((match = keyPattern.exec(body))) {
    keys.push(match[1] || match[2] || match[3]);
  }
  return Array.from(new Set(keys)).sort();
}

function difference(left, right) {
  const rightSet = new Set(right);
  return left.filter((key) => !rightSet.has(key));
}
