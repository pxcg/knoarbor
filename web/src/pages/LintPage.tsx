import type { AppContext } from "../appContext";
import { RunPage } from "./RunPage";

type Props = {
  context: AppContext;
};

export function LintPage({ context }: Props) {
  return (
    <section className="view active">
      <RunPage context={context} embedded mode="lint" />
    </section>
  );
}
