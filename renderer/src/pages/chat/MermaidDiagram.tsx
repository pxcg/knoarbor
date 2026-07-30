import { useEffect, useId, useState } from "react";

type MermaidDiagramProps = {
  chart: string;
};

type MermaidState =
  | { status: "rendering"; svg?: undefined; error?: undefined }
  | { status: "ready"; svg: string; error?: undefined }
  | { status: "error"; svg?: undefined };

export function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const rawId = useId();
  const [state, setState] = useState<MermaidState>({ status: "rendering" });

  useEffect(() => {
    let cancelled = false;
    const renderId = `knoarbor-mermaid-${rawId.replace(/[^a-zA-Z0-9_-]/g, "")}-${hashChart(chart)}`;

    async function renderDiagram() {
      setState({ status: "rendering" });
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: {
            primaryColor: "#e8f2ed",
            primaryTextColor: "#17231c",
            primaryBorderColor: "#9fc6aa",
            lineColor: "#6b7c72",
            secondaryColor: "#ffffff",
            tertiaryColor: "#f7faf8",
            fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
          },
        });
        const result = await mermaid.render(renderId, chart);
        if (!cancelled) setState({ status: "ready", svg: result.svg });
      } catch (error) {
        console.error("Mermaid rendering failed", error);
        if (!cancelled) setState({ status: "error" });
      }
    }

    void renderDiagram();
    return () => {
      cancelled = true;
    };
  }, [chart, rawId]);

  if (state.status === "ready") {
    return (
      <figure className="chat-mermaid-diagram">
        <div dangerouslySetInnerHTML={{ __html: state.svg }} />
      </figure>
    );
  }

  if (state.status === "error") {
    return (
      <pre className="chat-mermaid-fallback">
        <code>{chart}</code>
      </pre>
    );
  }

  return (
    <figure className="chat-mermaid-diagram loading">
      <span>Rendering diagram...</span>
    </figure>
  );
}

function hashChart(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash.toString(36);
}
