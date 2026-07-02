import type { AppContext } from "../../appContext";
import { LineIcon } from "../LineIcon";

export function RunFlowGuide({ context, mode }: { context: AppContext; mode: "both" | "ingest" | "lint" }) {
  const cards =
    mode === "lint"
      ? [
          { icon: "lint" as const, title: context.t("lintFlowCheck"), copy: context.t("lintFlowCheckCopy") },
          { icon: "reports" as const, title: context.t("lintFlowReview"), copy: context.t("lintFlowReviewCopy") },
        ]
      : mode === "ingest"
        ? [
            { icon: "sources" as const, title: context.t("ingestFlowInput"), copy: context.t("ingestFlowInputCopy") },
            { icon: "mineru" as const, title: context.t("ingestFlowPreprocess"), copy: context.t("ingestFlowPreprocessCopy") },
            { icon: "ingest" as const, title: context.t("ingestFlowCompile"), copy: context.t("ingestFlowCompileCopy") },
          ]
        : [
            { icon: "sources" as const, title: context.t("ingestFlowInput"), copy: context.t("ingestFlowInputCopy") },
            { icon: "ingest" as const, title: context.t("ingestFlowCompile"), copy: context.t("ingestFlowCompileCopy") },
            { icon: "lint" as const, title: context.t("lintFlowCheck"), copy: context.t("lintFlowCheckCopy") },
          ];
  return (
    <article className="run-flow-guide">
      <div className="run-flow-heading">
        <h2>{context.t("processingFlow")}</h2>
        <p>{context.t(mode === "lint" ? "lintProcessingFlowCopy" : "ingestProcessingFlowCopy")}</p>
      </div>
      <div className="run-flow-steps">
        {cards.map((card) => (
          <div className="flow-step-card" key={card.title}>
            <span className="flow-step-icon">
              <LineIcon name={card.icon} />
            </span>
            <div>
              <strong>{card.title}</strong>
              <p>{card.copy}</p>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
