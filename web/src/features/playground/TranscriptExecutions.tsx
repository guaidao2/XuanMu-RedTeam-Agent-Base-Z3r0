import { Button, Tag } from "@douyinfe/semi-ui";
import { ChevronDown, ChevronRight, GitBranch, PanelRightOpen, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { NestedTranscript, SubagentExecutionItem, ToolExecutionItem } from "./chatState";
import { cx } from "../../shared/lib/className";
import { subagentStatusColor, subordinateStatusLabel, type SubagentSelection } from "./subagentView";
import { emptyAgentTranscript, transcriptHasRunningExecution, transcriptItemCount, type ToolBlock } from "./transcriptView";

export function ToolGroup({
  items,
  live,
  selectedSubagent,
  onOpenSubagent,
  allowSubagentOpen,
  header,
}: {
  items: ToolBlock[];
  live: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
  allowSubagentOpen: boolean;
  header: (props: PanelHeaderProps) => ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className={cx("transcript-panel transcript-panel-tools", live && "transcript-panel-live")}>
      {header({
        icon: <Wrench size={13} />,
        title: "Tools",
        count: items.length,
        open,
        onToggle: () => setOpen((next) => !next),
      })}
      {open ? (
        <div className="tool-list">
          {items.map((block) =>
            block.kind === "tool" ? (
              <ToolExecutionBlock
                key={`${block.kind}:${block.id}`}
                item={block}
                live={live}
                selectedSubagent={allowSubagentOpen ? selectedSubagent : null}
                onOpenSubagent={allowSubagentOpen ? onOpenSubagent : undefined}
                allowSubagentOpen={allowSubagentOpen}
              />
            ) : (
              <SubagentExecutionBlock
                key={`${block.kind}:${block.id}`}
                item={block}
                selected={allowSubagentOpen && selectedSubagent === block.agentCode}
                onOpenSubagent={allowSubagentOpen ? onOpenSubagent : undefined}
              />
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}

type PanelHeaderProps = {
  icon: ReactNode;
  title: string;
  count?: number;
  open: boolean;
  onToggle: () => void;
};

function ToolExecutionBlock({
  item,
  live,
  selectedSubagent,
  onOpenSubagent,
  allowSubagentOpen,
}: {
  item: ToolExecutionItem;
  live: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
  allowSubagentOpen: boolean;
}) {
  const [open, setOpen] = useState(false);
  const detailRef = useRef<HTMLDivElement | null>(null);
  const nestedActive = !!item.nested && transcriptHasRunningExecution(item.nested);
  const status = toolExecutionStatus(item);
  const displayName = item.name;

  useEffect(() => {
    if (open) detailRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [open]);

  return (
    <div className={cx("execution-row", `execution-row-${status.tone}`)}>
      <button
        type="button"
        className="execution-row-head"
        aria-expanded={open}
        onClick={() => setOpen((next) => !next)}
      >
        <ExecutionName name={displayName} />
        <Tag size="small" color={status.color}>{status.label}</Tag>
        <span className="execution-row-toggle">{open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
      </button>
      {open ? (
        <div ref={detailRef} className="execution-row-detail">
          <JsonExecutionSection label="Arguments" value={item.arguments} />
          {allowSubagentOpen && (item.nested || item.subagentTask) ? (
            <NestedTranscriptPanel
              nested={item.nested ?? emptyAgentTranscript()}
              task={item.subagentTask}
              live={live && (nestedActive || item.subagentTask?.status === "running")}
              selected={selectedSubagent === item.subagentTask?.agentCode}
              onOpenSubagent={onOpenSubagent}
            />
          ) : null}
          {item.resolved ? (
            <ToolOutputSection output={item.output} tone={item.isError ? "error" : undefined} />
          ) : (
            <ExecutionSection label="Output" body="Pending..." />
          )}
        </div>
      ) : null}
    </div>
  );
}

function SubagentExecutionBlock({
  item,
  selected,
  onOpenSubagent,
}: {
  item: SubagentExecutionItem;
  selected: boolean;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  return (
    <div className={cx("execution-row execution-row-subagent", `execution-row-subagent-${item.status}`, selected && "execution-row-selected")}>
      <div className="execution-row-head execution-row-head-static">
        <ExecutionName name={item.agentCode || "subagent"} />
        <SubagentStatusTag status={item.status} />
        <OpenSubagentButton agentCode={item.agentCode} onOpenSubagent={onOpenSubagent} />
      </div>
    </div>
  );
}

function NestedTranscriptPanel({
  nested,
  task,
  live,
  selected,
  onOpenSubagent,
}: {
  nested: NestedTranscript;
  task?: SubagentExecutionItem;
  live: boolean;
  selected: boolean;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  const itemCount = transcriptItemCount(nested);
  if (itemCount === 0 && !task) return null;

  return (
    <div className={cx("nested-panel", live && "nested-panel-live", selected && "nested-panel-selected")}>
      <div className="nested-panel-head">
        <GitBranch size={13} />
        <span className="nested-panel-title">
          Subagent{task?.agentCode ? ` - ${task.agentCode}` : nested.agentName ? ` - ${nested.agentName}` : ""}
        </span>
        {task ? <SubagentStatusTag status={task.status} /> : null}
        <span className="nested-panel-count">{itemCount}</span>
        <OpenSubagentButton agentCode={task?.agentCode} onOpenSubagent={onOpenSubagent} />
      </div>
    </div>
  );
}

function ExecutionName({ name }: { name: string }) {
  return <span className="execution-row-name" title={name}>{name}</span>;
}

function OpenSubagentButton({
  agentCode,
  onOpenSubagent,
}: {
  agentCode?: string;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  if (!agentCode || !onOpenSubagent) return null;
  return (
    <Button
      className="execution-row-expand"
      icon={<PanelRightOpen size={13} />}
      size="small"
      theme="borderless"
      type="tertiary"
      onClick={() => onOpenSubagent(agentCode)}
    >
      Open
    </Button>
  );
}

export function SubagentStatusTag({ status }: { status: SubagentExecutionItem["status"] }) {
  return <Tag size="small" color={subagentStatusColor(status)}>{subordinateStatusLabel(status)}</Tag>;
}

export function ExecutionSection({ label, body, tone }: { label: string; body: string; tone?: "error" }) {
  return (
    <div className={cx("execution-section", tone && `execution-section-${tone}`)}>
      <div className="execution-section-label">{label}</div>
      <pre className="execution-section-body">{body}</pre>
    </div>
  );
}

function JsonExecutionSection({ label, value, tone }: { label: string; value: unknown; tone?: "error" }) {
  const json = useMemo(() => tokenizeJson(stringifyJson(value)), [value]);
  return (
    <div className={cx("execution-section", tone && `execution-section-${tone}`)}>
      <div className="execution-section-label">{label}</div>
      <pre className="execution-section-body execution-json-body">
        <code>
          {json.map((token, index) => (
            token.tone ? (
              <span key={`${index}:${token.text}`} className={`json-token-${token.tone}`}>
                {token.text}
              </span>
            ) : token.text
          ))}
        </code>
      </pre>
    </div>
  );
}

function ToolOutputSection({ output, tone }: { output: string; tone?: "error" }) {
  const parsed = useMemo(() => parseJsonText(output), [output]);
  if (!parsed.ok) {
    return <ExecutionSection label="Output" body={output || "(empty)"} tone={tone} />;
  }
  return <JsonExecutionSection label="Output" value={parsed.value} tone={tone} />;
}

function toolExecutionStatus(item: ToolExecutionItem): { label: string; color: "red" | "green" | "amber"; tone: "error" | "ok" | "running" } {
  if (item.resolved && item.isError) return { label: "Failed", color: "red", tone: "error" };
  if (item.subagentTask?.status === "failed" || item.subagentTask?.status === "canceled") {
    return { label: subordinateStatusLabel(item.subagentTask.status), color: "red", tone: "error" };
  }
  if (!item.resolved || item.subagentTask?.status === "running") return { label: "Running", color: "amber", tone: "running" };
  return { label: "Done", color: "green", tone: "ok" };
}

function parseJsonText(output: string): { ok: true; value: unknown } | { ok: false } {
  const text = output.trim();
  if (!text) return { ok: true, value: "" };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}

function stringifyJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2) ?? JSON.stringify(String(value));
  } catch {
    return JSON.stringify(String(value));
  }
}

type JsonToken = { text: string; tone?: "key" | "string" | "number" | "boolean" | "null" };

const JSON_TOKEN_PATTERN = /"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\btrue\b|\bfalse\b|\bnull\b/g;

function tokenizeJson(source: string): JsonToken[] {
  const tokens: JsonToken[] = [];
  let cursor = 0;
  for (const match of source.matchAll(JSON_TOKEN_PATTERN)) {
    const text = match[0];
    const index = match.index ?? cursor;
    if (index > cursor) tokens.push({ text: source.slice(cursor, index) });
    tokens.push({ text, tone: jsonTokenTone(source, index, text) });
    cursor = index + text.length;
  }
  if (cursor < source.length) tokens.push({ text: source.slice(cursor) });
  return tokens;
}

function jsonTokenTone(source: string, index: number, text: string): JsonToken["tone"] {
  if (text.startsWith("\"")) {
    return /^\s*:/.test(source.slice(index + text.length)) ? "key" : "string";
  }
  if (text === "true" || text === "false") return "boolean";
  if (text === "null") return "null";
  return "number";
}
