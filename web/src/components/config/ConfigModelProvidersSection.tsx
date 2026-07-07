import type { Dispatch, SetStateAction } from "react";

import type { AppNotice } from "../../appContext";
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
  onCommit,
  onError,
}: SectionProps & {
  probeResults: Record<string, ModelProviderProbeState>;
  pendingAction: string | null;
  onDiscover: (provider: string) => void;
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (notice: AppNotice | null) => void;
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
        onCommit={onCommit}
        onError={onError}
      />
      <ImageModelProvidersSection form={form} setForm={setForm} t={t} onCommit={onCommit} onError={onError} />
    </>
  );
}
