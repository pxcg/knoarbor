import type { AppContext } from "../App";
import { RunPage } from "./RunPage";

type Props = {
  context: AppContext;
};

export function IngestPage({ context }: Props) {
  return (
    <section className="view active">
      <div className="page-intro">
        <div>
          <p className="eyebrow">{context.t("sourceToWiki")}</p>
          <h2>{context.t("ingestTitle")}</h2>
          <p className="panel-copy">{context.t("ingestSubtitle")}</p>
        </div>
      </div>
      <RunPage context={context} embedded mode="ingest" />
    </section>
  );
}
