import type { AppContext } from "../appContext";
import { RunPage } from "./RunPage";

type Props = {
  context: AppContext;
};

export function ImportPage({ context }: Props) {
  return (
    <section className="view active import-page">
      <RunPage context={context} embedded mode="ingest" />
    </section>
  );
}
