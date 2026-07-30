import type { RunAppContext } from "../appContext";
import { RunPage } from "./RunPage";

type Props = {
  active: boolean;
  context: RunAppContext;
};

export function ImportPage({ active, context }: Props) {
  return (
    <section className="view active import-page">
      <RunPage active={active} context={context} embedded mode="ingest" />
    </section>
  );
}
