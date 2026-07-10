import { isValidElement, memo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { MermaidDiagram } from "./MermaidDiagram";

const MARKDOWN_PLUGINS = [remarkGfm, remarkBreaks];

const MARKDOWN_COMPONENTS: Components = {
  pre({ children, node: _node, ...props }) {
    const mermaidSource = mermaidBlockSource(children);
    if (mermaidSource !== null) return <MermaidDiagram source={mermaidSource} />;
    return <pre {...props}>{children}</pre>;
  },
};

function MarkdownRendererComponent({ markdown }: { markdown: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={MARKDOWN_PLUGINS}
      components={MARKDOWN_COMPONENTS}
    >
      {markdown}
    </ReactMarkdown>
  );
}

export const MarkdownRenderer = memo(MarkdownRendererComponent);

function mermaidBlockSource(children: ReactNode) {
  const child = Array.isArray(children) ? children[0] : children;
  if (!isValidElement<{ className?: string; children?: ReactNode }>(child)) return null;
  if (child.type !== "code" || !child.props.className?.split(/\s+/).includes("language-mermaid")) return null;
  return textContent(child.props.children).replace(/\n$/, "");
}

function textContent(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textContent).join("");
  return "";
}
