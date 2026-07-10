import { apiGet, apiPatch } from "./client";
import type {
  GetInstanceConfigResponse,
  UpdateInstanceConfigRequest,
  UpdateInstanceConfigResponse,
} from "./types";

const SYSTEM_CONFIG_PATH = "/api/system-config";

export function getInstanceConfig() {
  return apiGet<GetInstanceConfigResponse>(`${SYSTEM_CONFIG_PATH}/instance`);
}

export function updateInstanceConfig(payload: UpdateInstanceConfigRequest) {
  return apiPatch<UpdateInstanceConfigResponse>(`${SYSTEM_CONFIG_PATH}/instance`, payload);
}
