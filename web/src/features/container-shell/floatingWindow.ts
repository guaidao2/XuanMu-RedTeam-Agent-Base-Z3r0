import type { MutableRefObject } from "react";


export type DockState = "normal" | "minimized";

export type Rect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type WindowStateBase = Rect & {
  title: string;
  dockState: DockState;
};

export type DockSlot = "shell" | "novnc" | "filemanager";

export type FlightState = {
  direction: "minimize" | "restore";
  title: string;
  meta: string;
  from: Rect;
  to: Rect;
};

export type DragState = {
  x: number;
  y: number;
  startX: number;
  startY: number;
};

export type ResizeState = {
  target: "shell" | "filemanager";
  width: number;
  height: number;
  startX: number;
  startY: number;
};

export const DEFAULT_WINDOW_WIDTH = 760;
export const DEFAULT_WINDOW_HEIGHT = 460;
export const WINDOW_HEADER_HEIGHT = 42;
export const WINDOW_BORDER_WIDTH = 1;
export const NOVNC_SCREEN_WIDTH = 1280;
export const NOVNC_SCREEN_HEIGHT = 720;
export const NOVNC_DEFAULT_WIDTH = NOVNC_SCREEN_WIDTH + (WINDOW_BORDER_WIDTH * 2);
export const NOVNC_DEFAULT_HEIGHT = NOVNC_SCREEN_HEIGHT + WINDOW_HEADER_HEIGHT + (WINDOW_BORDER_WIDTH * 2);
export const MIN_WINDOW_WIDTH = 420;
export const MIN_WINDOW_HEIGHT = 260;
export const MAXIMIZED_MARGIN = 12;
const DOCK_BUTTON_RIGHT = 0;
const DOCK_BUTTON_SIZE = 46;
const DOCK_BUTTON_GAP = 54;
const WINDOW_DOCK_TRANSITION_MS = 420;

export function getDraggedWindowPosition(drag: DragState, event: PointerEvent) {
  return {
    x: clamp(drag.x + event.clientX - drag.startX, 8, window.innerWidth - 80),
    y: clamp(drag.y + event.clientY - drag.startY, 8, window.innerHeight - 80),
  };
}

export function getResizedWindowSize(resize: ResizeState, event: PointerEvent): Pick<Rect, "width" | "height"> {
  return {
    width: clamp(resize.width + event.clientX - resize.startX, MIN_WINDOW_WIDTH, window.innerWidth - 24),
    height: clamp(resize.height + event.clientY - resize.startY, MIN_WINDOW_HEIGHT, window.innerHeight - 24),
  };
}

export function clampWindowToViewport<T extends Rect>(rect: T): T {
  return {
    ...rect,
    x: clamp(rect.x, 8, window.innerWidth - 80),
    y: clamp(rect.y, 8, window.innerHeight - 80),
    width: clamp(rect.width, MIN_WINDOW_WIDTH, window.innerWidth - 24),
    height: clamp(rect.height, MIN_WINDOW_HEIGHT, window.innerHeight - 24),
  };
}

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(value, max));
}

export function getInitialNoVNCRect(): Rect {
  const width = Math.min(NOVNC_DEFAULT_WIDTH, Math.max(420, window.innerWidth - 24));
  const height = Math.min(NOVNC_DEFAULT_HEIGHT, Math.max(300, window.innerHeight - 24));
  return {
    x: Math.max(12, Math.round((window.innerWidth - width) / 2)),
    y: Math.max(72, Math.round((window.innerHeight - height) / 2)),
    width,
    height,
  };
}

export function getInitialFileManagerRect(): Rect {
  const width = Math.min(760, Math.max(420, window.innerWidth - 24));
  const height = Math.min(520, Math.max(300, window.innerHeight - 24));
  return {
    x: Math.max(24, window.innerWidth - width - 36),
    y: Math.max(92, window.innerHeight - height - 36),
    width,
    height,
  };
}

export function getWindowRect(rect: Rect): Rect {
  return {
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
  };
}

