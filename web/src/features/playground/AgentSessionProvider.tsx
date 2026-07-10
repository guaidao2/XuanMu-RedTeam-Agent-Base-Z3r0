import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { listAgents } from "../../shared/api/agents";
import {
  buildAgentStreamUrl,
  cancelAllAgentSessionTasks,
  createAgentSessionTurn,
  deleteAgentSession,
  interruptAgentSession,
  listAgentEvents,
  listAgentSessions,
  submitAgentSessionTurn,
  updateAgentSessionSandboxContainer,
} from "../../shared/api/agentSessions";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import { getStoredAccessToken } from "../../shared/auth/session";
import type {
  AgentInfo,
  AgentInputPart,
  AgentSessionSummary,
  AgentStreamEvent,
  AgentTurnData,
} from "../../shared/api/types";
import type { ChatState } from "./chatState";
import {
  deriveChatState,
  emptyTimelineStore,
  endStreaming,
  ingestEvents,
  type TimelineStore,
} from "./timelineStore";

type ConnectionStatus = "idle" | "connecting" | "open" | "closed";

type SessionRuntime = {
  store: TimelineStore;
  state: ChatState;
  status: ConnectionStatus;
  historyLoading: boolean;
  historyPrepending: boolean;
  historyHasMore: boolean;
  historyBeforeSeq: number | null;
  historyVersion: number;
  // user-overridden agent for this session; "" => fall back to server-side sticky
  agentCodeOverride: string;
};

function createSessionRuntime(): SessionRuntime {
  const store = emptyTimelineStore();
  return {
    store,
    state: deriveChatState(store),
    status: "idle",
    historyLoading: false,
    historyPrepending: false,
    historyHasMore: false,
    historyBeforeSeq: null,
    historyVersion: 0,
    agentCodeOverride: "",
  };
}

const IDLE_CLOSE_MS = 5 * 60 * 1000;
const DELETED_SESSION_TOMBSTONE_MS = 30 * 1000;
const HISTORY_PAGE_SIZE = 80;
const LIVE_FLUSH_INTERVAL_MS = 33;

type AgentSessionContextValue = {
  sessions: AgentSessionSummary[];
  sessionsLoading: boolean;
  refreshSessions: () => Promise<void>;
  syncSessionSummaries: (items: AgentSessionSummary[]) => void;
  deleteSession: (sessionId: string) => Promise<void>;
  dropSessionRuntime: (sessionId: string) => void;

  activeSessionId: string | null;
  activeSessionSummary: AgentSessionSummary | null;
  selectSession: (sessionId: string | null, options?: { navigateBlank?: boolean }) => void;

  chatState: ChatState;
  status: ConnectionStatus;
  historyLoading: boolean;
  historyPrepending: boolean;
  historyHasMore: boolean;
  historyVersion: number;

  agents: AgentInfo[];
  defaultAgentCode: string;
  activeAgentCode: string;
  setActiveAgentCode: (code: string) => void;

  send: (content: AgentInputPart[], sessionId: string | null, sandboxContainerId: number | null) => Promise<void>;
  updateSelectedSandboxContainer: (sessionId: string, sandboxContainerId: number | null) => Promise<AgentSessionSummary | null>;
  interrupt: (sessionId?: string | null) => Promise<void>;
  cancelAll: (sessionId?: string | null) => Promise<void>;
  loadPreviousHistory: (sessionId?: string | null) => Promise<void>;
};

const AgentSessionContext = createContext<AgentSessionContextValue | null>(null);

export function useAgentSessionContext(): AgentSessionContextValue {
  const value = useContext(AgentSessionContext);
  if (!value) throw new Error("useAgentSessionContext must be used inside AgentSessionProvider");
  return value;
}

