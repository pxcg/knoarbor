import type { AppContext } from "../App";
import { RunPage } from "./RunPage";

type Props = {
  context: AppContext;
};

export function LintPage({ context }: Props) {
  return (
    <section className="view active">
      <div className="page-intro">
        <div>
          <p className="eyebrow">{context.t("wikiMaintenance")}</p>
          <h2>{context.t("lintTitle")}</h2>
          <p className="panel-copy">{context.t("lintSubtitle")}</p>
        </div>
      </div>
      <RunPage context={context} embedded mode="lint" />
    </section>
  );
}
