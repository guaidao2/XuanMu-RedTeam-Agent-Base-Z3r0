import { useEffect, useState } from "react";

export function useVisibleResourceIds(items: Array<{ id: number }>) {
  const [visibleIds, setVisibleIds] = useState<Set<number>>(() => new Set());

  useEffect(() => {
    const ids = new Set(items.map((item) => item.id));
    setVisibleIds((current) => {
      const next = new Set([...current].filter((id) => ids.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [items]);

  const toggle = (id: number) => {
    setVisibleIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return { isVisible: (id: number) => visibleIds.has(id), toggle };
}
