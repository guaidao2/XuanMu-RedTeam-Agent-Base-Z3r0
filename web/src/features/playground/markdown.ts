export function normalizeMarkdownForRender(text: string, streaming: boolean) {
  const normalized = text.replace(/\r\n?/g, "\n");
  if (!streaming) return normalized;

  const openFence = getOpenMarkdownFence(normalized);
  if (!openFence) return normalized;
  const markdown = openFence.language === "mermaid" ? downgradeOpenFenceLanguage(normalized, openFence) : normalized;
  return `${markdown.endsWith("\n") ? markdown : `${markdown}\n`}${openFence.marker}`;
}

function getOpenMarkdownFence(markdown: string) {
  let open: MarkdownFence | null = null;
  const lines = markdown.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const fence = markdownFence(line);
    if (!fence) continue;
    if (!open) {
      open = { ...fence, lineIndex: index };
      continue;
    }
    if (fence.marker[0] === open.marker[0] && fence.marker.length >= open.marker.length) {
      open = null;
    }
  }
  return open;
}

type MarkdownFence = {
  marker: string;
  language: string;
  lineIndex: number;
};

function markdownFence(line: string): Omit<MarkdownFence, "lineIndex"> | null {
  const match = line.match(/^\s{0,3}(`{3,}|~{3,})(.*)$/);
  if (!match) return null;
  return {
    marker: match[1],
    language: match[2].trim().split(/\s+/, 1)[0]?.toLowerCase() ?? "",
  };
}

function downgradeOpenFenceLanguage(markdown: string, fence: MarkdownFence) {
  const lines = markdown.split("\n");
  lines[fence.lineIndex] = lines[fence.lineIndex].replace(/^(\s{0,3}(?:`{3,}|~{3,}))\s*mermaid\b/i, "$1 text");
  return lines.join("\n");
}
