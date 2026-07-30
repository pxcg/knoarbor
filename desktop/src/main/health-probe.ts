import { request as requestHttp } from "node:http";
import { request as requestHttps } from "node:https";

const HEALTH_POLL_INTERVAL_MS = 350;
const HEALTH_REQUEST_TIMEOUT_MS = 1_500;

export type HealthProbeResult = {
  healthy: boolean;
  lastError?: string;
};

export async function waitForHealth(
  url: string,
  timeoutMs: number,
): Promise<HealthProbeResult> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "The health endpoint did not respond.";
  while (Date.now() < deadline) {
    const remainingMs = Math.max(1, deadline - Date.now());
    try {
      const status = await requestHealth(url, Math.min(HEALTH_REQUEST_TIMEOUT_MS, remainingMs));
      if (status >= 200 && status < 300) {
        return { healthy: true };
      }
      lastError = `Health endpoint returned HTTP ${status}.`;
    } catch (error) {
      lastError = boundedError(error);
    }
    const delayMs = Math.min(HEALTH_POLL_INTERVAL_MS, Math.max(0, deadline - Date.now()));
    if (delayMs > 0) await delay(delayMs);
  }
  return { healthy: false, lastError };
}

function requestHealth(url: string, timeoutMs: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const request =
      target.protocol === "http:"
        ? requestHttp
        : target.protocol === "https:"
          ? requestHttps
          : null;
    if (!request) {
      reject(new Error(`Unsupported health endpoint protocol: ${target.protocol}`));
      return;
    }

    const operation = request(
      target,
      {
        agent: false,
        headers: { Accept: "application/json" },
        method: "GET",
      },
      (response) => {
        response.resume();
        resolve(response.statusCode ?? 0);
      },
    );
    operation.setTimeout(timeoutMs, () => {
      operation.destroy(new Error(`Health request timed out after ${timeoutMs}ms.`));
    });
    operation.once("error", reject);
    operation.end();
  });
}

function boundedError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message.slice(0, 240) || "The health endpoint did not respond.";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
