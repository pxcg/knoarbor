import type { RunRecord } from "../types";

export function runStatusLabel(status: RunRecord["status"] | string, t: (key: string) => string) {
  const key = `runStatus.${status}`;
  const translated = t(key);
  return translated === key ? status : translated;
}

export function runStatusClass(status: RunRecord["status"] | string) {
  return `status-dot ${status}`;
}
