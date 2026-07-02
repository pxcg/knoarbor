import type { SectionProps } from "./ConfigSectionTypes";

export function ConfigRuntimeSection({ form, setForm, t }: SectionProps) {
  return (
    <>
      <div className="section-divider" id="settings-runtime">
        <div>
          <h2>{t("runtimeParameters")}</h2>
          <p className="panel-copy">{t("runtimeParametersCopy")}</p>
        </div>
      </div>
      <div className="form-grid config-runtime-grid">
        <label className="field">
          <span>{t("serverHost")}</span>
          <input value={form.server_host} onChange={(event) => setForm({ ...form, server_host: event.target.value })} />
        </label>
        <label className="field">
          <span>{t("serverPort")}</span>
          <input type="number" value={form.server_port} onChange={(event) => setForm({ ...form, server_port: Number(event.target.value) })} />
        </label>
        <label className="field">
          <span>{t("defaultProvider")}</span>
          <select value={form.default_provider} onChange={(event) => setForm({ ...form, default_provider: event.target.value })}>
            <option value="">{t("none")}</option>
            {form.providers
              .filter((provider) => provider.name)
              .map((provider) => (
                <option value={provider.name} key={provider.name}>
                  {provider.name}
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          <span>{t("maxTokens")}</span>
          <input type="number" value={form.default_max_tokens || ""} onChange={(event) => setForm({ ...form, default_max_tokens: event.target.value ? Number(event.target.value) : null })} />
        </label>
        <label className="field">
          <span>{t("requestTimeout")}</span>
          <input type="number" value={form.request_timeout_seconds} onChange={(event) => setForm({ ...form, request_timeout_seconds: Number(event.target.value) })} />
        </label>
      </div>
    </>
  );
}
