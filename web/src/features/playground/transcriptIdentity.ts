import type { AgentContentEvent, AgentInputPart } from "../../shared/api/types";
import { stableJson } from "../../shared/lib/json";
import type {
  AgentTranscript,
  ChatNode,
  StreamingItem,
  ToolExecutionItem,
  TranscriptBlock,
} from "./transcriptTypes";

export function contentSignature(content: AgentInputPart[]): string {
  return content.map((part) => {
    if (part.type === "text") return `text:${part.text}`;
    return `image:${part.media_type}:${part.data.length}:${part.data.slice(0, 64)}`;
  }).join("\n");
}

export function transcriptHasEvent(transcript: AgentTranscript, event: AgentContentEvent): boolean {
  switch (event.type) {
    case "thinking_delta":
      return hasCoveredCompletedText(transcript.blocks, "thinking", event.text);
    case "thinking_complete":
      return hasCoveredCompletedText(transcript.blocks, "thinking", event.text);
    case "text_delta":
      return hasCoveredCompletedText(transcript.blocks, "text", event.text);
    case "text_complete":
      return hasCoveredCompletedText(transcript.blocks, "text", event.text);
    case "tool_call":
      return findToolBlockIndex(transcript.blocks, event.call_id, event.name, event.arguments ?? {}) !== -1;
    case "tool_result": {
      const index = findToolBlockIndex(transcript.blocks, event.call_id);
      const block = index === -1 ? null : transcript.blocks[index];
      return Boolean(block?.kind === "tool" && block.resolved && block.output === event.output && block.isError === event.is_error);
    }
    case "subagent_task":
      return transcript.blocks.some((block) => (
        block.kind === "subagent"
        && block.runId === event.run_id
        && block.status === event.status
        && block.progress === event.progress
        && block.resultPreview === event.result_preview
        && block.errorPreview === event.error_preview
        && block.resultChars === event.result_chars
        && block.errorChars === event.error_chars
        && block.truncated === event.truncated
      ));
    default:
      return false;
  }
}

export function findToolBlockIndex(
  blocks: TranscriptBlock[],
  callId: string,
  name = "",
  argumentsValue: Record<string, unknown> | null = null,
): number {
  const byCallId = blocks.findIndex((block) => block.kind === "tool" && block.callId === callId);
  if (byCallId !== -1 || !name || argumentsValue === null) return byCallId;
  const signature = toolSignature(name, argumentsValue);
  return blocks.findIndex((block) => block.kind === "tool" && toolSignature(block.name, block.arguments) === signature);
}

export function hasCoveredCompletedText(blocks: TranscriptBlock[], kind: StreamingItem["kind"], text: string): boolean {
  if (!text) return false;
  return blocks.some((block) => (
    block.kind === kind && block.complete && (block.text === text || block.text.startsWith(text))
  ));
}

export function findCompletedTextIndex(blocks: TranscriptBlock[], kind: StreamingItem["kind"], text: string, exceptIndex = -1): number {
  if (!text) return -1;
  return blocks.findIndex((block, index) => (
    index !== exceptIndex && block.kind === kind && block.complete && block.text === text
  ));
}

export function findStreamingBlockIndex(blocks: TranscriptBlock[], kind: StreamingItem["kind"], segmentId: string): number {
  for (let index = blocks.length - 1; index >= 0; index -= 1) {
    const block = blocks[index];
    if (block.kind === kind && block.segmentId === segmentId) return index;
  }
  return -1;
}

export function hasToolCall(nodes: ChatNode[], callId: string): boolean {
  return nodes.some((node) => node.kind === "agent" && findToolBlockIndex(node.blocks, callId) !== -1);
}

export function toolSignature(name: string, argumentsValue: Record<string, unknown>): string {
  return `${name}\u001f${stableJson(argumentsValue)}`;
}

export function isToolBlock(block: TranscriptBlock): block is ToolExecutionItem {
  return block.kind === "tool";
}
