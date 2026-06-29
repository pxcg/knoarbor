import type { AppContext } from "../appContext";
import { RunPage } from "./RunPage";

type Props = {
  context: AppContext;
};

export function IngestPage({ context }: Props) {
  return (
    <section className="view active">
      <RunPage context={context} embedded mode="ingest" />
    </section>
  );
}