export function AgentSessionProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [sessionSummaries, setSessionSummaries] = useState<Map<string, AgentSessionSummary>>(() => new Map());
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [runtimes, setRuntimes] = useState<Map<string, SessionRuntime>>(() => new Map());

  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [defaultAgentCode, setDefaultAgentCode] = useState("");
  // pending pick for the next brand-new chat (when activeSessionId is still null)
  const [pendingAgentCode, setPendingAgentCode] = useState("");
  // sockets + timers live outside react state because their identity does not
  // drive rendering; one ws per session is kept alive across session switches
  const socketsRef = useRef<Map<string, WebSocket>>(new Map());
  const socketCleanupRef = useRef<Map<string, () => void>>(new Map());
  const idleTimersRef = useRef<Map<string, number>>(new Map());
  const deletedMarkerTimersRef = useRef<Map<string, number>>(new Map());
  const ensuredRef = useRef<Set<string>>(new Set());
  const loadingHistoryRef = useRef<Set<string>>(new Set());
  const deletedSessionsRef = useRef<Set<string>>(new Set());
  const liveFlushTimersRef = useRef<Map<string, number>>(new Map());
  const liveFrameEventsRef = useRef<Map<string, AgentStreamEvent[]>>(new Map());
  const manualBlankSessionRef = useRef(false);

  const clearDeletedMarkerLater = useCallback((sessionId: string) => {
    const existing = deletedMarkerTimersRef.current.get(sessionId);
    if (existing != null) window.clearTimeout(existing);
    const timer = window.setTimeout(() => {
      deletedSessionsRef.current.delete(sessionId);
      deletedMarkerTimersRef.current.delete(sessionId);
    }, DELETED_SESSION_TOMBSTONE_MS);
    deletedMarkerTimersRef.current.set(sessionId, timer);
  }, []);

  // ---------------------------------------------------------------- helpers
  const initRuntime = useCallback((sessionId: string) => {
    setRuntimes((prev) => {
      if (prev.has(sessionId)) return prev;
      const next = new Map(prev);
      next.set(sessionId, createSessionRuntime());
      return next;
    });
  }, []);

  const updateRuntime = useCallback((sessionId: string, fn: (r: SessionRuntime) => SessionRuntime) => {
    setRuntimes((prev) => {
      const current = prev.get(sessionId) ?? createSessionRuntime();
      const next = new Map(prev);
      next.set(sessionId, fn(current));
      return next;
    });
  }, []);

  // apply a store mutation and re-derive the rendered chat state in one shot
  const applyStore = useCallback((sessionId: string, fn: (store: TimelineStore) => TimelineStore) => {
    updateRuntime(sessionId, (r) => {
      const store = fn(r.store);
      if (store === r.store) return r;
      return { ...r, store, state: deriveChatState(store) };
    });
  }, [updateRuntime]);

  const dropRuntime = useCallback((sessionId: string, options: { keepDeletedMarker?: boolean } = {}) => {
    setRuntimes((prev) => {
      if (!prev.has(sessionId)) return prev;
      const next = new Map(prev);
      next.delete(sessionId);
      return next;
    });
    setSessionSummaries((prev) => {
      if (!prev.has(sessionId)) return prev;
      const next = new Map(prev);
      next.delete(sessionId);
      return next;
    });
    ensuredRef.current.delete(sessionId);
    loadingHistoryRef.current.delete(sessionId);
    if (!options.keepDeletedMarker) {
      deletedSessionsRef.current.delete(sessionId);
      const deletedTimer = deletedMarkerTimersRef.current.get(sessionId);
      if (deletedTimer != null) {
        window.clearTimeout(deletedTimer);
        deletedMarkerTimersRef.current.delete(sessionId);
      }
    }
    liveFrameEventsRef.current.delete(sessionId);
    const timer = liveFlushTimersRef.current.get(sessionId);
    if (timer != null) {
      window.clearTimeout(timer);
      liveFlushTimersRef.current.delete(sessionId);
    }
  }, []);

  const syncSessionSummaries = useCallback((items: AgentSessionSummary[]) => {
    if (!items.length) return;
    setSessionSummaries((prev) => {
      const next = new Map(prev);
      for (const session of items) next.set(session.session_id, session);
      return next;
    });
  }, []);

  const syncSession = useCallback((item: AgentSessionSummary) => {
    setSessionSummaries((prev) => {
      const next = new Map(prev);
      next.set(item.session_id, item);
      return next;
    });
    setSessions((prev) => {
      if (item.session_type !== "chat") return prev.filter((session) => session.session_id !== item.session_id);
      if (!prev.some((session) => session.session_id === item.session_id)) return [item, ...prev];
      return prev.map((session) => session.session_id === item.session_id ? item : session);
    });
  }, []);

  // ------------------------------------------------------------- agents
  useEffect(() => {
    listAgents()
      .then((response) => {
        setAgents(response.data?.items ?? []);
        setDefaultAgentCode(response.data?.default_code ?? "");
      })
      .catch(showApiError);
  }, []);

  // ------------------------------------------------------------- sessions
  const refreshSessions = useCallback(async (silent = false) => {
    if (!silent) setSessionsLoading(true);
    try {
      const response = await listAgentSessions();
      const items = response.data?.items ?? [];
      setSessions(items);
      syncSessionSummaries(items);
    } catch (error) {
      if (!silent) showApiError(error);
    } finally {
      if (!silent) setSessionsLoading(false);
    }
  }, [syncSessionSummaries]);

  const refreshSessionsRef = useRef(refreshSessions);
  refreshSessionsRef.current = refreshSessions;

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  // ------------------------------------------------------------ ws + idle
  const clearIdleTimer = useCallback((sessionId: string) => {
    const timer = idleTimersRef.current.get(sessionId);
    if (timer != null) {
      window.clearTimeout(timer);
      idleTimersRef.current.delete(sessionId);
    }
  }, []);

  const closeSocket = useCallback((sessionId: string) => {
    clearIdleTimer(sessionId);
    const socket = socketsRef.current.get(sessionId);
    if (!socket) return;
    socketsRef.current.delete(sessionId);
    socketCleanupRef.current.get(sessionId)?.();
    socketCleanupRef.current.delete(sessionId);
    socket.close();
    updateRuntime(sessionId, (r) => {
      const store = endStreaming(r.store);
      return { ...r, status: "closed", store, state: store === r.store ? r.state : deriveChatState(store) };
    });
  }, [clearIdleTimer, updateRuntime]);

  const dropSessionRuntime = useCallback((sessionId: string) => {
    closeSocket(sessionId);
    dropRuntime(sessionId);
  }, [closeSocket, dropRuntime]);

  const markActivity = useCallback((sessionId: string) => {
    clearIdleTimer(sessionId);
    if (!socketsRef.current.has(sessionId)) return;
    const timer = window.setTimeout(() => closeSocket(sessionId), IDLE_CLOSE_MS);
    idleTimersRef.current.set(sessionId, timer);
  }, [clearIdleTimer, closeSocket]);

  const flushLiveEvents = useCallback((sessionId: string) => {
    liveFlushTimersRef.current.delete(sessionId);
    const events = liveFrameEventsRef.current.get(sessionId);
    if (!events?.length) return;
    liveFrameEventsRef.current.delete(sessionId);
    if (deletedSessionsRef.current.has(sessionId)) return;

    applyStore(sessionId, (store) => ingestEvents(store, events));

    if (events.some((event) => event.type === "user_message")) {
      void refreshSessionsRef.current(true);
    }
    if (events.some((event) => event.type === "run_state" && !event.running)) {
      void refreshSessionsRef.current(true);
    }
  }, [applyStore]);

  const enqueueStreamEvent = useCallback((sessionId: string, event: AgentStreamEvent) => {
    const events = liveFrameEventsRef.current.get(sessionId);
    if (events) events.push(event);
    else liveFrameEventsRef.current.set(sessionId, [event]);

    if (liveFlushTimersRef.current.has(sessionId)) return;
    const timer = window.setTimeout(() => flushLiveEvents(sessionId), LIVE_FLUSH_INTERVAL_MS);
    liveFlushTimersRef.current.set(sessionId, timer);
  }, [flushLiveEvents]);

  // pull the latest persisted page and merge it (idempotent) to recover any
  // frames missed while the socket was closed; never touches the scroll-up cursor
  const mergeLatestHistory = useCallback((sessionId: string) => {
    if (deletedSessionsRef.current.has(sessionId)) return;
    listAgentEvents(sessionId, { limit: HISTORY_PAGE_SIZE })
      .then((response) => {
        if (deletedSessionsRef.current.has(sessionId)) return;
        applyStore(sessionId, (store) => ingestEvents(store, response.data?.items ?? []));
      })
      .catch(() => {
        // best-effort catch-up; the next reconnect or idle refresh retries
      });
  }, [applyStore]);

  const connectFor = useCallback((sessionId: string): WebSocket => {
    const existing = socketsRef.current.get(sessionId);
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return existing;
    }

    const token = getStoredAccessToken();
    if (!token) throw new Error("missing access token");

    const socket = new WebSocket(buildAgentStreamUrl(sessionId, token));
    socketsRef.current.set(sessionId, socket);
    initRuntime(sessionId);
    updateRuntime(sessionId, (r) => ({ ...r, status: "connecting" }));

    const onOpen = () => {
      if (socketsRef.current.get(sessionId) !== socket) return;
      updateRuntime(sessionId, (r) => ({ ...r, status: "open" }));
      markActivity(sessionId);
      // a reconnect may have missed frames; the live projection covers the
      // current turn, this merges anything persisted while we were away
      if (ensuredRef.current.has(sessionId)) mergeLatestHistory(sessionId);
    };
    socket.addEventListener("open", onOpen);

    const onTerminate = (event: CloseEvent | Event) => {
      if (socketsRef.current.get(sessionId) !== socket) return;
      socketsRef.current.delete(sessionId);
      socketCleanupRef.current.get(sessionId)?.();
      socketCleanupRef.current.delete(sessionId);
      clearIdleTimer(sessionId);
      if (deletedSessionsRef.current.has(sessionId)) return;
      updateRuntime(sessionId, (r) => {
        if (!r.store.streaming) {
          return { ...r, status: "closed" };
        }
        const errored = ingestEvents(r.store, [{
          type: "error",
          created_at: new Date().toISOString(),
          seq: 0,
          agent_name: "",
          nested_for: "",
          nested_call_id: "",
          message: websocketCloseMessage(event),
          code: "connection_closed",
        }]);
        const store = endStreaming(errored);
        return { ...r, status: "closed", store, state: deriveChatState(store) };
      });
    };
    socket.addEventListener("close", onTerminate);
    socket.addEventListener("error", onTerminate);

    const onMessage = (event: MessageEvent) => {
      if (socketsRef.current.get(sessionId) !== socket) return;
      markActivity(sessionId);
      try {
        const parsed = JSON.parse(event.data) as AgentStreamEvent;
        if (deletedSessionsRef.current.has(sessionId)) return;
        enqueueStreamEvent(sessionId, parsed);
      } catch {
        // backend only emits json frames; swallow malformed payloads defensively
      }
    };
    socket.addEventListener("message", onMessage);
    socketCleanupRef.current.set(sessionId, () => {
      socket.removeEventListener("open", onOpen);
      socket.removeEventListener("close", onTerminate);
      socket.removeEventListener("error", onTerminate);
      socket.removeEventListener("message", onMessage);
    });
    return socket;
  }, [clearIdleTimer, enqueueStreamEvent, initRuntime, markActivity, mergeLatestHistory, updateRuntime]);

  const tryConnectFor = useCallback((sessionId: string): boolean => {
    try {
      connectFor(sessionId);
      return true;
    } catch (error) {
      showApiError(error);
      updateRuntime(sessionId, (r) => ({ ...r, status: "closed" }));
      return false;
    }
  }, [connectFor, updateRuntime]);

  // ---------------------------------------------------------- history load
  const loadHistory = useCallback((sessionId: string, markEnsured: boolean) => {
    if (deletedSessionsRef.current.has(sessionId)) return;
    if (loadingHistoryRef.current.has(sessionId)) return;
    initRuntime(sessionId);
    loadingHistoryRef.current.add(sessionId);
    updateRuntime(sessionId, (r) => ({ ...r, historyLoading: true }));
    if (!tryConnectFor(sessionId)) {
      loadingHistoryRef.current.delete(sessionId);
      updateRuntime(sessionId, (r) => ({ ...r, historyLoading: false }));
      return;
    }

    listAgentEvents(sessionId, { limit: HISTORY_PAGE_SIZE })
      .then((response) => {
        if (deletedSessionsRef.current.has(sessionId)) return;
        const data = response.data;
        const items = data?.items ?? [];
        if (markEnsured) ensuredRef.current.add(sessionId);
        loadingHistoryRef.current.delete(sessionId);
        updateRuntime(sessionId, (r) => {
          const store = ingestEvents(r.store, items);
          return {
            ...r,
            store,
            state: deriveChatState(store),
            historyLoading: false,
            historyHasMore: Boolean(data?.has_more),
            historyBeforeSeq: data?.next_before_seq ?? null,
            historyVersion: r.historyVersion + 1,
          };
        });
      })
      .catch((error) => {
        ensuredRef.current.delete(sessionId);
        loadingHistoryRef.current.delete(sessionId);
        if (deletedSessionsRef.current.has(sessionId)) return;
        showApiError(error);
        updateRuntime(sessionId, (r) => ({ ...r, historyLoading: false }));
      });
  }, [initRuntime, tryConnectFor, updateRuntime]);

  const ensureHistoryLoaded = useCallback((sessionId: string) => {
    if (ensuredRef.current.has(sessionId)) return;
    loadHistory(sessionId, true);
  }, [loadHistory]);

  const openLiveSession = useCallback((sessionId: string) => {
    initRuntime(sessionId);
    ensuredRef.current.add(sessionId);
    manualBlankSessionRef.current = false;
    setActiveSessionId(sessionId);
    tryConnectFor(sessionId);
    mergeLatestHistory(sessionId);
  }, [initRuntime, mergeLatestHistory, tryConnectFor]);

  const runtimesRef = useRef(runtimes);
  runtimesRef.current = runtimes;

  const loadPreviousHistory = useCallback(async (sessionId: string | null = activeSessionId) => {
    const targetSessionId = sessionId ?? activeSessionId;
    if (!targetSessionId || deletedSessionsRef.current.has(targetSessionId)) return;
    const runtime = runtimesRef.current.get(targetSessionId);
    if (!runtime?.historyHasMore || runtime.historyBeforeSeq == null || runtime.historyPrepending) return;
    updateRuntime(targetSessionId, (r) => ({ ...r, historyPrepending: true }));
    try {
      const response = await listAgentEvents(targetSessionId, {
        beforeSeq: runtime.historyBeforeSeq,
        limit: HISTORY_PAGE_SIZE,
      });
      if (deletedSessionsRef.current.has(targetSessionId)) return;
      const data = response.data;
      updateRuntime(targetSessionId, (r) => {
        const store = ingestEvents(r.store, data?.items ?? []);
        return {
          ...r,
          store,
          state: deriveChatState(store),
          historyPrepending: false,
          historyHasMore: Boolean(data?.has_more),
          historyBeforeSeq: data?.next_before_seq ?? null,
          historyVersion: r.historyVersion + 1,
        };
      });
    } catch (error) {
      if (!deletedSessionsRef.current.has(targetSessionId)) showApiError(error);
      updateRuntime(targetSessionId, (r) => ({ ...r, historyPrepending: false }));
    }
  }, [activeSessionId, updateRuntime]);

  // ----------------------------------------------------------- selection
  const selectSession = useCallback((sessionId: string | null, options: { navigateBlank?: boolean } = {}) => {
    if (sessionId) {
      initRuntime(sessionId);
    }
    manualBlankSessionRef.current = sessionId === null && options.navigateBlank !== false;
    setActiveSessionId(sessionId);
  }, [initRuntime]);

  useEffect(() => {
    if (!activeSessionId) return;
    if (ensuredRef.current.has(activeSessionId)) {
      tryConnectFor(activeSessionId);
      return;
    }
    ensureHistoryLoaded(activeSessionId);
  }, [activeSessionId, ensureHistoryLoaded, tryConnectFor]);

  useEffect(() => {
    const runningSessions = sessions.filter((session) => session.is_running);
    if (!runningSessions.length) return;

    if (!activeSessionId && !manualBlankSessionRef.current) {
      const [first] = runningSessions;
      if (first) setActiveSessionId(first.session_id);
    }

    for (const session of runningSessions) {
      if (ensuredRef.current.has(session.session_id)) {
        tryConnectFor(session.session_id);
        continue;
      }
      ensureHistoryLoaded(session.session_id);
    }
  }, [activeSessionId, ensureHistoryLoaded, sessions, tryConnectFor]);

  // ------------------------------------------------------------- agentCode
  const sessionAgentCode = useCallback(
    (sessionId: string | null): string => {
      if (!sessionId) return "";
      return sessionSummaries.get(sessionId)?.agent_code ?? "";
    },
    [sessionSummaries],
  );

  const activeAgentCode = useMemo(() => {
    if (!activeSessionId) {
      return pendingAgentCode || defaultAgentCode;
    }
    const runtime = runtimes.get(activeSessionId);
    if (runtime?.agentCodeOverride) return runtime.agentCodeOverride;
    return sessionAgentCode(activeSessionId) || defaultAgentCode;
  }, [activeSessionId, defaultAgentCode, pendingAgentCode, runtimes, sessionAgentCode]);

  const setActiveAgentCode = useCallback((code: string) => {
    if (!agents.some((agent) => agent.code === code)) return;
    if (!activeSessionId) {
      setPendingAgentCode(code);
      return;
    }
    initRuntime(activeSessionId);
    updateRuntime(activeSessionId, (r) => ({ ...r, agentCodeOverride: code }));
  }, [activeSessionId, agents, initRuntime, updateRuntime]);

  const getSessionAgentCode = useCallback((sessionId: string | null) => {
    if (!sessionId) return pendingAgentCode || defaultAgentCode;
    const runtime = runtimes.get(sessionId);
    if (runtime?.agentCodeOverride) return runtime.agentCodeOverride;
    return sessionAgentCode(sessionId) || defaultAgentCode;
  }, [defaultAgentCode, pendingAgentCode, runtimes, sessionAgentCode]);

  // ------------------------------------------------------------- commands
  const updateSelectedSandboxContainer = useCallback(async (sessionId: string, sandboxContainerId: number | null) => {
    const response = await updateAgentSessionSandboxContainer(sessionId, { sandbox_container_id: sandboxContainerId });
    const summary = response.data ?? null;
    if (summary) syncSession(summary);
    return summary;
  }, [syncSession]);

  const applyTurnEvents = useCallback((sessionId: string, events: readonly AgentStreamEvent[]) => {
    if (events.length) applyStore(sessionId, (store) => ingestEvents(store, events));
  }, [applyStore]);

  const send = useCallback(async (
    content: AgentInputPart[],
    sessionId: string | null,
    sandboxContainerId: number | null,
  ) => {
    const agentCode = getSessionAgentCode(sessionId);
    try {
      if (sessionId) {
        const response = await submitAgentSessionTurn(sessionId, {
          content,
          agent_code: agentCode || null,
          sandbox_container_id: sandboxContainerId,
        });
        const data = requireTurnData(response.data);
        syncSession(data.session);
        applyTurnEvents(sessionId, data.events);
        tryConnectFor(sessionId);
        return;
      }

      const response = await createAgentSessionTurn({
        content,
        agent_code: agentCode || null,
        sandbox_container_id: sandboxContainerId,
      });
      const data = requireTurnData(response.data);
      syncSession(data.session);
      applyTurnEvents(data.session_id, data.events);
      openLiveSession(data.session_id);
      setPendingAgentCode("");
    } catch (error) {
      showApiError(error);
      throw error;
    }
  }, [applyTurnEvents, getSessionAgentCode, openLiveSession, syncSession, tryConnectFor]);

  const interrupt = useCallback(async (sessionId: string | null = activeSessionId) => {
    const targetSessionId = sessionId ?? activeSessionId;
    if (!targetSessionId) return;
    try {
      const response = await interruptAgentSession(targetSessionId);
      const data = requireTurnData(response.data);
      syncSession(data.session);
      applyTurnEvents(targetSessionId, data.events);
      tryConnectFor(targetSessionId);
    } catch (error) {
      showApiError(error);
    }
  }, [activeSessionId, applyTurnEvents, syncSession, tryConnectFor]);

  const cancelAll = useCallback(async (sessionId: string | null = activeSessionId) => {
    const targetSessionId = sessionId ?? activeSessionId;
    if (!targetSessionId) return;
    try {
      const response = await cancelAllAgentSessionTasks(targetSessionId);
      const data = requireTurnData(response.data);
      syncSession(data.session);
      applyTurnEvents(targetSessionId, data.events);
      tryConnectFor(targetSessionId);
    } catch (error) {
      showApiError(error);
    }
  }, [activeSessionId, applyTurnEvents, syncSession, tryConnectFor]);

  const deleteSession = useCallback(async (sessionId: string) => {
    deletedSessionsRef.current.add(sessionId);
    closeSocket(sessionId);
    dropRuntime(sessionId, { keepDeletedMarker: true });
    if (activeSessionId === sessionId) selectSession(null);
    try {
      const response = await deleteAgentSession(sessionId);
      showApiSuccess(response);
      await refreshSessions();
      clearDeletedMarkerLater(sessionId);
    } catch (error) {
      deletedSessionsRef.current.delete(sessionId);
      showApiError(error);
      await refreshSessions();
    }
  }, [activeSessionId, clearDeletedMarkerLater, closeSocket, dropRuntime, refreshSessions, selectSession]);

  // -------------------------------------------------------------- unmount
  useEffect(() => {
    return () => {
      for (const socket of socketsRef.current.values()) socket.close();
      for (const cleanup of socketCleanupRef.current.values()) cleanup();
      for (const timer of idleTimersRef.current.values()) window.clearTimeout(timer);
      for (const timer of deletedMarkerTimersRef.current.values()) window.clearTimeout(timer);
      for (const timer of liveFlushTimersRef.current.values()) window.clearTimeout(timer);
      socketsRef.current.clear();
      socketCleanupRef.current.clear();
      idleTimersRef.current.clear();
      deletedMarkerTimersRef.current.clear();
      liveFlushTimersRef.current.clear();
      ensuredRef.current.clear();
      loadingHistoryRef.current.clear();
      deletedSessionsRef.current.clear();
      liveFrameEventsRef.current.clear();
    };
  }, []);

  // -------------------------------------------------------------- derived
  const defaultRuntime = useMemo(createSessionRuntime, []);
  const activeRuntime = activeSessionId ? runtimes.get(activeSessionId) ?? defaultRuntime : defaultRuntime;
  const activeSessionSummary = activeSessionId ? sessionSummaries.get(activeSessionId) ?? null : null;
  const value = useMemo<AgentSessionContextValue>(() => ({
    sessions, sessionsLoading, refreshSessions, syncSessionSummaries, deleteSession,
    dropSessionRuntime,
    activeSessionId, activeSessionSummary, selectSession,
    chatState: activeRuntime.state,
    status: activeRuntime.status,
    historyLoading: activeRuntime.historyLoading,
    historyPrepending: activeRuntime.historyPrepending,
    historyHasMore: activeRuntime.historyHasMore,
    historyVersion: activeRuntime.historyVersion,
    agents, defaultAgentCode, activeAgentCode, setActiveAgentCode,
    send, updateSelectedSandboxContainer, interrupt, cancelAll, loadPreviousHistory,
  }), [
    sessions, sessionsLoading, refreshSessions, syncSessionSummaries, deleteSession,
    dropSessionRuntime,
    activeSessionId, activeSessionSummary, selectSession,
    activeRuntime,
    agents, defaultAgentCode, activeAgentCode, setActiveAgentCode,
    send, updateSelectedSandboxContainer, interrupt, cancelAll, loadPreviousHistory,
  ]);

  return <AgentSessionContext.Provider value={value}>{children}</AgentSessionContext.Provider>;
}

function websocketCloseMessage(event: CloseEvent | Event): string {
  if (event instanceof CloseEvent) {
    if (event.reason) return `Agent stream connection closed: ${event.reason}`;
    if (event.code === 1009) return "Agent stream connection closed because the image payload is too large";
    if (event.code !== 1000 && event.code !== 1005) {
      return `Agent stream connection closed unexpectedly (code ${event.code})`;
    }
  }
  return "Agent stream connection closed before the model returned output";
}

function requireTurnData(data: AgentTurnData | null | undefined): AgentTurnData {
  if (!data) throw new Error("agent session turn response missing data");
  return data;
}
