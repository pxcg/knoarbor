import { PagePathLinks } from "../PagePathLinks";
import { localizeReportValue } from "../reportLabels";
import { extractWikiPagePaths } from "./reportParser";
import {
  localizeCandidateKind,
  localizeDecision,
  localizeExecutorFit,
  localizeIssueCode,
  localizeOperationAction,
  localizeReportSentence,
  localizeRisk,
  localizeSeverity,
} from "./reportReadableLocalizers";

export function ReportValue({ value, t, onOpenPage }: { value: string; t: (key: string) => string; onOpenPage: (path: string) => void }) {
  const structured = structuredReportValue(value, t, onOpenPage);
  if (structured) return structured;
  const localized = localizeReportValue(value, t);
  const paths = extractWikiPagePaths(value);
  if (!paths.length) return <>{localized}</>;
  return (
    <>
      {localized}
      <PagePathLinks links={paths.map((path) => ({ path }))} inline onOpenPage={onOpenPage} />
    </>
  );
}

function structuredReportValue(value: string, t: (key: string) => string, onOpenPage: (path: string) => void) {
  const issue = value.match(/^\[(\w+)]\s+`([^`]+)`\s+in\s+`([^`]+)`:\s+(.+)$/);
  if (issue) {
    return (
      <span className="report-structured-line">
        <span className="pill">{localizeSeverity(issue[1], t)}</span>
        <code>{localizeIssueCode(issue[2], t)}</code>
        <button type="button" onClick={() => onOpenPage(issue[3])}>
          {issue[3]}
        </button>
        <span>{localizeReportSentence(issue[4], t)}</span>
      </span>
    );
  }

  const candidate = value.match(/^`([^`]+)`\s+(\S+)\s+(\S+)\s+->\s+(.+)$/);
  if (candidate) {
    return (
      <span className="report-structured-line">
        <span className="pill">{t("reportCandidate")}</span>
        <code>{localizeCandidateKind(candidate[2], t)}</code>
        <code>{localizeOperationAction(candidate[3], t)}</code>
        <button type="button" onClick={() => onOpenPage(candidate[4])}>
          {candidate[4]}
        </button>
        <small>{candidate[1]}</small>
      </span>
    );
  }

  const decision = value.match(/^\[(approve|reject)]\s+operation\s+(\d+)\s+(\S+)\s+risk=(\w+):\s+(.+)$/);
  if (decision) {
    return (
      <span className="report-structured-line decision-line">
        <span className={`pill ${decision[1] === "reject" ? "danger" : "success"}`}>{localizeDecision(decision[1], t)}</span>
        <code>{`${t("operation")} ${decision[2]}`}</code>
        <code>{localizeExecutorFit(decision[3], t)}</code>
        <code>{`${t("risk")}: ${localizeRisk(decision[4], t)}`}</code>
        <span>{localizeReportSentence(decision[5], t)}</span>
      </span>
    );
  }

  const queued = value.match(/^\[(\w+)]\s+`([^`]+)`\s+on\s+`([^`]+)`\s+risk=(\w+):\s+(.+)$/);
  if (queued) {
    return (
      <span className="report-structured-line">
        <span className="pill">{localizeOperationAction(queued[1], t)}</span>
        <code>{localizeOperationAction(queued[2], t)}</code>
        <button type="button" onClick={() => onOpenPage(queued[3])}>
          {queued[3]}
        </button>
        <code>{`${t("risk")}: ${localizeRisk(queued[4], t)}`}</code>
        <span>{localizeReportSentence(queued[5], t)}</span>
      </span>
    );
  }

  return null;
}
