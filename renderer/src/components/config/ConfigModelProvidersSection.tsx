import type { Dispatch, SetStateAction } from "react";

import type { ConfigForm, ImageProviderProbeResponse, ModelProviderProbeState } from "../../api/client";
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
  imageProbeResults,
  pendingAction,
  imagePendingProvider,
  onDiscover,
  onImageProbe,
  onImageProbeInvalidated,
  onCommit,
  onError,
}: SectionProps & {
  probeResults: Record<string, ModelProviderProbeState>;
  imageProbeResults: Record<string, ImageProviderProbeResponse>;
  pendingAction: string | null;
  imagePendingProvider: string | null;
  onDiscover: (provider: string) => void;
  onImageProbe: (provider: string) => void;
  onImageProbeInvalidated: (provider: string) => void;
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (error: unknown) => void;
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
      <ImageModelProvidersSection
        form={form}
        setForm={setForm}
        t={t}
        probeResults={imageProbeResults}
        pendingProvider={imagePendingProvider}
        onProbe={onImageProbe}
        onProbeInvalidated={onImageProbeInvalidated}
        onCommit={onCommit}
        onError={onError}
      />
    </>
  );
}
