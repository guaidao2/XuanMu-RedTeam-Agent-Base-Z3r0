import { apiBlob, apiDelete, apiForm, apiGet, apiPatch, apiPost, buildAuthenticatedWebSocketUrl } from "./client";
import { SANDBOX_CONTAINER_STATUS } from "./generated/constants";
import { getStoredAccessToken } from "../auth/session";
import { buildQuery } from "./query";
import type {
  ContainerFileCopyRequest,
  ContainerFileCopyResponse,
  ContainerFileDeleteRequest,
  ContainerFileDeleteResponse,
  ContainerFileMkdirRequest,
  ContainerFileMkdirResponse,
  ContainerFileMoveRequest,
  ContainerFileMoveResponse,
  ContainerFileUploadRequest,
  ContainerFileUploadResponse,
  ContainerFileWriteRequest,
  ContainerFileWriteResponse,
  CreateSandboxContainerRequest,
  CreateSandboxContainerResponse,
  DeleteSandboxContainerResponse,
  ListContainerFilesParams,
  ListContainerFilesResponse,
  DownloadContainerFilesParams,
  QueryAvailableSandboxContainersParams,
  QueryAvailableSandboxContainersResponse,
  QuerySandboxContainersParams,
  QuerySandboxContainersResponse,
  ReadContainerFileParams,
  ReadContainerFileResponse,
  SandboxContainer,
  SandboxContainerPathParams,
  StartSandboxContainerPathParams,
  StartSandboxContainerResponse,
  StopSandboxContainerPathParams,
  StopSandboxContainerResponse,
  UpdateSandboxContainerEgressPathParams,
  UpdateSandboxContainerEgressRequest,
  UpdateSandboxContainerEgressResponse,
} from "./types";

const SANDBOX_CONTAINERS_PATH = "/api/sandbox-containers";

export function querySandboxContainers(params: QuerySandboxContainersParams) {
  return apiGet<QuerySandboxContainersResponse>(`${SANDBOX_CONTAINERS_PATH}${buildQuery(params)}`);
}

export function queryAvailableSandboxContainers(params: QueryAvailableSandboxContainersParams) {
  return apiGet<QueryAvailableSandboxContainersResponse>(`${SANDBOX_CONTAINERS_PATH}/available${buildQuery(params)}`);
}

export function createSandboxContainer(payload: CreateSandboxContainerRequest) {
  return apiPost<CreateSandboxContainerResponse>(SANDBOX_CONTAINERS_PATH, payload);
}

export function startSandboxContainer(id: StartSandboxContainerPathParams["id"]) {
  return apiPost<StartSandboxContainerResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/start`);
}

export function stopSandboxContainer(id: StopSandboxContainerPathParams["id"]) {
  return apiPost<StopSandboxContainerResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/stop`);
}

export function updateSandboxContainerEgress(
  id: UpdateSandboxContainerEgressPathParams["id"],
  payload: UpdateSandboxContainerEgressRequest,
) {
  return apiPatch<UpdateSandboxContainerEgressResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/egress`, payload);
}

export function deleteSandboxContainer(id: SandboxContainerPathParams["id"]) {
  return apiDelete<DeleteSandboxContainerResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}`);
}

export function buildContainerShellUrl(containerId: number) {
  return buildAuthenticatedWebSocketUrl(`${SANDBOX_CONTAINERS_PATH}/${containerId}/shell`);
}

export function canOpenContainerNoVNC(container: SandboxContainer) {
  return Boolean(container.control_proxy_host_port > 0 && container.status === SANDBOX_CONTAINER_STATUS.RUNNING);
}

export function buildContainerNoVNCUrl(container: SandboxContainer) {
  if (!canOpenContainerNoVNC(container)) {
    throw new Error("container control port is not ready");
  }

  const token = getStoredAccessToken();
  if (!token) throw new Error("missing access token");

  const wsPath = `../novnc-ws?token=${encodeURIComponent(token)}`;
  const base = `${window.location.origin}/api/sandbox-containers/${container.id}/novnc/vnc.html`;

  const url = new URL(base);
  url.searchParams.set("autoconnect", "true");
  url.searchParams.set("resize", "remote");
  url.searchParams.set("path", wsPath);
  url.searchParams.set("token", token);
  return url.toString();
}


// ── container file operations ──────────────────────────────────────────────

export function listContainerFiles(id: number, params: ListContainerFilesParams) {
  return apiGet<ListContainerFilesResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files${buildQuery(params)}`);
}

export function readContainerFile(id: number, params: ReadContainerFileParams) {
  return apiGet<ReadContainerFileResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/read${buildQuery(params)}`);
}

export function writeContainerFile(id: number, payload: ContainerFileWriteRequest) {
  return apiPost<ContainerFileWriteResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/write`, payload);
}

export function uploadContainerFiles(
  id: number,
  path: ContainerFileUploadRequest["path"],
  files: File[],
  overwrite: ContainerFileUploadRequest["overwrite"] = true,
) {
  const form = new FormData();
  form.set("path", path);
  form.set("overwrite", String(overwrite));
  files.forEach((file) => form.append("files", file));
  return apiForm<ContainerFileUploadResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/upload`, form);
}

export function downloadContainerFiles(id: number, params: DownloadContainerFilesParams) {
  const query = new URLSearchParams();
  params.path.forEach((path) => query.append("path", path));
  return apiBlob(`${SANDBOX_CONTAINERS_PATH}/${id}/files/download?${query.toString()}`);
}

export function copyContainerFiles(id: number, payload: ContainerFileCopyRequest) {
  return apiPost<ContainerFileCopyResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/copy`, payload);
}

export function moveContainerFiles(id: number, payload: ContainerFileMoveRequest) {
  return apiPost<ContainerFileMoveResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/move`, payload);
}

export function deleteContainerFiles(id: number, payload: ContainerFileDeleteRequest) {
  return apiPost<ContainerFileDeleteResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/delete`, payload);
}

export function createContainerDirectory(id: number, payload: ContainerFileMkdirRequest) {
  return apiPost<ContainerFileMkdirResponse>(`${SANDBOX_CONTAINERS_PATH}/${id}/files/mkdir`, payload);
}
