import mermaid from "mermaid";
import { memo, useEffect, useId, useMemo, useState } from "react";

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
  theme: "base",
  themeVariables: {
    primaryColor: "#161f2e",
    primaryTextColor: "#f8fafc",
    primaryBorderColor: "#9cc7cb",
    lineColor: "#9fb2c7",
    secondaryColor: "#1d2838",
    tertiaryColor: "#0b1018",
    noteBkgColor: "#2a1720",
    noteTextColor: "#f8fafc",
  },
});

export const MermaidDiagram = memo(function MermaidDiagram({ source }: { source: string }) {
  const reactId = useId();
  const renderId = useMemo(() => `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`, [reactId]);
  const [result, setResult] = useState<{ svg: string } | { error: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setResult(null);

    mermaid
      .render(renderId, source)
      .then(({ svg }) => {
        if (!cancelled) setResult({ svg });
      })
      .catch((error: unknown) => {
        if (!cancelled) setResult({ error: error instanceof Error ? error.message : String(error) });
      });

    return () => {
      cancelled = true;
    };
  }, [renderId, source]);

  if (result && "error" in result) {
    return (
      <div className="mermaid-diagram mermaid-diagram-error" title={result.error}>
        <div className="mermaid-error-label">Mermaid render failed</div>
        <pre>
          <code className="language-mermaid">{source}</code>
        </pre>
      </div>
    );
  }

  return (
    <div
      className="mermaid-diagram"
      aria-busy={!result}
      aria-label="Mermaid diagram"
      dangerouslySetInnerHTML={result && "svg" in result ? { __html: result.svg } : undefined}
    />
  );
});
