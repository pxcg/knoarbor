import type { SourceConnectorCatalogItem } from "./api/client";
import type { BrandIconName } from "./components/BrandIcon";

type Translator = (key: string) => string;

type SourceUiMetadata = {
  descriptionKey: string;
  icon: BrandIconName;
  titleKey: string;
};

export const SOURCE_CONNECTOR_ORDER = ["markdown", "codex", "hermes", "openclaw", "claude_code", "generic_chat"];

const SOURCE_UI_METADATA: Record<string, SourceUiMetadata> = {
  markdown: {
    descriptionKey: "sourceMarkdownDescription",
    icon: "markdown",
    titleKey: "markdownConnector",
  },
  codex: {
    descriptionKey: "sourceCodexDescription",
    icon: "codex",
    titleKey: "codexConnector",
  },
  hermes: {
    descriptionKey: "sourceHermesDescription",
    icon: "hermes",
    titleKey: "hermesConnector",
  },
  openclaw: {
    descriptionKey: "sourceOpenClawDescription",
    icon: "openclaw",
    titleKey: "openclawConnector",
  },
  claude_code: {
    descriptionKey: "sourceClaudeCodeDescription",
    icon: "claude_code",
    titleKey: "claudeCodeConnector",
  },
  generic_chat: {
    descriptionKey: "sourceGenericChatDescription",
    icon: "generic_chat",
    titleKey: "genericChatConnector",
  },
  mineru: {
    descriptionKey: "sourceMineruDescription",
    icon: "mineru",
    titleKey: "mineruAdapter",
  },
};

export function sortSourceConnectors<T extends { name: string }>(items: T[]) {
  const order = new Map(SOURCE_CONNECTOR_ORDER.map((name, index) => [name, index]));
  return [...items].sort((left, right) => {
    const leftIndex = order.get(left.name) ?? Number.MAX_SAFE_INTEGER;
    const rightIndex = order.get(right.name) ?? Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    return left.name.localeCompare(right.name);
  });
}

export function sourceIconName(name: string): BrandIconName | null {
  return SOURCE_UI_METADATA[name]?.icon || null;
}

export function sourceTitle(name: string, t: Translator) {
  const key = SOURCE_UI_METADATA[name]?.titleKey;
  return key ? t(key) : name;
}

export function sourceDescription(name: string, t: Translator) {
  const key = SOURCE_UI_METADATA[name]?.descriptionKey;
  return key ? t(key) : name;
}

export function sourceSettingsFields(connector?: SourceConnectorCatalogItem) {
  const schema = connector?.settings_schema;
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) return [];
  const properties = (schema as { properties?: unknown }).properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return [];
  return Object.keys(properties as Record<string, unknown>);
}
