import type {
  AgentTranscript,
  ErrorItem,
  ExecutionItem,
  SubagentExecutionItem,
  TextItem,
  ThinkingItem,
  ToolExecutionItem,
} from "./chatState";

type TranscriptItem = AgentTranscript["blocks"][number];
export type ToolBlock = ToolExecutionItem | SubagentExecutionItem;
export type ContentBlock = TextItem | ErrorItem;
export type TranscriptRenderSegment =
  | { kind: "thinking"; id: "thinking"; items: ThinkingItem[] }
  | { kind: "tools"; id: "tools"; items: ToolBlock[] }
  | { kind: "content"; id: string; block: ContentBlock };

export function buildTranscriptSegments(blocks: TranscriptItem[]): TranscriptRenderSegment[] {
  const thinkingItems: ThinkingItem[] = [];
  const toolItems: ToolBlock[] = [];
  const contentSegments: TranscriptRenderSegment[] = [];

  for (const block of blocks) {
    if (block.kind === "thinking") {
      thinkingItems.push(block);
    } else if (isToolBlock(block)) {
      toolItems.push(block);
    } else {
      contentSegments.push({ kind: "content", id: `${block.kind}:${block.id}`, block });
    }
  }

  const segments: TranscriptRenderSegment[] = [];
  if (thinkingItems.length) segments.push({ kind: "thinking", id: "thinking", items: thinkingItems });
  if (toolItems.length) segments.push({ kind: "tools", id: "tools", items: toolItems });
  return [...segments, ...contentSegments];
}

export function emptyAgentTranscript(): AgentTranscript {
  return {
    createdAt: "",
    agentName: "",
    blocks: [],
  };
}

export function isTranscriptEmpty(transcript: AgentTranscript) {
  return transcript.blocks.length === 0;
}

export function activeThinkingItemId(blocks: TranscriptItem[]) {
  return [...blocks].reverse().find((block): block is ThinkingItem => block.kind === "thinking" && !block.complete)?.id ?? "";
}

export function activeTextItemId(blocks: TranscriptItem[]) {
  return [...blocks].reverse().find((block): block is TextItem => block.kind === "text" && !block.complete)?.id ?? "";
}

export function transcriptHasRunningExecution(transcript: AgentTranscript): boolean {
  return transcript.blocks.some((block) => isToolBlock(block) && isExecutionRunning(block));
}

export function transcriptItemCount(transcript: AgentTranscript) {
  return transcript.blocks.length;
}

function isToolBlock(block: TranscriptItem): block is ToolBlock {
  return block.kind === "tool" || block.kind === "subagent";
}

function isExecutionRunning(item: ExecutionItem) {
  if (item.kind === "tool") {
    return !item.resolved || item.subagentTask?.status === "running" || Boolean(item.nested && transcriptHasRunningExecution(item.nested));
  }
  return item.status === "running";
}
