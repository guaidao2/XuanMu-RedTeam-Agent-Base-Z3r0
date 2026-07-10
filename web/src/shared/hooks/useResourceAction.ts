import { useCallback, useEffect, useRef, useState } from "react";
import { showApiError, showApiSuccess } from "../api/feedback";
import type { CommonResponsePayload } from "../api/types";

export function useResourceAction<Item extends { id: number }>(
  action: (item: Item) => Promise<CommonResponsePayload>,
  onAfter?: () => void | Promise<void>,
) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => () => {
    mountedRef.current = false;
  }, []);

  const run = useCallback(
    async (item: Item) => {
      if (busyId !== null) return;
      setBusyId(item.id);
      try {
        const response = await action(item);
        if (!mountedRef.current) return;
        showApiSuccess(response);
        await onAfter?.();
      } catch (error) {
        if (mountedRef.current) showApiError(error);
      } finally {
        if (mountedRef.current) setBusyId(null);
      }
    },
    [action, busyId, onAfter],
  );

  return { run, busyId };
}
