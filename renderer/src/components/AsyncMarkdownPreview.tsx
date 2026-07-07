import { lazy, Suspense } from "react";

import type { MarkdownPreviewProps } from "./MarkdownPreview";

const MarkdownPreview = lazy(() => import("./MarkdownPreview").then((module) => ({ default: module.MarkdownPreview })));

export function AsyncMarkdownPreview(props: MarkdownPreviewProps) {
  return (
    <Suspense fallback={<div className="markdown-rendered markdown-loading">Loading content…</div>}>
      <MarkdownPreview {...props} />
    </Suspense>
  );
}
