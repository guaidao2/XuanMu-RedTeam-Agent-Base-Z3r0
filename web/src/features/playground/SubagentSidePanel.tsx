import { Button } from "@douyinfe/semi-ui";
import { GitBranch, X } from "lucide-react";
import { useMemo } from "react";
import type { AgentInfo } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";
import type { ChatNode, SubagentExecutionItem } from "./chatState";
import {
  findSubagentTarget,
  type SubagentSelection,
  type SubagentTab,
  type SubagentTarget,
} from "./subagentView";
import { MessageScrollPanel } from "./MessageScrollPanel";
import { TranscriptContent } from "./Transcript";
import { ExecutionSection, SubagentStatusTag } from "./TranscriptExecutions";

export function SubagentSidePanel({
  nodes,
  tabs,
  agents,
  selection,
  onSelect,
  onClose,
}: {
  nodes: ChatNode[];
  tabs: SubagentTab[];
  agents: AgentInfo[];
  selection: SubagentSelection | null;
  onSelect: (selection: SubagentSelection) => void;
  onClose: () => void;
}) {
  const target = useMemo(
    () => selection ? findSubagentTarget(nodes, selection) : null,
    [nodes, selection],
  );
  const open = Boolean(selection);
  const agentNameByCode = useMemo(
    () => new Map(agents.map((agent) => [agent.code, agent.name])),
    [agents],
  );
  const selectionKey = selection ?? "";

  return (
    <aside className={cx("subagent-side-panel", open && "subagent-side-panel-open")} aria-hidden={!open}>
      <div className="subagent-side-panel-inner">
        <div className="subagent-side-header">
          <div className="subagent-side-heading">
            <GitBranch size={15} />
            <span>Subagents</span>
          </div>
          {tabs.length > 0 ? (
            <div className="subagent-side-tabs" role="tablist" aria-label="Subagent messages">
              {tabs.map((tab) => {
                const active = selection === tab.agentCode;
                return (
                  <button
                    key={tab.agentCode}
                    type="button"
                    className={cx("subagent-tab", active && "subagent-tab-active")}
                    role="tab"
                    aria-selected={active}
                    onClick={() => onSelect(tab.agentCode)}
                  >
                    <span className="subagent-tab-name" title={tab.agentCode || "subagent"}>
                      {agentNameByCode.get(tab.agentCode) || tab.agentCode || "Subagent"}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : null}
          <Button icon={<X size={14} />} theme="borderless" type="tertiary" onClick={onClose} aria-label="Close subagent panel" />
        </div>
        <MessageScrollPanel
          ariaLabel="Subagent messages"
          className="subagent-side-body-shell"
          contentClassName="subagent-side-body"
          enabled={open}
          resetKey={selectionKey}
          scrollButtonClassName="subagent-scroll-tail-floating"
          watch={[target]}
        >
          {(tailRef) => (
            <>
              {target ? <SubagentTargetView target={target} /> : <div className="transcript-empty">Subagent output is no longer available.</div>}
              <div ref={tailRef} className="chat-tail" />
            </>
          )}
        </MessageScrollPanel>
      </div>
    </aside>
  );
}

function SubagentTargetView({ target }: { target: SubagentTarget }) {
  return (
    <div className="subagent-transcript-view">
      {target.runs.map((run) => (
        <SubagentRunView key={run.task.runId} run={run} />
      ))}
    </div>
  );
}

function SubagentRunView({ run }: { run: SubagentTarget["runs"][number] }) {
  const body = run.transcript ? (
    <TranscriptContent
      transcript={run.transcript}
      live={run.live}
      emptyText="No subagent output yet."
      allowSubagentOpen={false}
    />
  ) : (
    <SubagentFallbackResult task={run.task} />
  );

  return (
    <div className="subagent-task-view">
      <SubagentTaskMeta item={run.task} />
      {body}
    </div>
  );
}

function SubagentFallbackResult({ task }: { task: SubagentExecutionItem }) {
  const failed = task.status === "failed" || task.status === "canceled";
  const label = task.status === "running" ? "Progress" : failed ? "Error Preview" : "Result Preview";
  const body = task.status === "running"
    ? task.progress || "Running"
    : previewBody(task);

  return <ExecutionSection label={label} body={body} tone={failed ? "error" : undefined} />;
}

function previewBody(task: SubagentExecutionItem): string {
  const body = task.resultPreview || task.errorPreview || "(empty)";
  return task.truncated ? `${body}\n\n[Preview truncated]` : body;
}

function SubagentTaskMeta({ item }: { item: SubagentExecutionItem }) {
  return (
    <div className="subagent-task-meta">
      <SubagentStatusTag status={item.status} />
      <span>{item.runId}</span>
      {item.status === "running" && item.progress ? <span>{item.progress}</span> : null}
    </div>
  );
}
