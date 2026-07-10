import { Button, Tooltip } from "@douyinfe/semi-ui";
import { Activity, FolderKanban, FolderOpen, Monitor, PanelRightOpen, Plus, SquareTerminal } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { showApiError } from "../../shared/api/feedback";
import { SANDBOX_CONTAINER_STATUS } from "../../shared/api/generated/constants";
import { canOpenContainerNoVNC, queryAvailableSandboxContainers } from "../../shared/api/sandboxContainers";
import { getWorkProjectRecordSnapshot } from "../../shared/api/workProjects";
import type { AgentInputPart, SandboxContainer } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";
import { useContainerShell } from "../container-shell/ContainerShellProvider";
import { WorkProjectInfoModal } from "../work-projects/WorkProjectInfoModal";
import { useAgentSessionContext } from "./AgentSessionProvider";
import { ChatStream } from "./ChatStream";
import { Composer } from "./Composer";
import { MessageScrollPanel } from "./MessageScrollPanel";
import { SandboxSelector } from "./SandboxSelector";
import { SubagentSidePanel } from "./SubagentSidePanel";
import { useSubagentPanel } from "./useSubagentPanel";

type PlaygroundLocationState = { sessionId?: string };

type SandboxActionButtonProps = {
  ariaLabel: string;
  disabled: boolean;
  icon: ReactNode;
  tooltip: string;
  onClick: () => void;
};

const STATUS_LABEL: Record<string, string> = {
  open: "Live",
  connecting: "Connecting",
  closed: "Disconnected",
  idle: "Idle",
};

