import type { ChatNode, NestedTranscript, SubagentExecutionItem, TranscriptBlock } from "./chatState";

export type SubagentTab = {
  agentCode: string;
  status: SubagentExecutionItem["status"];
  runIds: string[];
};

export type SubagentSelection = string;

export type SubagentRunTarget = {
  task: SubagentExecutionItem;
  transcript?: NestedTranscript;
  live: boolean;
};

export type SubagentTarget = {
  runs: SubagentRunTarget[];
};

export function collectSubagentTabs(nodes: ChatNode[]): SubagentTab[] {
  const tabs = new Map<string, { status: SubagentExecutionItem["status"]; runIds: Set<string> }>();
  for (const { task } of subagentRuns(nodes)) {
    const current = tabs.get(task.agentCode);
    tabs.set(task.agentCode, {
      status: mergeSubagentStatus(current?.status, task.status),
      runIds: new Set([...(current?.runIds ?? []), task.runId]),
    });
  }
  return Array.from(tabs, ([agentCode, tab]) => ({
    agentCode,
    status: tab.status,
    runIds: Array.from(tab.runIds),
  }));
}

export function findSubagentTarget(nodes: ChatNode[], selection: SubagentSelection): SubagentTarget | null {
  const runs = new Map<string, SubagentRunTarget>();
  for (const { task, transcript } of subagentRuns(nodes, true)) {
    if (task.agentCode !== selection || runs.has(task.runId)) continue;
    runs.set(task.runId, { task, transcript, live: task.status === "running" });
  }
  const orderedRuns = Array.from(runs.values()).reverse();
  return orderedRuns.length ? { runs: orderedRuns } : null;
}

export function subagentStatusColor(status: SubagentExecutionItem["status"]): "red" | "green" | "amber" {
  if (status === "failed" || status === "canceled") return "red";
  return status === "completed" ? "green" : "amber";
}

export function subordinateStatusLabel(status: SubagentExecutionItem["status"]) {
  switch (status) {
    case "running":
      return "Running";
    case "completed":
      return "Completed";
    case "canceled":
      return "Canceled";
    case "failed":
      return "Failed";
  }
}

function mergeSubagentStatus(
  current: SubagentExecutionItem["status"] | undefined,
  next: SubagentExecutionItem["status"],
): SubagentExecutionItem["status"] {
  if (current === "running" || next === "running") return "running";
  return next;
}

function* subagentRuns(nodes: ChatNode[], reverse = false): Generator<SubagentRunTarget> {
  const start = reverse ? nodes.length - 1 : 0;
  const end = reverse ? -1 : nodes.length;
  const step = reverse ? -1 : 1;

  for (let i = start; i !== end; i += step) {
    const node = nodes[i];
    if (node.kind !== "agent") continue;
    yield* subagentRunsFromBlocks(node.blocks, reverse);
  }
}

function* subagentRunsFromBlocks(blocks: TranscriptBlock[], reverse: boolean): Generator<SubagentRunTarget> {
  const start = reverse ? blocks.length - 1 : 0;
  const end = reverse ? -1 : blocks.length;
  const step = reverse ? -1 : 1;

  for (let i = start; i !== end; i += step) {
    const block = blocks[i];
    const task = subagentTask(block);
    if (!task?.agentCode || !task.runId) continue;
    yield {
      task,
      transcript: block.kind === "tool" ? block.nested : undefined,
      live: task.status === "running",
    };
  }
}

function subagentTask(block: TranscriptBlock): SubagentExecutionItem | undefined {
  if (block.kind === "subagent") return block;
  if (block.kind === "tool") return block.subagentTask;
  return undefined;
}
