import { KeyboardEvent, RefObject, TouchEvent, WheelEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

type UseAutoFollowScrollOptions<T extends HTMLElement> = {
  enabled?: boolean;
  onScrollToTop?: () => void;
  onUserScrollIntent?: () => void;
  suspendAutoFollow?: boolean;
  topLoadThreshold?: number;
  containerRef: RefObject<T | null>;
  resetKey?: string | number | null;
  watch?: readonly unknown[];
};

const DEFAULT_TOP_LOAD_THRESHOLD = 180;
const watchObjectIds = new WeakMap<object, number>();
let watchObjectIdSeq = 0;

export function useAutoFollowScroll<T extends HTMLElement = HTMLDivElement>({
  enabled = true,
  onScrollToTop,
  onUserScrollIntent,
  suspendAutoFollow = false,
  topLoadThreshold = DEFAULT_TOP_LOAD_THRESHOLD,
  containerRef,
  resetKey,
  watch = [],
}: UseAutoFollowScrollOptions<T>) {
  const tailRef = useRef<HTMLDivElement | null>(null);
  const touchStartYRef = useRef<number | null>(null);
  const lastScrollTopRef = useRef(0);
  const followingRef = useRef(true);
  const [following, setFollowingState] = useState(true);

  const watchKey = useMemo(() => watch.map(watchIdentityKey).join("\u001f"), [...watch]);
  const onScrollToTopRef = useRef(onScrollToTop);
  onScrollToTopRef.current = onScrollToTop;
  const onUserScrollIntentRef = useRef(onUserScrollIntent);
  onUserScrollIntentRef.current = onUserScrollIntent;

  const setFollowing = useCallback((next: boolean) => {
    followingRef.current = next;
    setFollowingState(next);
  }, []);

  const getContainer = useCallback(() => {
    return containerRef.current;
  }, [containerRef]);

  const scrollTail = useCallback((behavior: ScrollBehavior) => {
    const container = getContainer();
    if (!container) return;
    const previousBehavior = container.style.scrollBehavior;
    container.style.scrollBehavior = "auto";
    container.scrollTo({ top: container.scrollHeight, behavior });
    container.style.scrollBehavior = previousBehavior;
    if (behavior === "auto") lastScrollTopRef.current = container.scrollTop;
  }, [getContainer]);

  const scrollToLatest = useCallback(() => {
    setFollowing(true);
    scrollTail("smooth");
  }, [scrollTail, setFollowing]);

  const resumeIfAtTail = useCallback(() => {
    const frame = window.requestAnimationFrame(() => {
      const container = getContainer();
      if (container && isNearScrollTail(container)) setFollowing(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [getContainer, setFollowing]);

  const triggerScrollToTop = useCallback(() => {
    const container = getContainer();
    if (!container || container.scrollTop > topLoadThreshold) return;
    onScrollToTopRef.current?.();
  }, [getContainer, topLoadThreshold]);

  useEffect(() => {
    if (resetKey == null) return;
    setFollowing(true);
    lastScrollTopRef.current = 0;
    touchStartYRef.current = null;
  }, [resetKey, setFollowing]);

  useEffect(() => {
    const container = enabled ? getContainer() : null;
    if (!container) return;

    const syncFollowing = () => {
      if (suspendAutoFollow) return;
      const scrollingUp = container.scrollTop < lastScrollTopRef.current - 2;
      lastScrollTopRef.current = container.scrollTop;

      if (scrollingUp) {
        setFollowing(false);
        triggerScrollToTop();
        return;
      }

      if (!isNearScrollTail(container) && followingRef.current) {
        setFollowing(false);
      }
    };

    container.addEventListener("scroll", syncFollowing, { passive: true });
    return () => {
      container.removeEventListener("scroll", syncFollowing);
    };
  }, [enabled, getContainer, resetKey, setFollowing, suspendAutoFollow, triggerScrollToTop, watchKey]);

  useLayoutEffect(() => {
    if (!enabled || suspendAutoFollow || !followingRef.current) return;
    scrollTail("auto");
    const frame = window.requestAnimationFrame(() => scrollTail("auto"));
    return () => window.cancelAnimationFrame(frame);
  }, [enabled, following, resetKey, scrollTail, suspendAutoFollow, watchKey]);

  const handleWheel = useCallback((event: WheelEvent<T>) => {
    if (event.deltaY !== 0) onUserScrollIntentRef.current?.();
    if (event.deltaY < 0) {
      setFollowing(false);
      triggerScrollToTop();
    } else if (event.deltaY > 0) {
      resumeIfAtTail();
    }
  }, [resumeIfAtTail, setFollowing, triggerScrollToTop]);

  const handleTouchStart = useCallback((event: TouchEvent<T>) => {
    touchStartYRef.current = event.touches[0]?.clientY ?? null;
  }, []);

  const handleTouchMove = useCallback((event: TouchEvent<T>) => {
    const startY = touchStartYRef.current;
    const currentY = event.touches[0]?.clientY;
    if (startY == null || currentY == null || Math.abs(currentY - startY) <= 2) return;
    onUserScrollIntentRef.current?.();
    if (currentY > startY) {
      setFollowing(false);
      triggerScrollToTop();
    } else {
      resumeIfAtTail();
    }
  }, [resumeIfAtTail, setFollowing, triggerScrollToTop]);

  const handleKeyDown = useCallback((event: KeyboardEvent<T>) => {
    if (event.currentTarget !== event.target) return;
    switch (event.key) {
      case "ArrowUp":
      case "PageUp":
      case "Home":
        onUserScrollIntentRef.current?.();
        setFollowing(false);
        triggerScrollToTop();
        break;
      case "ArrowDown":
      case "PageDown":
      case "End":
      case " ":
        onUserScrollIntentRef.current?.();
        resumeIfAtTail();
        break;
      default:
        break;
    }
  }, [resumeIfAtTail, setFollowing, triggerScrollToTop]);

  return {
    following,
    tailRef,
    scrollToLatest,
    scrollHandlers: {
      onWheel: handleWheel,
      onKeyDown: handleKeyDown,
      onTouchStart: handleTouchStart,
      onTouchMove: handleTouchMove,
    },
  };
}

function isNearScrollTail(container: HTMLElement) {
  return container.scrollHeight - container.scrollTop - container.clientHeight < 8;
}

function watchIdentityKey(value: unknown) {
  if ((typeof value !== "object" && typeof value !== "function") || value === null) {
    return String(value);
  }
  const objectValue = value as object;
  let id = watchObjectIds.get(objectValue);
  if (!id) {
    id = ++watchObjectIdSeq;
    watchObjectIds.set(objectValue, id);
  }
  return `ref:${id}`;
}
