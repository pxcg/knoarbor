import type { ConfigDiagnosticItem, ConfigDiagnostics } from "../../api/client";
import { BrandIcon, type BrandIconName } from "../BrandIcon";
import { LineIcon, type IconName } from "../LineIcon";

type Props = {
  diagnostics?: ConfigDiagnostics | null;
  loading?: boolean;
  t: (key: string) => string;
};

const BRAND_DIAGNOSTIC_ICONS: Record<string, BrandIconName> = {
  markdown: "markdown",
  hermes: "hermes",
  codex: "codex",
  openclaw: "openclaw",
  claude_code: "claude_code",
  generic_chat: "generic_chat",
  mineru: "mineru",
};

export function ConfigDiagnosticsPanel({ diagnostics, loading = false, t }: Props) {
  if (loading) {
    return <div className="empty-state">{t("loading")}</div>;
  }
  const connectorItems = [...(diagnostics?.connectors || []), ...(diagnostics?.processors || [])];
  return (
    <div className="diagnostic-grid">
      <DiagnosticGroup title={t("connectorStatus")} items={connectorItems} t={t} />
      <DiagnosticGroup title={t("modelStatus")} items={diagnostics?.providers || []} t={t} />
      <DiagnosticGroup title={t("pathStatus")} items={diagnostics?.paths || []} t={t} />
    </div>
  );
}

function DiagnosticGroup({ title, items, t }: { title: string; items: ConfigDiagnosticItem[]; t: (key: string) => string }) {
  return (
    <section className="diagnostic-card">
      <h3>{title}</h3>
      {items.length ? (
        <div className="diagnostic-list">
          {items.map((item) => (
            <article className={`diagnostic-item ${item.enabled ? (item.ok ? "ok" : "error") : "disabled"}`} key={`${item.category}:${item.name}`}>
              <DiagnosticIcon item={item} />
              <div className="diagnostic-main">
                <strong>{diagnosticName(item.name, t)}</strong>
                <span>{diagnosticMessage(item, t)}</span>
                <small>{diagnosticMeta(item, t)}</small>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="panel-copy">{t("noDiagnostics")}</p>
      )}
    </section>
  );
}

function DiagnosticIcon({ item }: { item: ConfigDiagnosticItem }) {
  const brand = BRAND_DIAGNOSTIC_ICONS[item.name];
  if (brand) {
    return (
      <span className="diagnostic-icon source-diagnostic-icon">
        <BrandIcon name={brand} />
      </span>
    );
  }
  const lineIcon: IconName = item.category === "provider" ? "settings" : item.name === "vault" ? "graph" : "overview";
  return (
    <span className="diagnostic-icon line-diagnostic-icon">
      <LineIcon name={lineIcon} />
    </span>
  );
}

function diagnosticName(name: string, t: (key: string) => string) {
  const key = `diagnosticName.${name}`;
  const translated = t(key);
  return translated === key ? name : translated;
}

function diagnosticMessage(item: ConfigDiagnosticItem, t: (key: string) => string) {
  const key = `diagnosticCode.${item.code}`;
  const translated = t(key);
  return translated === key ? item.code : translated;
}

function diagnosticMeta(item: ConfigDiagnosticItem, t: (key: string) => string) {
  const parts: string[] = [];
  if (item.path) parts.push(item.path);
  if (typeof item.count === "number") parts.push(`${item.count} ${t("files")}`);
  if (item.detail) parts.push(item.detail);
  return parts.join(" · ") || t("noExtraDetail");
}
