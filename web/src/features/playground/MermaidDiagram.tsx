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
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setResult(null);

    // 先检查是否是有效的 mermaid 代码（简单校验）
    const trimmed = source.trim();
    if (!trimmed || !/^(graph|flowchart|sequence|class|state|er|pie|gantt|journey|git|mindmap|timeline|block|packet|quadrant|requirement|architecture|sankey|xychart|c4|zenuml|sprite|kanban|other|gitgraph|ganttdiagram)/i.test(trimmed)) {
      // 不是有效的 mermaid 语法，直接静默不渲染
      setFailed(true);
      return;
    }

    mermaid
      .render(renderId, source)
      .then(({ svg }) => {
        if (!cancelled) {
          // mermaid v11 有时渲染成功但内容含错误信息，检查并过滤
          if (svg.includes('mermaid-error') || svg.includes('Syntax error') || svg.includes('diagram-error')) {
            return;
          }
          setResult({ svg });
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [renderId, source]);

  if (failed) {
    return null;
  }

  if (result && "error" in result) {
    return null;
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
