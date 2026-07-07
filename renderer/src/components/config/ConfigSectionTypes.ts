import type { Dispatch, SetStateAction } from "react";

import type { ConfigForm } from "../../api/client";

export type SectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
};
