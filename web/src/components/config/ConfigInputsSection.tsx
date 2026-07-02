import { BrandIcon, type BrandIconName } from "../BrandIcon";
import { ConnectorCard, PathField, splitLines } from "./ConfigFormControls";
import type { SectionProps } from "./ConfigSectionTypes";

export function ConfigInputsSection({ form, setForm, t }: SectionProps) {
  const genericChatRoots = form.generic_chat_roots || [];
  const chatSources: ChatSourceRow[] = [
    {
      key: "codex",
      icon: "codex",
      title: t("codexConnector"),
      enabled: form.codex_enabled,
      path: form.codex_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, codex_enabled: checked }),
      setPath: (value) => setForm({ ...form, codex_sessions_dir: value }),
      placeholder: "~/.codex/sessions",
    },
    {
      key: "hermes",
      icon: "hermes",
      title: t("hermesConnector"),
      enabled: form.hermes_enabled,
      path: form.hermes_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, hermes_enabled: checked }),
      setPath: (value) => setForm({ ...form, hermes_sessions_dir: value }),
      placeholder: "~/.hermes/sessions",
    },
    {
      key: "openclaw",
      icon: "openclaw",
      title: t("openclawConnector"),
      enabled: form.openclaw_enabled,
      path: form.openclaw_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, openclaw_enabled: checked }),
      setPath: (value) => setForm({ ...form, openclaw_sessions_dir: value }),
      placeholder: "~/.openclaw/agents/main/sessions",
    },
    {
      key: "claude_code",
      icon: "claude_code",
      title: t("claudeCodeConnector"),
      enabled: form.claude_code_enabled,
      path: form.claude_code_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, claude_code_enabled: checked }),
      setPath: (value) => setForm({ ...form, claude_code_sessions_dir: value }),
      placeholder: "~/.claude/projects",
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
      <div className="settings-card-grid">
        <ConnectorCard title={t("markdownConnector")} checked={form.markdown_enabled} onChange={(checked) => setForm({ ...form, markdown_enabled: checked })}>
          <label className="field">
            <span>{t("markdownRoots")}</span>
            <textarea className="path-list-editor" value={form.markdown_roots.join("\n")} onChange={(event) => setForm({ ...form, markdown_roots: splitLines(event.target.value) })} />
          </label>
        </ConnectorCard>
        <ConnectorCard title={t("nonMarkdownConnector")} checked={form.mineru_enabled} onChange={(checked) => setForm({ ...form, mineru_enabled: checked })}>
          <PathField
            label={t("nonMarkdownInputDir")}
            value={form.mineru_input_dir}
            onChange={(value) => setForm({ ...form, mineru_input_dir: value })}
            placeholder="./vaults/all/raw/inbox/documents"
            selectDirectoryTitle={t("chooseSourceFolder")}
            t={t}
          />
          <p className="panel-copy compact-copy">{t("nonMarkdownInputCopy")}</p>
        </ConnectorCard>
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
                <input type="checkbox" checked={form.generic_chat_enabled} onChange={(event) => setForm({ ...form, generic_chat_enabled: event.target.checked })} />
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
  path: string;
  setEnabled: (checked: boolean) => void;
  setPath: (value: string) => void;
  placeholder: string;
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
      <PathField label="" value={source.path} onChange={source.setPath} className="chat-source-path" placeholder={source.placeholder} ariaLabel={source.title} selectDirectoryTitle={source.title} t={t} />
    </div>
  );
}
