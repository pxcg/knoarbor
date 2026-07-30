export function resolveVaultAssetImageSrc(src: string | undefined, vaultPath: string | undefined): string | undefined {
  if (!src) return src;
  if (src.startsWith("/vault-assets/")) return src;
  const existingVaultAssetPath = vaultAssetPathFromApiSrc(src);
  if (existingVaultAssetPath && vaultPath) {
    return `/vault-assets/${encodeURIComponent(existingVaultAssetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
  }
  if (/^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("//") || src.startsWith("/")) return src;
  const assetPath = vaultAssetPathFromSrc(src);
  if (!assetPath || !vaultPath) return src;
  return `/vault-assets/${encodeURIComponent(assetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
}

export function vaultAssetPathFromSrc(src: string): string | null {
  let cleaned = src.replace(/\\/g, "/").replace(/^\.\//, "");
  while (cleaned.startsWith("../")) cleaned = cleaned.slice(3);
  if (cleaned.startsWith("../assets/")) cleaned = cleaned.slice("../assets/".length);
  else if (cleaned.startsWith("raw/derived/assets/")) cleaned = cleaned.slice("raw/derived/assets/".length);
  else if (cleaned.startsWith("raw/assets/")) cleaned = cleaned.slice("raw/assets/".length);
  else if (cleaned.startsWith("assets/")) cleaned = cleaned.slice("assets/".length);
  if (cleaned.startsWith("artifacts/")) return cleaned;
  if (/^(images|media|pages|tables)\//.test(cleaned)) return cleaned;
  return null;
}

export function vaultAssetPathFromApiSrc(src: string): string | null {
  let pathname = src;
  try {
    pathname = new URL(src, "http://knoarbor.local").pathname;
  } catch {
    pathname = src.split("?", 1)[0];
  }
  const prefix = "/vault-assets/";
  if (!pathname.startsWith(prefix)) return null;
  const encoded = pathname.slice(prefix.length);
  if (!encoded) return null;
  try {
    return decodeURIComponent(encoded);
  } catch {
    return encoded;
  }
}

