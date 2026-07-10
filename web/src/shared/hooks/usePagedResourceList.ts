import { useCallback, useEffect, useRef, useState } from "react";
import { showApiError } from "../api/feedback";

type QueryParams = {
  page: number;
  size: number;
  keyword: string;
};

type QueryResponse<Item> = {
  data?: {
    items: Item[];
    total: number;
  } | null;
};

type UsePagedResourceListOptions<Item> = {
  pageSize?: number;
  query: (params: QueryParams) => Promise<QueryResponse<Item>>;
};

const DEFAULT_PAGE_SIZE = 10;

export function usePagedResourceList<Item>({ pageSize = DEFAULT_PAGE_SIZE, query }: UsePagedResourceListOptions<Item>) {
  const [items, setItems] = useState<Item[]>([]);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [activeKeyword, setActiveKeyword] = useState("");
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const requestIdRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => () => {
    mountedRef.current = false;
    requestIdRef.current += 1;
  }, []);

  const loadItems = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    try {
      const response = await query({ page, size: pageSize, keyword: activeKeyword });
      if (!mountedRef.current || requestIdRef.current !== requestId) return;
      const nextItems = response.data?.items || [];
      if (nextItems.length === 0 && page > 1) {
        setPage((current) => Math.max(1, current - 1));
        return;
      }
      setItems(nextItems);
      setTotal(response.data?.total ?? 0);
    } catch (error) {
      if (mountedRef.current && requestIdRef.current === requestId) {
        showApiError(error);
      }
    } finally {
      if (mountedRef.current && requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [activeKeyword, page, pageSize, query]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const search = useCallback(() => {
    setPage(1);
    setActiveKeyword(keyword.trim());
  }, [keyword]);

  const previous = useCallback(() => {
    setPage((current) => Math.max(1, current - 1));
  }, []);

  const next = useCallback(() => {
    setPage((current) => current + 1);
  }, []);

  return {
    items,
    page,
    pageSize,
    keyword,
    total,
    rangeStart: total === 0 ? 0 : (page - 1) * pageSize + 1,
    rangeEnd: Math.min(page * pageSize, total),
    loading,
    loadItems,
    setKeyword,
    search,
    previous,
    next,
    canGoBack: page > 1,
    canGoNext: page * pageSize < total,
  };
}
