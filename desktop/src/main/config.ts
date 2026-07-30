import { app } from "electron";
import {
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { desktopProduct, productEnv } from "./product.js";

const DEFAULT_HOST = "127.0.0.1";
let configuredProductDataRoot: string | undefined;

export type DesktopAppServerConfig =
  | {
      mode: "external";
      url: string;
    }
  | {
      appDataRoot: string;
      configPath: string;
      host: string;
      mode: "managed";
      port: number;
      serviceCommand: string;
      serviceArgs: string[];
      serviceCwd: string;
      rendererAssetsRoot: string;
    };

export type DesktopAppConfig = {
  appServer: DesktopAppServerConfig;
  appUserModelId: string;
  rendererAssetsRoot: string;
};

export function resolveDesktopAppConfig(): DesktopAppConfig {
  const appServer = resolveAppServerConfig();
  return {
    appServer,
    appUserModelId: desktopProduct.appUserModelId,
    rendererAssetsRoot:
      appServer.mode === "managed" ? appServer.rendererAssetsRoot : resolveRendererAssetsRoot(),
  };
}

export function configureDesktopDataPaths(): string {
  const override = productEnv("DESKTOP_APP_DATA_ROOT");
  const productRoot = override || defaultProductDataRoot();
  const stateRoot = join(productRoot, "state");
  const cacheRoot = join(productRoot, "cache");
  mkdirSync(join(stateRoot, "electron"), { recursive: true });
  mkdirSync(cacheRoot, { recursive: true });
  app.setPath("userData", join(stateRoot, "electron"));
  app.setPath("sessionData", join(stateRoot, "electron"));
  configuredProductDataRoot = productRoot;
  return productRoot;
}

function resolveAppServerConfig(): DesktopAppServerConfig {
  const externalUrl = productEnv("DESKTOP_APP_SERVER_URL");
  if (externalUrl) {
    return { mode: "external", url: externalUrl };
  }

  const appDataRoot =
    productEnv("DESKTOP_APP_DATA_ROOT") || configuredProductDataRoot || defaultProductDataRoot();
  const configPath = resolveConfigPath(
    productEnv("CONFIG_PATH"),
    appDataRoot,
  );
  return {
    appDataRoot,
    configPath,
    host: productEnv("DESKTOP_APP_SERVER_HOST") ?? DEFAULT_HOST,
    mode: "managed",
    port: readPort(productEnv("DESKTOP_APP_SERVER_PORT")),
    serviceArgs: readServiceArgs(app.isPackaged),
    serviceCommand: resolveServiceCommand(app.isPackaged),
    serviceCwd:
      productEnv("DESKTOP_SERVICE_CWD") ||
      (app.isPackaged ? appDataRoot : findRepoRootFromDesktopRoot()),
    rendererAssetsRoot: resolveRendererAssetsRoot(),
  };
}

function resolveRendererAssetsRoot(): string {
  return app.isPackaged
    ? join(process.resourcesPath, "renderer")
    : join(findRepoRootFromDesktopRoot(), "renderer", "dist");
}

export function ensureDesktopBootstrapConfig(config: DesktopAppServerConfig): void {
  if (config.mode !== "managed") return;
  for (const directory of ["logs", "state", "cache", "tmp"]) {
    mkdirSync(join(config.appDataRoot, directory), { recursive: true });
  }
  const defaultVaultRoot = join(config.appDataRoot, "vaults", "default");
  createDesktopVaultLayout(defaultVaultRoot);
  mkdirSync(dirname(config.configPath), { recursive: true });
  if (existsSync(config.configPath)) return;
  writePrivateFileAtomic(
    config.configPath,
    desktopDefaultConfigYaml({
      host: config.host,
      port: config.port || 0,
      vaultPath: defaultVaultRoot,
    }),
  );
}

export function writePrivateFileAtomic(path: string, content: string): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.${Date.now()}.tmp`;
  let descriptor: number | undefined;
  try {
    descriptor = openSync(temporary, "wx", 0o600);
    writeFileSync(descriptor, content, "utf-8");
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = undefined;
    renameSync(temporary, path);
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
    if (existsSync(temporary)) unlinkSync(temporary);
  }
}

function defaultProductDataRoot(): string {
  if (process.platform === "win32") {
    const localAppData = process.env.LOCALAPPDATA?.trim();
    return join(localAppData || app.getPath("appData"), desktopProduct.appDataDir);
  }
  if (process.platform === "linux") {
    const dataHome = process.env.XDG_DATA_HOME?.trim() || join(homedir(), ".local", "share");
    return join(dataHome, desktopProduct.appDataDir);
  }
  return join(app.getPath("appData"), desktopProduct.appDataDir);
}

function createDesktopVaultLayout(vaultRoot: string): void {
  const directories = [
    "raw/inbox/documents",
    "raw/inbox/chats",
    "raw/inbox/media",
    "raw/inbox/notes",
    "raw/derived/markdown",
    "raw/derived/excerpts",
    "raw/derived/assets/images",
    "raw/derived/assets/media",
    "raw/derived/assets/pages",
    "raw/derived/assets/tables",
    "raw/derived/metadata/documents",
    "raw/derived/metadata/sources",
    "artifacts/chat",
    "wiki/pages",
    "wiki/sources",
    "maintenance/reports/ingest",
    "maintenance/reports/lint",
    "maintenance/reports/query",
    "maintenance/reports/run-failure",
    "maintenance/archives",
    ".knoarbor/index",
    ".knoarbor/ledgers",
    ".knoarbor/checkpoints",
    ".knoarbor/runs",
    ".knoarbor/locks",
    ".knoarbor/logs",
    ".knoarbor/tmp",
    ".knoarbor/chat/sessions",
  ];
  for (const directory of directories) {
    mkdirSync(join(vaultRoot, directory), { recursive: true });
  }
}

function desktopDefaultConfigYaml(input: {
  host: string;
  port: number;
  vaultPath: string;
}): string {
  const port = input.port > 0 ? input.port : 8000;
  const vaultPath = pathRelativeToConfigDir(input.vaultPath);
  const vaultRelative = (relativePath: string): string => `${vaultPath}/${relativePath}`;
  return `# ${desktopProduct.name} Desktop local configuration.
# Model providers use direct API key fields in the settings page.

project:
  name: ${desktopProduct.defaultVaultName}
  host_project_root: .

config_version: 3

vaults:
  default: default
  profiles:
    default:
      name: ${desktopProduct.defaultVaultName}
      path: ${quoteYamlString(vaultPath)}

vault:
  path: ${quoteYamlString(vaultPath)}

server:
  host: ${quoteYamlString(input.host)}
  port: ${port}

models:
  default_provider:
  default_max_tokens: 30000
  request_timeout_seconds: 600
  retry:
    enabled: true
    max_attempts: 2
    backoff_seconds: 2
    retry_on_invalid_output: true
  providers: {}

document_processing:
  mineru:
    enabled: false
    endpoint: http://127.0.0.1:18000/file_parse
    input_dir: ${quoteYamlString(vaultRelative("raw/inbox/documents"))}
    output_dir: ${quoteYamlString(vaultRelative("raw/derived/markdown"))}
    recursive: true
    patterns:
      - "*.pdf"
      - "*.docx"
      - "*.pptx"
    mode: auto
    timeout_seconds: 600
    file_field: files
    output_dir_field:
    mode_field: parse_method
    response_markdown_field: markdown
    response_path_field:
    headers: {}
    extra_fields:
      backend: pipeline
      lang_list: ch
      formula_enable: true
      table_enable: true
      start_page_id: 0
      end_page_id: 99999
      return_md: true
      return_middle_json: false
      return_model_output: false
      return_content_list: false
      return_images: true
      response_format_zip: false

connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - ${quoteYamlString(vaultRelative("raw/inbox/notes"))}
        - ${quoteYamlString(vaultRelative("raw/derived/markdown"))}
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/inbox/notes"))}
      preserve_relative_paths: true
  codex:
    enabled: false
    settings:
      sessions_dir: ~/.codex/sessions
      pattern: "rollout-*.jsonl"
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/inbox/chats"))}
  hermes:
    enabled: false
    settings:
      sessions_dir: ~/.hermes/sessions
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/inbox/chats"))}
  openclaw:
    enabled: false
    settings:
      sessions_dir: ~/.openclaw/agents/main/sessions
      pattern: "*.jsonl"
      recursive: false
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/inbox/chats"))}
  claude_code:
    enabled: false
    settings:
      sessions_dir: ~/.claude/projects
      pattern: "*.jsonl"
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/inbox/chats"))}
  generic_chat:
    enabled: false
    settings:
      roots: []
      patterns:
        - "*.jsonl"
        - "*.sqlite"
        - "*.db"
      recursive: true
      raw_output_dir: ${quoteYamlString(vaultRelative("raw/inbox/chats"))}

memory:
  enabled: true
  auto_write_explicit_low_risk: true
  max_recalled_records: 12

chat:
  auto_ingest:
    enabled: false
    trigger: on_session_close
    min_user_turns: 2
    write: true
    write_report: true
    append_ledger: true

ingest:
  auto_scoped_lint: true
  segmentation:
    enabled: true
    max_chars_per_segment: 18000
    soft_chars_per_segment: 12000
    max_segments_per_source: 20
    min_segment_chars: 1000

lint:
  default_scope: latest-ingest
  scoped_include_related: true
  include_neighbors: true
  include_global_checks: true

privacy:
  redaction_enabled: true
  redact_emails: true
  redact_phone_numbers: true
  redact_api_keys: true
  redact_private_keys: true
  redact_platform_ids: true
  redact_local_paths: true
  redact_source_paths_in_pages: true
  redact_private_ips: false
  custom_terms: []
`;
}

function quoteYamlString(value: string): string {
  return JSON.stringify(value);
}

function pathRelativeToConfigDir(path: string): string {
  return `./${relativePathFromRootToAppData(path)}`;
}

function relativePathFromRootToAppData(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const marker = "/vaults/";
  const index = normalized.lastIndexOf(marker);
  return index >= 0 ? normalized.slice(index + 1) : normalized;
}

function resolveServiceCommand(isPackaged: boolean): string {
  const explicit = productEnv("DESKTOP_SERVICE_COMMAND");
  if (explicit) return explicit;
  if (!isPackaged) return "uv";
  const executable = process.platform === "win32" ? "knoar-service.exe" : "knoar-service";
  return join(process.resourcesPath, "service", executable);
}

function readServiceArgs(isPackaged: boolean): string[] {
  const raw = productEnv("DESKTOP_SERVICE_ARGS");
  if (raw) {
    return raw.split(/\s+/).filter(Boolean);
  }
  return isPackaged ? [] : ["run", "knoar"];
}

function readPort(value: string | undefined): number {
  if (!value) return 0;
  const port = Number(value);
  return Number.isInteger(port) && port >= 0 && port <= 65535 ? port : 0;
}

function resolveConfigPath(value: string | undefined, appDataRoot: string): string {
  if (value) {
    return isAbsolute(value) ? value : resolve(process.cwd(), value);
  }
  return join(appDataRoot, "config.yaml");
}

function findDesktopRoot(): string {
  let current = dirname(fileURLToPath(import.meta.url));
  while (true) {
    if (existsSync(join(current, "package.json"))) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) {
      return process.cwd();
    }
    current = parent;
  }
}

function findRepoRootFromDesktopRoot(): string {
  let current = findDesktopRoot();
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
