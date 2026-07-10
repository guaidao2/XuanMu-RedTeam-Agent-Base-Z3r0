import { apiDelete, apiGet, apiPatch, apiPost, buildAuthenticatedWebSocketUrl } from "./client";
import { buildQuery } from "./query";
import type {
  CreateManagedHostRequest,
  CreateManagedHostResponse,
  DeleteManagedHostImageRequest,
  DeleteManagedHostResponse,
  ListManagedHostImagesResponse,
  ManagedHostPathParams,
  PullManagedHostImagesRequest,
  PullManagedHostImagesResponse,
  QueryManagedHostsParams,
  QueryManagedHostsResponse,
  UpdateManagedHostRequest,
  UpdateManagedHostResponse,
} from "./types";

const HOSTS_PATH = "/api/hosts";

export function queryManagedHosts(params: QueryManagedHostsParams) {
  return apiGet<QueryManagedHostsResponse>(`${HOSTS_PATH}${buildQuery(params)}`);
}

export function createManagedHost(payload: CreateManagedHostRequest) {
  return apiPost<CreateManagedHostResponse>(HOSTS_PATH, payload);
}

export function updateManagedHost(id: ManagedHostPathParams["id"], payload: UpdateManagedHostRequest) {
  return apiPatch<UpdateManagedHostResponse>(`${HOSTS_PATH}/${id}`, payload);
}

export function deleteManagedHost(id: ManagedHostPathParams["id"]) {
  return apiDelete<DeleteManagedHostResponse>(`${HOSTS_PATH}/${id}`);
}

export function listManagedHostImages(id: ManagedHostPathParams["id"]) {
  return apiGet<ListManagedHostImagesResponse>(`${HOSTS_PATH}/${id}/images`);
}

export function pullManagedHostImages(id: ManagedHostPathParams["id"], payload: PullManagedHostImagesRequest) {
  return apiPost<PullManagedHostImagesResponse>(`${HOSTS_PATH}/${id}/images/pull`, payload);
}

export function removeManagedHostImage(id: ManagedHostPathParams["id"], payload: DeleteManagedHostImageRequest) {
  return apiPost(`${HOSTS_PATH}/${id}/images/remove`, payload);
}

export function buildHostShellUrl(id: ManagedHostPathParams["id"]) {
  return buildAuthenticatedWebSocketUrl(`${HOSTS_PATH}/${id}/shell`);
}
