export function normalizePathSeparators(value: string): string {
  return value.replace(/\\/g, "/");
}

export function pathBaseName(value: string): string {
  const normalized = normalizePathSeparators(value.trim());
  if (!normalized) return value;
  return normalized.split("/").filter(Boolean).pop() || normalized;
}
