import { apiGet } from "./client";
import type { ListAgentsResponse } from "./types";

const AGENTS_PATH = "/api/agents";

export function listAgents() {
  return apiGet<ListAgentsResponse>(AGENTS_PATH);
}
