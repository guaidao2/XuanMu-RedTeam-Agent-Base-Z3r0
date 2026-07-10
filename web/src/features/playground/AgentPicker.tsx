import { Bot } from "lucide-react";
import { useEffect, useRef } from "react";
import type { AgentInfo } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";

type AgentPickerProps = {
  agents: AgentInfo[];
  highlightedIndex: number;
  disabled?: boolean;
  disabledReason?: string;
  onSelect: (agent: AgentInfo) => void;
  onHover: (index: number) => void;
};

export function AgentPicker({
  agents,
  highlightedIndex,
  disabled = false,
  disabledReason = "",
  onSelect,
  onHover,
}: AgentPickerProps) {
  const activeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [highlightedIndex]);

  if (agents.length === 0) {
    return (
      <div className="agent-picker agent-picker-empty">
        <Bot size={14} />
        <span>No agents available</span>
      </div>
    );
  }

  return (
    <div className="agent-picker" role="listbox" aria-label="Pick an agent">
      <div className="agent-picker-hint">Pick an agent · ↑↓ to navigate · Enter or Tab to confirm</div>
      {agents.map((agent, index) => {
        const active = index === highlightedIndex;
        const description = disabled ? disabledReason : agent.description;
        return (
          <button
            key={agent.code}
            ref={active ? activeRef : null}
            type="button"
            role="option"
            aria-selected={active}
            disabled={disabled}
            title={description || agent.name}
            className={cx("agent-picker-row", active && "agent-picker-row-active")}
            onMouseDown={(event) => event.preventDefault()}
            onMouseEnter={() => onHover(index)}
            onClick={() => !disabled && onSelect(agent)}
          >
            <span className="agent-picker-avatar"><Bot size={14} /></span>
            <span className="agent-picker-body">
              <span className="agent-picker-name">{agent.name}</span>
              <span className="agent-picker-code">{agent.code}</span>
            </span>
            {description ? <span className="agent-picker-desc">{description}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
