import { useEffect, useMemo, useRef, useState } from "react";
import type { ChatState } from "./chatState";
import {
  collectSubagentTabs,
  type SubagentTab,
  type SubagentSelection,
} from "./subagentView";

export function useSubagentPanel(chatState: ChatState, scopeKey: string | null) {
  const [selectedSubagent, setSelectedSubagent] = useState<SubagentSelection | null>(null);
  const knownRunsRef = useRef<Set<string>>(new Set());
  const suppressedAutoOpenRunIdsRef = useRef<Set<string>>(new Set());

  const tabs = useMemo(() => collectSubagentTabs(chatState.nodes), [chatState.nodes]);

  useEffect(() => {
    knownRunsRef.current = new Set();
    suppressedAutoOpenRunIdsRef.current = new Set();
    setSelectedSubagent(null);
  }, [scopeKey]);

  useEffect(() => {
    const knownRuns = knownRunsRef.current;
    const suppressedRunIds = suppressedAutoOpenRunIdsRef.current;
    let newestRunning: SubagentTab | null = null;

    for (const tab of tabs) {
      for (const runId of tab.runIds) {
        if (knownRuns.has(runId)) continue;
        knownRuns.add(runId);
        if (tab.status === "running") newestRunning = tab;
      }
    }

    const latestRunning = latestRunningTab(tabs);
    const newestRunningRunId = newestRunning ? latestRunId(newestRunning) : null;
    const latestRunningRunId = latestRunning ? latestRunId(latestRunning) : null;

    if (selectedSubagent && !tabs.some((tab) => tab.agentCode === selectedSubagent)) {
      setSelectedSubagent(latestRunning?.agentCode ?? tabs[tabs.length - 1]?.agentCode ?? null);
      return;
    }

    if (newestRunning && newestRunningRunId && !suppressedRunIds.has(newestRunningRunId)) {
      setSelectedSubagent(newestRunning.agentCode);
      return;
    }

    if (!selectedSubagent && latestRunning && latestRunningRunId && !suppressedRunIds.has(latestRunningRunId)) {
      setSelectedSubagent(latestRunning.agentCode);
    }
  }, [selectedSubagent, tabs]);

  const closeSubagentPanel = () => {
    const latestRunning = latestRunningTab(tabs);
    const runId = latestRunning ? latestRunId(latestRunning) : null;
    if (runId) suppressedAutoOpenRunIdsRef.current.add(runId);
    setSelectedSubagent(null);
  };

  return {
    selectedSubagent,
    setSelectedSubagent,
    subagentTabs: tabs,
    closeSubagentPanel,
  };
}

function latestRunningTab(tabs: SubagentTab[]): SubagentTab | null {
  for (let index = tabs.length - 1; index >= 0; index -= 1) {
    if (tabs[index].status === "running") return tabs[index];
  }
  return null;
}

function latestRunId(tab: SubagentTab): string | null {
  return tab.runIds[tab.runIds.length - 1] ?? null;
}
