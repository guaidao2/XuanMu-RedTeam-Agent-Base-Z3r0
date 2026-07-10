import { useCallback, useEffect, useRef, useState } from "react";
import { showApiError } from "../api/feedback";

type QueryResponse<Item> = {
  data?: {
    items: Item[];
  } | null;
};

type QueryOptions<Item> = {
  enabled?: boolean;
  query: (params: { page: number; size: number; keyword: string }) => Promise<QueryResponse<Item>>;
};

export function useOptionList<Item>({ enabled = true, query }: QueryOptions<Item>) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => () => {
    mountedRef.current = false;
  }, []);

  const load = useCallback(async () => {
    if (!mountedRef.current) return;
    setLoading(true);
    try {
      const response = await query({ page: 1, size: 100, keyword: "" });
      if (mountedRef.current) setItems(response.data?.items ?? []);
    } catch (error) {
      if (mountedRef.current) showApiError(error);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);

  return { items, loading, load };
}
