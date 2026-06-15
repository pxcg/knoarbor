type LoadingBlockProps = {
  title: string;
  copy?: string;
  compact?: boolean;
};

export function LoadingBlock({ title, copy, compact = false }: LoadingBlockProps) {
  return (
    <div className={`loading-block ${compact ? "compact" : ""}`} role="status" aria-live="polite">
      <span className="loading-spinner" aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        {copy && <p>{copy}</p>}
      </div>
    </div>
  );
}
