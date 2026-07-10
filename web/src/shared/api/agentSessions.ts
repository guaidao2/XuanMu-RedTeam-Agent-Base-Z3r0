import { apiDelete, apiGet, apiPatch, apiPost, buildAuthenticatedWebSocketUrl } from "./client";
import type {
  AgentTurnRequest,
  CancelAllAgentSessionTasksResponse,
  CreateAgentSessionTurnResponse,
  DeleteAgentSessionResponse,
  InterruptAgentSessionResponse,
  ListAgentEventsResponse,
  ListAgentSessionsResponse,
  SubmitAgentSessionTurnResponse,
  UpdateAgentSessionSandboxContainerRequest,
  UpdateAgentSessionSandboxContainerResponse,
  UpdateAgentSessionTitleRequest,
  UpdateAgentSessionTitleResponse,
} from "./types";

const AGENT_SESSIONS_PATH = "/api/agent-sessions";

export function listAgentSessions(limit = 100) {
  return apiGet<ListAgentSessionsResponse>(`${AGENT_SESSIONS_PATH}?limit=${limit}`);
}

export function createAgentSessionTurn(payload: AgentTurnRequest) {
  return apiPost<CreateAgentSessionTurnResponse>(`${AGENT_SESSIONS_PATH}/turns`, payload);
}

export function submitAgentSessionTurn(sessionId: string, payload: AgentTurnRequest) {
  return apiPost<SubmitAgentSessionTurnResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/turns`,
    payload,
  );
}

export function interruptAgentSession(sessionId: string) {
  return apiPost<InterruptAgentSessionResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/interrupt`,
  );
}

export function cancelAllAgentSessionTasks(sessionId: string) {
  return apiPost<CancelAllAgentSessionTasksResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/cancel-all`,
  );
}

export function listAgentEvents(
  sessionId: string,
  options: { beforeSeq?: number | null; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (options.beforeSeq) params.set("before_seq", String(options.beforeSeq));
  if (options.limit) params.set("limit", String(options.limit));
  const query = params.toString();
  return apiGet<ListAgentEventsResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/events${query ? `?${query}` : ""}`,
  );
}

export function updateAgentSessionTitle(sessionId: string, payload: UpdateAgentSessionTitleRequest) {
  return apiPatch<UpdateAgentSessionTitleResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/title`,
    payload,
  );
}

export function updateAgentSessionSandboxContainer(
  sessionId: string,
  payload: UpdateAgentSessionSandboxContainerRequest,
) {
  return apiPatch<UpdateAgentSessionSandboxContainerResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/sandbox-container`,
    payload,
  );
}

export function deleteAgentSession(sessionId: string) {
  return apiDelete<DeleteAgentSessionResponse>(
    `${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}`,
  );
}

export function buildAgentStreamUrl(sessionId: string, token: string) {
  return buildAuthenticatedWebSocketUrl(`${AGENT_SESSIONS_PATH}/${encodeURIComponent(sessionId)}/stream`, token);
}