export function getMaximizedRect(): Rect {
  return {
    x: MAXIMIZED_MARGIN,
    y: MAXIMIZED_MARGIN,
    width: Math.max(MIN_WINDOW_WIDTH, window.innerWidth - (MAXIMIZED_MARGIN * 2)),
    height: Math.max(MIN_WINDOW_HEIGHT, window.innerHeight - (MAXIMIZED_MARGIN * 2)),
  };
}

export function buildFlight(
  state: WindowStateBase,
  direction: FlightState["direction"],
  slot: DockSlot,
  meta: string,
): FlightState {
  const rect = getWindowRect(state);
  const dockRect = getDockRect(slot);
  return {
    direction,
    title: state.title,
    meta,
    from: direction === "minimize" ? rect : dockRect,
    to: direction === "minimize" ? dockRect : rect,
  };
}

export function getDockRect(slot: DockSlot): Rect {
  let yOffset = 0;
  if (slot === "novnc") yOffset = DOCK_BUTTON_GAP;
  else if (slot === "filemanager") yOffset = DOCK_BUTTON_GAP * 2;
  return {
    x: window.innerWidth - DOCK_BUTTON_RIGHT - DOCK_BUTTON_SIZE,
    y: (window.innerHeight / 2) + yOffset,
    width: DOCK_BUTTON_SIZE,
    height: DOCK_BUTTON_SIZE,
  };
}

export function cancelFlightFrame(frameRef: MutableRefObject<number | null>) {
  if (frameRef.current === null) return;
  window.cancelAnimationFrame(frameRef.current);
  frameRef.current = null;
}

export function animateWindowFlight(
  element: HTMLDivElement,
  flight: FlightState,
  frameRef: MutableRefObject<number | null>,
  onDone: () => void,
) {
  const startedAt = performance.now();
  const base = getFlightBaseRect(flight);

  const tick = (now: number) => {
    const progress = clamp((now - startedAt) / WINDOW_DOCK_TRANSITION_MS, 0, 1);
    const eased = easeInOutCubic(progress);
    const rect = interpolateRect(flight.from, flight.to, eased);

    element.style.opacity = String(getFlightOpacity(flight.direction, eased));
    element.style.transform = buildWindowFlightTransform(base, rect);

    if (progress < 1) {
      frameRef.current = window.requestAnimationFrame(tick);
      return;
    }

    frameRef.current = null;
    onDone();
  };

  frameRef.current = window.requestAnimationFrame(tick);
  return () => cancelFlightFrame(frameRef);
}

export function buildWindowFlightStyle(flight: FlightState) {
  const base = getFlightBaseRect(flight);
  return {
    left: base.x,
    top: base.y,
    width: base.width,
    height: base.height,
    opacity: getFlightOpacity(flight.direction, 0),
    transform: buildWindowFlightTransform(base, flight.from),
  };
}

function getFlightBaseRect(flight: FlightState) {
  return flight.direction === "restore" ? flight.to : flight.from;
}

function buildWindowFlightTransform(base: Rect, rect: Rect) {
  const scaleX = rect.width / base.width;
  const scaleY = rect.height / base.height;
  const translateX = rect.x - base.x;
  const translateY = rect.y - base.y;
  return `matrix(${scaleX}, 0, 0, ${scaleY}, ${translateX}, ${translateY})`;
}

function interpolateRect(from: Rect, to: Rect, progress: number): Rect {
  return {
    x: lerp(from.x, to.x, progress),
    y: lerp(from.y, to.y, progress),
    width: lerp(from.width, to.width, progress),
    height: lerp(from.height, to.height, progress),
  };
}

function lerp(from: number, to: number, progress: number) {
  return from + ((to - from) * progress);
}

function easeInOutCubic(progress: number) {
  return progress < 0.5
    ? 4 * progress * progress * progress
    : 1 - (Math.pow(-2 * progress + 2, 3) / 2);
}

function getFlightOpacity(direction: FlightState["direction"], progress: number) {
  return direction === "minimize" ? 1 - (0.78 * progress) : 0.22 + (0.78 * progress);
}
