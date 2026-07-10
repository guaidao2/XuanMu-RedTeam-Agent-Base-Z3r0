import { Toast } from "@douyinfe/semi-ui";
import { ApiError } from "./client";
import type { CommonResponsePayload } from "./types";

export function showApiSuccess(response: CommonResponsePayload) {
  if (response.message) {
    Toast.success(response.message);
  }
}

export function showApiError(error: unknown) {
  if (error instanceof ApiError && error.response?.message) {
    Toast.error(error.response.message);
    return;
  }

  if (error instanceof Error && error.message) {
    Toast.error(error.message);
    return;
  }

  Toast.error("Network request failed");
}
