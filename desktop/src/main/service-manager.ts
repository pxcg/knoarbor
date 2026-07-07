import log from "electron-log/main";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, isAbsolute, join } from "node:path";
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
      const startedAt = new Date().toISOString();
      this.setState({
        endpoint: config.url,
        mode: "external",
        startedAt,
        status: "starting",
      });
      const healthy = await waitForHealth(`${config.url}/health`, STARTUP_TIMEOUT_MS);
      this.setState({
        endpoint: config.url,
        lastError: healthy
          ? undefined
          : `External KnoArbor service is not healthy: ${config.url}`,
        mode: "external",
        startedAt,
        status: healthy ? "healthy" : "failed",
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
    const appDataRoot = dirname(config.configPath);
    const logDir = join(appDataRoot, "logs");
    const stateDir = join(appDataRoot, "state");
    const logPath = join(logDir, "service.log");
    mkdirSync(logDir, { recursive: true });
    mkdirSync(stateDir, { recursive: true });
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
      KNOARBOR_LOG_DIR: logDir,
      KNOARBOR_STATE_DIR: stateDir,
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
    log.info("Starting KnoArbor managed service", {
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
        lastOutput: this.recentOutput,
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
        exitCode: code,
        lastError: `Service exited before shutdown. code=${String(code)} signal=${String(signal)} recent=${this.recentOutput.join(" | ")}`,
        lastOutput: this.recentOutput,
        signal,
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
        logDir,
        logPath,
        mode: "managed",
        port,
        stateDir,
        status: "failed",
      });
      return this.state;
    }

    writeFileSync(
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
      "utf-8",
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
