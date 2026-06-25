import log from "electron-log/main";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import type { DesktopAppServerConfig } from "./config.js";
import type { DesktopServiceState } from "../preload/types.js";

type StateListener = (state: DesktopServiceState) => void;

const STARTUP_TIMEOUT_MS = 30_000;
const HEALTH_POLL_INTERVAL_MS = 350;
const STOP_TIMEOUT_MS = 5_000;
const RECENT_OUTPUT_LIMIT = 40;

export class DesktopServiceManager {
  private child?: ChildProcessWithoutNullStreams;
  private listener?: StateListener;
  private serviceConfig?: DesktopAppServerConfig;
  private state: DesktopServiceState = {
    mode: "managed",
    status: "idle",
  };
  private recentOutput: string[] = [];

  onStateChanged(listener: StateListener): void {
    this.listener = listener;
  }

  async start(config: DesktopAppServerConfig): Promise<DesktopServiceState> {
    this.serviceConfig = config;
    if (config.mode === "external") {
      this.setState({
        endpoint: config.url,
        mode: "external",
        startedAt: new Date().toISOString(),
        status: "healthy",
      });
      return this.state;
    }

    this.setState({
      configPath: config.configPath,
      mode: "managed",
      port: config.port,
      status: "starting",
    });

    if (!existsSync(config.webAssetsRoot)) {
      this.setState({
        ...this.state,
        lastError: `Packaged web resources are missing: ${config.webAssetsRoot}`,
        status: "failed",
      });
      return this.state;
    }

    const port = config.port || (await findAvailablePort(config.host));
    const endpoint = `http://${config.host}:${port}`;
    const logPath = join(dirname(config.configPath), "logs", "service.log");
    mkdirSync(dirname(logPath), { recursive: true });
    const logStream = createWriteStream(logPath, { flags: "a" });
    const args = [
      ...config.serviceArgs,
      "--config",
      config.configPath,
      "serve",
      "--host",
      config.host,
      "--port",
      String(port),
    ];
    const env = {
      ...process.env,
      KNOARBOR_CONFIG_PATH: config.configPath,
      KNOARBOR_DESKTOP: "1",
      KNOARBOR_LOG_DIR: dirname(logPath),
    };

    this.recentOutput = [];
    this.setState({
      command: [config.serviceCommand, ...args].join(" "),
      configPath: config.configPath,
      endpoint,
      logPath,
      mode: "managed",
      port,
      startedAt: new Date().toISOString(),
      status: "starting",
    });
    log.info("Starting KnoArbor managed service", {
      args,
      configPath: config.configPath,
      endpoint,
      logPath,
      webAssetsRoot: config.webAssetsRoot,
    });

    const child = spawn(config.serviceCommand, args, {
      cwd: findRepoRoot(),
      env,
    });
    this.child = child;

    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      logStream.write(text);
      this.recordOutput(text);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      logStream.write(text);
      this.recordOutput(text);
    });
    child.on("error", (error) => {
      logStream.end();
      this.child = undefined;
      this.setState({
        ...this.state,
        lastError: error.message,
        status: "failed",
      });
    });
    child.on("exit", (code, signal) => {
      logStream.end();
      if (this.state.status === "stopping" || this.state.status === "stopped") {
        this.child = undefined;
        return;
      }
      this.child = undefined;
      this.setState({
        ...this.state,
        lastError: `Service exited before shutdown. code=${String(code)} signal=${String(signal)} recent=${this.recentOutput.join(" | ")}`,
        lastOutput: this.recentOutput,
        status: "failed",
      });
    });

    const healthy = await waitForHealth(`${endpoint}/health`, STARTUP_TIMEOUT_MS);
    if (!healthy) {
      await this.stop();
      this.setState({
        ...this.state,
        endpoint,
        lastError: `Service did not become healthy within ${STARTUP_TIMEOUT_MS}ms. Recent output: ${this.recentOutput.join(" | ")}`,
        lastOutput: this.recentOutput,
        logPath,
        mode: "managed",
        port,
        status: "failed",
      });
      return this.state;
    }

    this.setState({
      configPath: config.configPath,
      endpoint,
      logPath,
      mode: "managed",
      port,
      startedAt: new Date().toISOString(),
      status: "healthy",
    });
    return this.state;
  }

  getState(): DesktopServiceState {
    return this.state;
  }

  async restart(config: DesktopAppServerConfig): Promise<DesktopServiceState> {
    await this.stop();
    return this.start(config);
  }

  async stop(): Promise<DesktopServiceState> {
    const child = this.child;
    if (this.state.status === "idle" || this.state.status === "stopped") {
      return this.state;
    }
    this.setState({ ...this.state, status: "stopping" });
    if (child && !child.killed) {
      child.kill("SIGTERM");
      await waitForExit(child, STOP_TIMEOUT_MS);
      if (!child.killed && child.exitCode === null) {
        child.kill("SIGKILL");
      }
    }
    this.child = undefined;
    this.setState({ ...this.state, status: "stopped" });
    return this.state;
  }

  private setState(state: DesktopServiceState): void {
    this.state = state;
    this.listener?.(state);
  }

  private recordOutput(text: string): void {
    const lines = text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    this.recentOutput.push(...lines);
    if (this.recentOutput.length > RECENT_OUTPUT_LIMIT) {
      this.recentOutput = this.recentOutput.slice(-RECENT_OUTPUT_LIMIT);
    }
  }
}

async function findAvailablePort(host: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, host, () => {
      const address = server.address();
      server.close(() => {
        if (address && typeof address === "object") {
          resolve(address.port);
        } else {
          reject(new Error("Could not allocate a local service port."));
        }
      });
    });
  });
}

async function waitForHealth(url: string, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return true;
    } catch {
      // Service is still starting.
    }
    await delay(HEALTH_POLL_INTERVAL_MS);
  }
  return false;
}

async function waitForExit(
  child: ChildProcessWithoutNullStreams,
  timeoutMs: number,
): Promise<void> {
  if (child.exitCode !== null) return;
  await Promise.race([
    new Promise<void>((resolve) => child.once("exit", () => resolve())),
    delay(timeoutMs),
  ]);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function findRepoRoot(): string {
  let current = process.cwd();
  while (true) {
    if (existsSync(join(current, "pyproject.toml"))) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) {
      return process.cwd();
    }
    current = parent;
  }
}
