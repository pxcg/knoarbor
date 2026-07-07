export function ReportDiffBlock({ lines }: { lines: string[] }) {
  return (
    <pre className="report-diff">
      {lines.map((line, index) => (
        <span className={diffLineClass(line)} key={`${index}:${line}`}>
          {line}
        </span>
      ))}
    </pre>
  );
}

function diffLineClass(line: string) {
  if (line.startsWith("+") && !line.startsWith("+++")) return "diff-add";
  if (line.startsWith("-") && !line.startsWith("---")) return "diff-remove";
  if (line.startsWith("@@")) return "diff-hunk";
  return "diff-context";
}
