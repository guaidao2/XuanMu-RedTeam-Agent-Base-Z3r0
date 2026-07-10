import { useCallback, useEffect, useRef, useState } from "react";
import { showApiError, showApiSuccess } from "../api/feedback";
import type { CommonResponsePayload } from "../api/types";


type ResourceSubmitOptions = {
  onSuccess?: () => void | Promise<void>;
};

export function useResourceSubmit({ onSuccess }: ResourceSubmitOptions = {}) {
  const [saving, setSaving] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => () => {
    mountedRef.current = false;
  }, []);

  const submit = useCallback(
    async (action: () => Promise<CommonResponsePayload>) => {
      if (saving) return;
      setSaving(true);
      try {
        const response = await action();
        if (!mountedRef.current) return;
        showApiSuccess(response);
        await onSuccess?.();
      } catch (error) {
        if (mountedRef.current) showApiError(error);
      } finally {
        if (mountedRef.current) setSaving(false);
      }
    },
    [onSuccess, saving],
  );

  return { saving, submit };
}
