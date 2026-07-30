import type { RunAppContext } from "../appContext";
import { RunPage } from "./RunPage";

type Props = {
  active: boolean;
  context: RunAppContext;
};

export function LintPage({ active, context }: Props) {
  return (
    <section className="view active">
      <RunPage active={active} context={context} embedded mode="lint" />
    </section>
  );
}
