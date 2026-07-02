import type { Dispatch, SetStateAction } from "react";

import type { ConfigForm, ModelProviderProbeState } from "../../api/client";
import { ChatModelProvidersSection } from "./ChatModelProvidersSection";
import { ImageModelProvidersSection } from "./ImageModelProvidersSection";

type SectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
};

export function ConfigModelProvidersSection({
  form,
  setForm,
  t,
  probeResults,
  pendingAction,
  onDiscover,
  onProbe,
}: SectionProps & {
  probeResults: Record<string, ModelProviderProbeState>;
  pendingAction: string | null;
  onDiscover: (provider: string) => void;
  onProbe: (provider: string) => void;
}) {
  return (
    <>
      <ChatModelProvidersSection
        form={form}
        setForm={setForm}
        t={t}
        probeResults={probeResults}
        pendingAction={pendingAction}
        onDiscover={onDiscover}
        onProbe={onProbe}
      />
      <ImageModelProvidersSection form={form} setForm={setForm} t={t} />
    </>
  );
}
