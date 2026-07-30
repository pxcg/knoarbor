import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const domains = ["ui", "config", "workflows"];
const enBody = readLocale("en");
const zhBody = readLocale("zh");

const enKeys = extractKeys(enBody);
const zhKeys = extractKeys(zhBody);
assertUnique("en", enKeys);
assertUnique("zh", zhKeys);

const missingInZh = difference(enKeys, zhKeys);
const missingInEn = difference(zhKeys, enKeys);

if (missingInZh.length || missingInEn.length) {
  console.error("i18n key parity failed.");
  if (missingInZh.length) console.error(`Missing in zh:\n${missingInZh.map((key) => `- ${key}`).join("\n")}`);
  if (missingInEn.length) console.error(`Missing in en:\n${missingInEn.map((key) => `- ${key}`).join("\n")}`);
  process.exit(1);
}

console.log(`i18n parity ok: ${new Set(enKeys).size} keys`);

function readLocale(language) {
  return domains.map((domain) => {
    const source = readFileSync(resolve(root, `src/i18n/locales/${language}-${domain}.ts`), "utf8");
    return extractObjectBody(source, `const ${domain}`);
  }).join("\n");
}

function extractObjectBody(text, marker) {
  const start = text.indexOf(marker);
  if (start < 0) throw new Error(`Cannot find marker: ${marker}`);
  const brace = text.indexOf("{", start);
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
  return keys.sort();
}

function assertUnique(language, keys) {
  const duplicates = keys.filter((key, index) => key === keys[index - 1]);
  if (!duplicates.length) return;
  console.error(`Duplicate ${language} keys:\n${Array.from(new Set(duplicates)).map((key) => `- ${key}`).join("\n")}`);
  process.exit(1);
}

function difference(left, right) {
  const rightSet = new Set(right);
  return left.filter((key) => !rightSet.has(key));
}
