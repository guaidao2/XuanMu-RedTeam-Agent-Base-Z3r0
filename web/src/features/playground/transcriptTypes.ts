import type {
  AgentContentEvent,
  AgentInputPart,
  SubagentTaskEvent,
  TextCompleteEvent,
  ThinkingCompleteEvent,
  ToolCallEvent,
  ToolResultEvent,
} from "../../shared/api/types";

export type ThinkingItem = {
  kind: "thinking";
  id: string;
  segmentId: ThinkingCompleteEvent["segment_id"];
  text: ThinkingCompleteEvent["text"];
  complete: boolean;
};

export type TextItem = {
  kind: "text";
  id: string;
  segmentId: TextCompleteEvent["segment_id"];
  text: TextCompleteEvent["text"];
  complete: boolean;
};

export type ToolExecutionItem = {
  kind: "tool";
  id: string;
  callId: ToolCallEvent["call_id"];
  name: ToolCallEvent["name"];
  arguments: NonNullable<ToolCallEvent["arguments"]>;
  output: ToolResultEvent["output"];
  isError: ToolResultEvent["is_error"];
  resolved: boolean;
  nested?: NestedTranscript;
  subagentTask?: SubagentExecutionItem;
};

export type SubagentExecutionItem = {
  kind: "subagent";
  id: SubagentTaskEvent["run_id"];
  createdAt: SubagentTaskEvent["created_at"];
  runId: SubagentTaskEvent["run_id"];
  parentAgentCode: SubagentTaskEvent["parent_agent_code"];
  parentAgentInstanceId: SubagentTaskEvent["parent_agent_instance_id"];
  agentCode: SubagentTaskEvent["agent_code"];
  nestedCallId: SubagentTaskEvent["nested_call_id"];
  status: SubagentTaskEvent["status"];
  resultPreview: SubagentTaskEvent["result_preview"];
  errorPreview: SubagentTaskEvent["error_preview"];
  resultChars: SubagentTaskEvent["result_chars"];
  errorChars: SubagentTaskEvent["error_chars"];
  truncated: SubagentTaskEvent["truncated"];
  progress: SubagentTaskEvent["progress"];
};

export type ErrorItem = { kind: "error"; id: string; message: string };
export type ExecutionItem = ToolExecutionItem | SubagentExecutionItem;
export type TranscriptBlock = ThinkingItem | TextItem | ExecutionItem | ErrorItem;

export type AgentTranscript = {
  createdAt: AgentContentEvent["created_at"] | "";
  agentName: string;
  blocks: TranscriptBlock[];
};

export type NestedTranscript = AgentTranscript;

export type ChatNode =
  | {
      kind: "user";
      id: string;
      createdAt: AgentContentEvent["created_at"];
      content: AgentInputPart[];
      displayText: string;
      targetAgentCode: string;
    }
  | ({ kind: "agent"; id: string } & AgentTranscript);

export type ChatState = {
  nodes: ChatNode[];
  streaming: boolean;
  pendingNested: Record<string, AgentContentEvent[]>;
  liveFrom: number | null;
};

export type StreamingItem = ThinkingItem | TextItem;
