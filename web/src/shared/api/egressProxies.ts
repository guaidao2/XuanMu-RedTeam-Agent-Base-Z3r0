import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import { buildQuery } from "./query";
import type {
  CreateEgressProxyRequest,
  CreateEgressProxyResponse,
  DeleteEgressProxyResponse,
  EgressProxyPathParams,
  QueryEgressProxiesParams,
  QueryEgressProxiesResponse,
  TestEgressProxyPathParams,
  TestEgressProxyResponse,
  UpdateEgressProxyRequest,
  UpdateEgressProxyResponse,
} from "./types";

const EGRESS_PROXIES_PATH = "/api/egress-proxies";

export function queryEgressProxies(params: QueryEgressProxiesParams) {
  return apiGet<QueryEgressProxiesResponse>(`${EGRESS_PROXIES_PATH}${buildQuery(params)}`);
}

export function createEgressProxy(payload: CreateEgressProxyRequest) {
  return apiPost<CreateEgressProxyResponse>(EGRESS_PROXIES_PATH, payload);
}

export function updateEgressProxy(id: EgressProxyPathParams["id"], payload: UpdateEgressProxyRequest) {
  return apiPatch<UpdateEgressProxyResponse>(`${EGRESS_PROXIES_PATH}/${id}`, payload);
}

export function deleteEgressProxy(id: EgressProxyPathParams["id"]) {
  return apiDelete<DeleteEgressProxyResponse>(`${EGRESS_PROXIES_PATH}/${id}`);
}

export function testEgressProxy(id: TestEgressProxyPathParams["id"]) {
  return apiPost<TestEgressProxyResponse>(`${EGRESS_PROXIES_PATH}/${id}/test`);
}
