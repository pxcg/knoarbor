import log from "electron-log/main";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, renameSync, statSync, unlinkSync } from "node:fs";
import { createServer } from "node:net";
import { isAbsolute, join } from "node:path";
import { writePrivateFileAtomic, type DesktopAppServerConfig } from "./config.js";
import { waitForHealth } from "./health-probe.js";
import { desktopProduct } from "./product.js";
import type { DesktopServiceState } from "../preload/types.js";

type StateListener = (state: DesktopServiceState) => void;

const STARTUP_TIMEOUT_MS = 30_000;
const STOP_TIMEOUT_MS = 5_000;
const RECENT_OUTPUT_LIMIT = 40;
const SERVICE_LOG_MAX_BYTES = 2_000_000;
const SERVICE_LOG_BACKUP_COUNT = 5;

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
      const startedAt = new Date().toISOString();
      this.setState({
        endpoint: config.url,
        mode: "external",
        startedAt,
        status: "starting",
      });
      const health = await waitForHealth(`${config.url}/health`, STARTUP_TIMEOUT_MS);
      this.setState({
        endpoint: config.url,
        lastError: health.healthy
          ? undefined
          : `External ${desktopProduct.name} service is not healthy: ${config.url}. ${health.lastError}`,
        mode: "external",
        startedAt,
        status: health.healthy ? "healthy" : "failed",
      });
      return this.state;
    }

    if (
      this.child &&
      (this.state.status === "starting" || this.state.status === "healthy")
    ) {
      return this.state;
    }

    this.setState({
      configPath: config.configPath,
      mode: "managed",
      port: config.port,
      status: "starting",
    });

    if (!existsSync(config.rendererAssetsRoot)) {
      this.setState({
        ...this.state,
        lastError: `Packaged renderer resources are missing: ${config.rendererAssetsRoot}`,
        status: "failed",
      });
      return this.state;
    }
    if (isAbsolute(config.serviceCommand) && !existsSync(config.serviceCommand)) {
      this.setState({
        ...this.state,
        lastError: `Packaged service executable is missing: ${config.serviceCommand}`,
        status: "failed",
      });
      return this.state;
    }

    const port = config.port || (await findAvailablePort(config.host));
    const endpoint = `http://${config.host}:${port}`;
    const appDataRoot = config.appDataRoot;
    const logDir = join(appDataRoot, "logs");
    const stateDir = join(appDataRoot, "state");
    const logPath = join(logDir, "service.log");
    mkdirSync(logDir, { recursive: true });
    mkdirSync(stateDir, { recursive: true });
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
      KNOARBOR_LOG_DIR: logDir,
      KNOARBOR_STATE_DIR: stateDir,
      KNOARBOR_RUNTIME_DIR: stateDir,
    };

    this.recentOutput = [];
    const startedAt = new Date().toISOString();
    this.setState({
      command: [config.serviceCommand, ...args].join(" "),
      configPath: config.configPath,
      endpoint,
      logDir,
      logPath,
      mode: "managed",
      port,
      startedAt,
      stateDir,
      status: "starting",
    });
    log.info(`Starting ${desktopProduct.name} managed service`, {
      args,
      configPath: config.configPath,
      endpoint,
      logPath,
      serviceCwd: config.serviceCwd,
      stateDir,
      rendererAssetsRoot: config.rendererAssetsRoot,
    });

    const child = spawn(config.serviceCommand, args, {
      cwd: config.serviceCwd,
      env,
    });
    this.child = child;

    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      appendBoundedServiceLog(logPath, text);
      this.recordOutput(text);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      appendBoundedServiceLog(logPath, text);
      this.recordOutput(text);
    });
    child.on("error", (error) => {
      this.child = undefined;
      this.setState({
        ...this.state,
        lastError: error.message,
        lastOutput: this.recentOutput,
        status: "failed",
      });
    });
    child.on("exit", (code, signal) => {
      if (this.state.status === "stopping" || this.state.status === "stopped") {
        this.child = undefined;
        return;
      }
      log.error(`${desktopProduct.name} managed service exited unexpectedly`, {
        code,
        signal,
      });
      this.child = undefined;
      this.setState({
        ...this.state,
        exitCode: code,
        lastError: `Service exited before shutdown. code=${String(code)} signal=${String(signal)} recent=${this.recentOutput.join(" | ")}`,
        lastOutput: this.recentOutput,
        signal,
        status: "failed",
      });
    });

    const health = await waitForHealth(`${endpoint}/health`, STARTUP_TIMEOUT_MS);
    if (!health.healthy) {
      await this.stop();
      log.error(`${desktopProduct.name} managed service health probe failed`, {
        endpoint,
        error: health.lastError,
      });
      this.setState({
        ...this.state,
        endpoint,
        lastError: `Service did not become healthy within ${STARTUP_TIMEOUT_MS}ms. ${health.lastError} Recent output: ${this.recentOutput.join(" | ")}`,
        lastOutput: this.recentOutput,
        logDir,
        logPath,
        mode: "managed",
        port,
        stateDir,
        status: "failed",
      });
      return this.state;
    }

    writePrivateFileAtomic(
      join(stateDir, "service.json"),
      JSON.stringify(
        {
          configPath: config.configPath,
          endpoint,
          logPath,
          pid: child.pid,
          port,
          startedAt,
        },
        null,
        2,
      ),
    );
    this.setState({
      configPath: config.configPath,
      endpoint,
      logDir,
      logPath,
      mode: "managed",
      port,
      startedAt,
      stateDir,
      status: "healthy",
    });
    return this.state;
  }

  getState(): DesktopServiceState {
    return this.state;
  }

  async restart(config: DesktopAppServerConfig): Promise<DesktopServiceState> {
    const currentPort = this.state.mode === "managed" ? this.state.port : undefined;
    const restartConfig =
      config.mode === "managed" && !config.port && currentPort
        ? { ...config, port: currentPort }
        : config;
    await this.stop();
    return this.start(restartConfig);
  }

  async stop(): Promise<DesktopServiceState> {
    const child = this.child;
    if (this.state.status === "idle" || this.state.status === "stopped") {
      return this.state;
    }
    this.setState({ ...this.state, status: "stopping" });
    if (child && !hasExited(child)) {
      child.kill("SIGTERM");
      await waitForExit(child, STOP_TIMEOUT_MS);
      if (!hasExited(child)) {
        child.kill("SIGKILL");
        await waitForExit(child, STOP_TIMEOUT_MS);
      }
      if (!hasExited(child)) {
        this.setState({
          ...this.state,
          lastError: "Local service did not stop after termination was requested.",
          status: "failed",
        });
        return this.state;
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

function appendBoundedServiceLog(path: string, text: string): void {
  let data = Buffer.from(text, "utf-8");
  if (data.length > SERVICE_LOG_MAX_BYTES) {
    data = data.subarray(data.length - SERVICE_LOG_MAX_BYTES);
  }
  const currentSize = existsSync(path) ? statSync(path).size : 0;
  if (currentSize + data.length > SERVICE_LOG_MAX_BYTES) {
    for (let index = SERVICE_LOG_BACKUP_COUNT; index >= 1; index -= 1) {
      const source = index === 1 ? path : `${path}.${index - 1}`;
      const target = `${path}.${index}`;
      if (!existsSync(source)) continue;
      if (existsSync(target)) unlinkSync(target);
      renameSync(source, target);
    }
  }
  appendFileSync(path, data, { mode: 0o600 });
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

async function waitForExit(
  child: ChildProcessWithoutNullStreams,
  timeoutMs: number,
): Promise<void> {
  if (hasExited(child)) return;
  await Promise.race([
    new Promise<void>((resolve) => child.once("exit", () => resolve())),
    delay(timeoutMs),
  ]);
}

function hasExited(child: ChildProcessWithoutNullStreams): boolean {
  return child.exitCode !== null || child.signalCode !== null;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