export function PlaygroundPage() {
  const setHeaderActions = useAdminHeaderActions();
  const {
    activeSessionId, activeSessionSummary, selectSession,
    chatState, status, historyLoading, historyHasMore, historyPrepending, historyVersion,
    agents, defaultAgentCode, activeAgentCode, setActiveAgentCode,
    send, updateSelectedSandboxContainer, interrupt, cancelAll, loadPreviousHistory,
  } = useAgentSessionContext();
  const location = useLocation();
  const navigate = useNavigate();
  const [sandboxContainers, setSandboxContainers] = useState<SandboxContainer[]>([]);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [sandboxContainerId, setSandboxContainerId] = useState<number | null>(null);
  const [projectSandboxContainerIds, setProjectSandboxContainerIds] = useState<number[]>([]);
  const [projectSandboxScopeLoaded, setProjectSandboxScopeLoaded] = useState(false);
  const [projectRecordsOpen, setProjectRecordsOpen] = useState(false);
  const { openFileManager, openNoVNC, openShell, syncContainerWindows } = useContainerShell();
  const { selectedSubagent, setSelectedSubagent, subagentTabs, closeSubagentPanel } = useSubagentPanel(chatState, activeSessionId);
  const hasRunningSubagents = subagentTabs.some((tab) => tab.status === "running");
  const agentSwitchDisabled = activeAgentCode === defaultAgentCode && hasRunningSubagents;

  const selectedSandboxContainer = useMemo(
    () => sandboxContainers.find((container) => container.id === sandboxContainerId) ?? null,
    [sandboxContainerId, sandboxContainers],
  );
  const shellUnavailableReason = getSandboxActionUnavailableReason(selectedSandboxContainer, { requiresControlProxy: true });
  const screenUnavailableReason = getSandboxActionUnavailableReason(selectedSandboxContainer, { requiresNoVNC: true });
  const selectedSandboxName = selectedSandboxContainer?.container_name ?? "selected sandbox";
  const activeProjectId = activeSessionSummary?.session_type === "project" ? activeSessionSummary.project_id ?? null : null;
  const selectableSandboxContainers = useMemo(() => {
    if (activeSessionSummary?.session_type !== "project") return sandboxContainers;
    const allowed = new Set(projectSandboxContainerIds);
    return sandboxContainers.filter((container) => allowed.has(container.id));
  }, [activeSessionSummary?.session_type, projectSandboxContainerIds, sandboxContainers]);
  const openProjectRecords = useCallback(() => {
    setProjectRecordsOpen(true);
  }, []);
  const openSubagentPanel = useCallback(() => {
    const tab = [...subagentTabs].reverse().find((item) => item.status === "running") ?? subagentTabs[subagentTabs.length - 1];
    if (tab) setSelectedSubagent(tab.agentCode);
  }, [setSelectedSubagent, subagentTabs]);

  const openSelectedFileManager = useCallback(() => {
    if (selectedSandboxContainer) openFileManager(selectedSandboxContainer);
  }, [openFileManager, selectedSandboxContainer]);

  const openSelectedShell = useCallback(() => {
    if (selectedSandboxContainer) openShell(selectedSandboxContainer);
  }, [openShell, selectedSandboxContainer]);

  const openSelectedNoVNC = useCallback(() => {
    if (selectedSandboxContainer) openNoVNC(selectedSandboxContainer);
  }, [openNoVNC, selectedSandboxContainer]);

  const loadSandboxes = useCallback(async () => {
    setSandboxLoading(true);
    try {
      const response = await queryAvailableSandboxContainers({ page: 1, size: 100, keyword: "" });
      setSandboxContainers(response.data?.items ?? []);
    } catch (error) {
      showApiError(error);
    } finally {
      setSandboxLoading(false);
    }
  }, []);

  // consume sessionId from navigate state (e.g. project "Go") then clear so
  // back-navigation does not retrigger the jump
  useEffect(() => {
    const incoming = (location.state as PlaygroundLocationState | null)?.sessionId;
    if (incoming) {
      selectSession(incoming);
      navigate(location.pathname, { replace: true });
    }
  }, [location.pathname, location.state, navigate, selectSession]);

  useEffect(() => {
    void loadSandboxes();
  }, [loadSandboxes]);

  useEffect(() => {
    setSandboxContainerId(activeSessionSummary?.selected_sandbox_container_id ?? null);
  }, [activeSessionSummary?.selected_sandbox_container_id]);

  useEffect(() => {
    syncContainerWindows(selectedSandboxContainer);
  }, [
    activeSessionId,
    selectedSandboxContainer?.id,
    selectedSandboxContainer?.control_proxy_host_port,
    selectedSandboxContainer?.status,
  ]);

  useEffect(() => {
    if (!activeProjectId) {
      setProjectSandboxContainerIds([]);
      setProjectSandboxScopeLoaded(false);
      return;
    }
    setProjectSandboxScopeLoaded(false);
    getWorkProjectRecordSnapshot(activeProjectId)
      .then((response) => {
        setProjectSandboxContainerIds(response.data?.project.sandbox_container_ids ?? []);
        setProjectSandboxScopeLoaded(true);
      })
      .catch((error) => {
        setProjectSandboxContainerIds([]);
        setProjectSandboxScopeLoaded(true);
        showApiError(error);
      });
  }, [activeProjectId]);

  const changeSandboxContainer = useCallback(async (nextContainerId: number | null) => {
    const nextContainer = sandboxContainers.find((container) => container.id === nextContainerId) ?? null;
    if (!activeSessionId) {
      setSandboxContainerId(nextContainerId);
      syncContainerWindows(nextContainer);
      return;
    }
    try {
      const summary = await updateSelectedSandboxContainer(activeSessionId, nextContainerId);
      const selectedId = summary?.selected_sandbox_container_id ?? null;
      setSandboxContainerId(selectedId);
      syncContainerWindows(sandboxContainers.find((container) => container.id === selectedId) ?? null);
    } catch (error) {
      showApiError(error);
    }
  }, [activeSessionId, sandboxContainers, syncContainerWindows, updateSelectedSandboxContainer]);

  useEffect(() => {
    if (activeSessionSummary?.session_type !== "project" || !projectSandboxScopeLoaded || sandboxContainerId === null) return;
    if (activeSessionSummary.is_running) return;
    if (!projectSandboxContainerIds.includes(sandboxContainerId)) {
      void changeSandboxContainer(null);
    }
  }, [activeSessionSummary?.is_running, activeSessionSummary?.session_type, changeSandboxContainer, projectSandboxContainerIds, projectSandboxScopeLoaded, sandboxContainerId]);

  useEffect(() => {
    if (activeSessionSummary?.session_type !== "project" || activeSessionSummary.is_running || !projectSandboxScopeLoaded || sandboxLoading || sandboxContainerId !== null) return;
    const allowed = new Set(projectSandboxContainerIds);
    const firstAvailable = sandboxContainers.find((container) => (
      allowed.has(container.id) && container.status === SANDBOX_CONTAINER_STATUS.RUNNING
    ));
    if (firstAvailable) void changeSandboxContainer(firstAvailable.id);
  }, [
    activeSessionSummary?.is_running,
    activeSessionSummary?.session_type,
    changeSandboxContainer,
    projectSandboxContainerIds,
    projectSandboxScopeLoaded,
    sandboxContainerId,
    sandboxContainers,
    sandboxLoading,
  ]);

  const headerNode = useMemo(() => (
    <>
      <SandboxSelector
        containers={selectableSandboxContainers}
        loading={sandboxLoading}
        value={sandboxContainerId}
        className="sandbox-selector-topbar"
        onChange={(id) => void changeSandboxContainer(id)}
      />
      <div className="sandbox-container-actions" aria-label="Selected sandbox actions">
        {activeProjectId ? (
          <SandboxActionButton
            ariaLabel="Open project records"
            disabled={false}
            icon={<FolderKanban size={15} />}
            tooltip="Project records"
            onClick={openProjectRecords}
          />
        ) : null}
        <SandboxActionButton
          ariaLabel="Open subagent panel"
          disabled={subagentTabs.length === 0}
          icon={<PanelRightOpen size={15} />}
          tooltip={subagentTabs.length > 0 ? "Open subagent panel" : "No subagent messages"}
          onClick={openSubagentPanel}
        />
        <SandboxActionButton
          ariaLabel={`Open terminal for ${selectedSandboxName}`}
          disabled={Boolean(shellUnavailableReason)}
          icon={<SquareTerminal size={15} />}
          tooltip={shellUnavailableReason ?? `Open terminal for ${selectedSandboxName}`}
          onClick={openSelectedShell}
        />
        <SandboxActionButton
          ariaLabel={`Open screen for ${selectedSandboxName}`}
          disabled={Boolean(screenUnavailableReason)}
          icon={<Monitor size={15} />}
          tooltip={screenUnavailableReason ?? `Open screen for ${selectedSandboxName}`}
          onClick={openSelectedNoVNC}
        />
        <SandboxActionButton
          ariaLabel={`Browse files for ${selectedSandboxName}`}
          disabled={Boolean(shellUnavailableReason)}
          icon={<FolderOpen size={15} />}
          tooltip={shellUnavailableReason ?? `Browse files for ${selectedSandboxName}`}
          onClick={openSelectedFileManager}
        />
      </div>
      <Button icon={<Plus size={16} />} theme="solid" type="primary" onClick={() => selectSession(null)}>
        New chat
      </Button>
      <span className={cx("stream-status", `stream-status-${status}`)}>
        <Activity size={14} />
        <span>{STATUS_LABEL[status] ?? "Idle"}</span>
      </span>
    </>
  ), [activeProjectId, changeSandboxContainer, openProjectRecords, openSelectedFileManager, openSelectedNoVNC, openSelectedShell, openSubagentPanel, sandboxContainerId, selectableSandboxContainers, sandboxLoading, screenUnavailableReason, selectSession, selectedSandboxName, shellUnavailableReason, status, subagentTabs.length]);

  useLayoutEffect(() => {
    setHeaderActions(headerNode);
    return () => setHeaderActions(null);
  }, [headerNode, setHeaderActions]);

  const handleSend = async (content: AgentInputPart[]) => {
    try {
      await send(content, activeSessionId, sandboxContainerId);
      return true;
    } catch {
      return false;
    }
  };

  return (
    <div className={cx("playground-shell", selectedSubagent && "playground-shell-split")}>
      <div className="playground-main">
        <div className="playground-conversation-frame">
          <div className="playground-main-column">
            <MessageScrollPanel
              ariaLabel="Conversation messages"
              className="playground-canvas-shell"
              contentClassName="playground-canvas"
              loading={historyLoading}
              loadingPrevious={historyPrepending}
              onLoadPrevious={historyHasMore && !historyPrepending ? () => void loadPreviousHistory() : undefined}
              preserveScrollKey={historyVersion}
              resetKey={activeSessionId ?? "new-chat"}
              scrollButtonClassName="chat-scroll-tail-floating"
              watch={[chatState.nodes, chatState.streaming]}
            >
              {(tailRef) => (
                <ChatStream
                  nodes={chatState.nodes}
                  streaming={chatState.streaming}
                  agents={agents}
                  selectedSubagent={selectedSubagent}
                  tailRef={tailRef}
                  onOpenSubagent={setSelectedSubagent}
                />
              )}
            </MessageScrollPanel>
            <div className="playground-composer">
              <Composer
                streaming={chatState.streaming}
                disabled={historyLoading}
                agents={agents}
                activeAgentCode={activeAgentCode}
                agentSwitchDisabled={agentSwitchDisabled}
                canCancelAll={hasRunningSubagents}
                onPickAgent={setActiveAgentCode}
                onSend={handleSend}
                onInterrupt={() => void interrupt()}
                onCancelAll={() => void cancelAll()}
              />
            </div>
          </div>
          <SubagentSidePanel
            nodes={chatState.nodes}
            tabs={subagentTabs}
            agents={agents}
            selection={selectedSubagent}
            onSelect={setSelectedSubagent}
            onClose={closeSubagentPanel}
          />
        </div>
      </div>
      <WorkProjectInfoModal
        open={projectRecordsOpen && Boolean(activeProjectId)}
        projectId={activeProjectId}
        initialTab="assets"
        onClose={() => setProjectRecordsOpen(false)}
      />
    </div>
  );
}

function SandboxActionButton({ ariaLabel, disabled, icon, onClick, tooltip }: SandboxActionButtonProps) {
  return (
    <Tooltip content={tooltip}>
      <span className="sandbox-action-tooltip">
        <Button
          aria-label={ariaLabel}
          className="sandbox-action-button"
          disabled={disabled}
          icon={icon}
          theme="borderless"
          type="tertiary"
          onClick={onClick}
        />
      </span>
    </Tooltip>
  );
}

function getSandboxActionUnavailableReason(
  container: SandboxContainer | null,
  options: { requiresControlProxy?: boolean; requiresNoVNC?: boolean },
) {
  if (!container) return "Select a sandbox first";
  if (container.status !== SANDBOX_CONTAINER_STATUS.RUNNING) return "Selected sandbox is not running";
  if (options.requiresControlProxy && container.control_proxy_host_port <= 0) return "Selected sandbox control port is not ready";
  if (options.requiresNoVNC && !canOpenContainerNoVNC(container)) return "Selected sandbox has no noVNC screen";
  return null;
}
