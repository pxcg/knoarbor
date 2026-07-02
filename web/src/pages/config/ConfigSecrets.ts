import type { ConfigForm } from "../../api/client";

export function collectDesktopEnvSecrets(form: ConfigForm): Record<string, string> {
  const secrets: Record<string, string> = {};
  for (const provider of form.providers) {
    const name = provider.api_key_env?.trim();
    const value = provider.api_key_value?.trim();
    if (name && value) secrets[name] = value;
  }
  for (const provider of form.image_providers) {
    const name = provider.api_key_env?.trim();
    const value = provider.api_key_value?.trim();
    if (name && value) secrets[name] = value;
  }
  return secrets;
}

export function clearDesktopEnvSecretValues(form: ConfigForm): ConfigForm {
  return {
    ...form,
    providers: form.providers.map((provider) => ({
      ...provider,
      api_key_value: "",
      api_key_configured: provider.api_key_configured || Boolean(provider.api_key_value?.trim()),
    })),
    image_providers: form.image_providers.map((provider) => ({
      ...provider,
      api_key_value: "",
      api_key_configured: provider.api_key_configured || Boolean(provider.api_key_value?.trim()),
    })),
  };
}
