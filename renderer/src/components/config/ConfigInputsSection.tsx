import { BrandIcon, type BrandIconName } from "../BrandIcon";
import type { AppNotice } from "../../appContext";
import type { ConfigForm } from "../../api/client";
import { splitLines } from "./ConfigFormControls";
import type { SectionProps } from "./ConfigSectionTypes";

type ConfigInputsSectionProps = SectionProps & {
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (notice: AppNotice | null) => void;
};

export function ConfigInputsSection({ form, setForm, t, onCommit, onError }: ConfigInputsSectionProps) {
  const genericChatRoots = form.generic_chat_roots || [];
  async function commit(nextForm: ConfigForm) {
    const previousForm = form;
    setForm(nextForm);
    try {
      await onCommit(nextForm);
    } catch (error) {
      setForm(previousForm);
      onError({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }

  const chatSources: ChatSourceRow[] = [
    {
      key: "codex",
      icon: "codex",
      title: t("codexConnector"),
      enabled: form.codex_enabled,
      detectedPaths: form.detected_chat_source_dirs?.codex || [],
      setEnabled: (checked) => void commit({ ...form, codex_enabled: checked, codex_sessions_dir: "" }),
    },
    {
      key: "hermes",
      icon: "hermes",
      title: t("hermesConnector"),
      enabled: form.hermes_enabled,
      detectedPaths: form.detected_chat_source_dirs?.hermes || [],
      setEnabled: (checked) => void commit({ ...form, hermes_enabled: checked, hermes_sessions_dir: "" }),
    },
    {
      key: "openclaw",
      icon: "openclaw",
      title: t("openclawConnector"),
      enabled: form.openclaw_enabled,
      detectedPaths: form.detected_chat_source_dirs?.openclaw || [],
      setEnabled: (checked) => void commit({ ...form, openclaw_enabled: checked, openclaw_sessions_dir: "" }),
    },
    {
      key: "claude_code",
      icon: "claude_code",
      title: t("claudeCodeConnector"),
      enabled: form.claude_code_enabled,
      detectedPaths: form.detected_chat_source_dirs?.claude_code || [],
      setEnabled: (checked) => void commit({ ...form, claude_code_enabled: checked, claude_code_sessions_dir: "" }),
    },
  ];

  return (
    <>
      <div className="section-divider" id="settings-inputs">
        <div>
          <h2>{t("inputPaths")}</h2>
          <p className="panel-copy">{t("inputPathsCopy")}</p>
        </div>
      </div>
      <div className="settings-card-grid single">
        <section className="settings-subcard chat-source-card">
          <div>
            <h3>{t("chatRecordInputs")}</h3>
            <p className="panel-copy">{t("chatRecordInputsCopy")}</p>
          </div>
          <div className="chat-source-list">
            {chatSources.map((source) => (
              <ChatSourceField key={source.key} source={source} t={t} />
            ))}
            <div className="chat-source-row custom">
              <label className="checkbox-field compact chat-source-toggle">
                <input type="checkbox" checked={form.generic_chat_enabled} onChange={(event) => void commit({ ...form, generic_chat_enabled: event.target.checked })} />
                <span className="chat-source-label">
                  <span className="chat-source-icon">
                    <BrandIcon name="generic_chat" />
                  </span>
                  {t("genericChatConnector")}
                </span>
              </label>
              <label className="field chat-source-path">
                <textarea
                  className="path-list-editor compact"
                  value={genericChatRoots.join("\n")}
                  onChange={(event) => setForm({ ...form, generic_chat_roots: splitLines(event.target.value) })}
                  onBlur={(event) => void commit({ ...form, generic_chat_roots: splitLines(event.target.value) })}
                  placeholder={t("genericChatRootsPlaceholder")}
                  aria-label={t("genericChatRoots")}
                />
              </label>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

type ChatSourceRow = {
  key: string;
  icon: BrandIconName;
  title: string;
  enabled: boolean;
  detectedPaths: string[];
  setEnabled: (checked: boolean) => void;
};

function ChatSourceField({ source, t }: { source: ChatSourceRow; t: (key: string) => string }) {
  return (
    <div className="chat-source-row">
      <label className="checkbox-field compact chat-source-toggle">
        <input type="checkbox" checked={source.enabled} onChange={(event) => source.setEnabled(event.target.checked)} />
        <span className="chat-source-label">
          <span className="chat-source-icon">
            <BrandIcon name={source.icon} />
          </span>
          {source.title}
        </span>
      </label>
      <div className={`chat-source-detected ${source.detectedPaths.length ? "" : "empty"}`}>
        {source.detectedPaths.length ? (
          source.detectedPaths.map((path) => <code key={path}>{path}</code>)
        ) : (
          <span>{t("autoDetectNoPath")}</span>
        )}
      </div>
    </div>
  );
}
