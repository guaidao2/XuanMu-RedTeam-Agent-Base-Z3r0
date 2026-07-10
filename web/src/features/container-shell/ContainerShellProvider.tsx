import { Button } from "@douyinfe/semi-ui";
import { Maximize2, Minimize2, Minus, Monitor, FolderOpen, SquareTerminal, X } from "lucide-react";
import {
  CSSProperties,
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  lazy,
  MutableRefObject,
  useMemo,
  PointerEvent as ReactPointerEvent,
  useRef,
  useState,
  Suspense,
} from "react";
import type { FitAddon } from "@xterm/addon-fit";
import type { Terminal } from "@xterm/xterm";
import { buildHostShellUrl } from "../../shared/api/hosts";
import { buildContainerNoVNCUrl, buildContainerShellUrl, canOpenContainerNoVNC } from "../../shared/api/sandboxContainers";
import { SANDBOX_CONTAINER_STATUS } from "../../shared/api/generated/constants";
import { showApiError } from "../../shared/api/feedback";
import type { ManagedHost, SandboxContainer } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";
import {
  animateWindowFlight,
  buildFlight,
  buildWindowFlightStyle,
  cancelFlightFrame,
  clamp,
  clampWindowToViewport,
  DEFAULT_WINDOW_HEIGHT,
  DEFAULT_WINDOW_WIDTH,
  type DockState,
  type DragState,
  type FlightState,
  getDraggedWindowPosition,
  getInitialFileManagerRect,
  getInitialNoVNCRect,
  getMaximizedRect,
  getResizedWindowSize,
  getWindowRect,
  MIN_WINDOW_HEIGHT,
  type Rect,
  type ResizeState,
  type WindowStateBase,
} from "./floatingWindow";

const ContainerFileManager = lazy(() => import("./ContainerFileManager").then((module) => ({ default: module.ContainerFileManager })));

type ShellStatus = "idle" | "connecting" | "open" | "closed";

type ShellWindowState = WindowStateBase & {
  connectionKey: number;
  shellUrl: string;
  targetKey: string;
  status: ShellStatus;
  isMaximized: boolean;
  restoreRect: Rect | null;
};

type ShellTarget = {
  key: string;
  title: string;
  url: string;
};

type NoVNCWindowState = WindowStateBase & {
  containerId: number;
  containerName: string;
  url: string;
};

type FileManagerWindowState = WindowStateBase & {
  containerId: number;
  containerName: string;
  isMaximized: boolean;
  restoreRect: Rect | null;
};

type ContainerShellContextValue = {
  openFileManager: (container: SandboxContainer) => void;
  openHostShell: (host: ManagedHost) => void;
  openNoVNC: (container: SandboxContainer) => void;
  openShell: (container: SandboxContainer) => void;
  syncContainerWindows: (container: SandboxContainer | null) => void;
};

type FloatingWindowProps = {
  actions: ReactNode;
  children: ReactNode;
  className?: string;
  dockState: DockState;
  icon: ReactNode;
  isMaximized?: boolean;
  meta: string;
  onHeaderPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  rect: Rect;
  resizeHandle?: ReactNode;
  title: string;
};

type FloatingWindowFlightProps = {
  flight: FlightState;
  frameRef: MutableRefObject<HTMLDivElement | null>;
  icon: ReactNode;
  style?: CSSProperties;
};

type MinimizedWindowButtonProps = {
  ariaLabel: string;
  className?: string;
  icon: ReactNode;
  onClick: () => void;
};

type FloatingWindowLayerProps = {
  actions: ReactNode;
  children: ReactNode;
  flight: FlightState | null;
  flightIcon: ReactNode;
  flightRef: MutableRefObject<HTMLDivElement | null>;
  flightStyle?: CSSProperties;
  icon: ReactNode;
  meta: string;
  minimizedAriaLabel: string;
  minimizedClassName?: string;
  minimizedIcon: ReactNode;
  onHeaderPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onRestore: () => void;
  resizeHandle?: ReactNode;
  state: WindowStateBase & { isMaximized?: boolean };
};

type WindowControlsProps = {
  closeAriaLabel: string;
  maximizeAriaLabel?: string;
  minimizeAriaLabel: string;
  isMaximized?: boolean;
  onClose: () => void;
  onMaximize?: () => void;
  onMinimize: () => void;
  restoreAriaLabel?: string;
};

type FitTerminalOptions = {
  snapHeight?: boolean;
};

const SHELL_OUTPUT_DECODER = new TextDecoder();

async function loadXterm() {
  const [{ Terminal }, { FitAddon }] = await Promise.all([
    import("@xterm/xterm"),
    import("@xterm/addon-fit"),
    import("@xterm/xterm/css/xterm.css"),
  ]);
  return { Terminal, FitAddon };
}

const ContainerShellContext = createContext<ContainerShellContextValue | null>(null);

export function useContainerShell() {
  const value = useContext(ContainerShellContext);
  if (!value) throw new Error("useContainerShell must be used inside ContainerShellProvider");
  return value;
}

export function ContainerShellProvider({ children }: { children: ReactNode }) {
  const [shell, setShell] = useState<ShellWindowState | null>(null);
  const [shellFlight, setShellFlight] = useState<FlightState | null>(null);
  const [noVNC, setNoVNC] = useState<NoVNCWindowState | null>(null);
  const [noVNCFlight, setNoVNCFlight] = useState<FlightState | null>(null);
  const [fileManager, setFileManager] = useState<FileManagerWindowState | null>(null);
  const [fileManagerFlight, setFileManagerFlight] = useState<FlightState | null>(null);
  const terminalHostRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const shellFlightRef = useRef<HTMLDivElement | null>(null);
  const shellFlightFrameRef = useRef<number | null>(null);
  const noVNCFlightRef = useRef<HTMLDivElement | null>(null);
  const noVNCFlightFrameRef = useRef<number | null>(null);
  const fileManagerFlightRef = useRef<HTMLDivElement | null>(null);
  const fileManagerFlightFrameRef = useRef<number | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const noVNCDragRef = useRef<DragState | null>(null);
  const fileManagerDragRef = useRef<DragState | null>(null);
  const resizeRef = useRef<ResizeState | null>(null);
  const fitWithoutSnapRef = useRef(false);
  const connectionKeyRef = useRef(0);
  const activeShellUrl = shell?.shellUrl ?? null;
  const activeConnectionKey = shell?.connectionKey ?? null;

  const disposeShellResources = useCallback(() => {
    closeSocket(socketRef.current);
    socketRef.current = null;
    terminalRef.current?.dispose();
    terminalRef.current = null;
    fitRef.current = null;
  }, []);

  const closeShell = useCallback(() => {
    cancelFlightFrame(shellFlightFrameRef);
    setShellFlight(null);
    disposeShellResources();
    setShell(null);
  }, [disposeShellResources]);

  const sendResize = useCallback(() => {
    const terminal = terminalRef.current;
    const socket = socketRef.current;
    if (!terminal || !socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "resize", rows: terminal.rows, cols: terminal.cols }));
  }, []);

  const fitTerminal = useCallback((options: FitTerminalOptions = {}) => {
    if (!fitRef.current || !terminalRef.current || !terminalHostRef.current) return;
    fitRef.current.fit();
    if (options.snapHeight !== false) {
      snapShellHeightToRows(terminalHostRef.current, terminalRef.current, setShell);
    }
    sendResize();
  }, [sendResize]);

  const toggleMaximizeShell = useCallback(() => {
    cancelFlightFrame(shellFlightFrameRef);
    dragRef.current = null;
    resizeRef.current = null;
    setShellFlight(null);
    fitWithoutSnapRef.current = true;
    setShell((current) => {
      if (!current) return current;
      if (current.isMaximized) {
        const restoreRect = current.restoreRect ?? getWindowRect(current);
        return { ...current, ...restoreRect, isMaximized: false, restoreRect: null };
      }

      return {
        ...current,
        ...getMaximizedRect(),
        isMaximized: true,
        restoreRect: getWindowRect(current),
      };
    });
  }, [fitTerminal]);

  const minimizeShell = useCallback(() => {
    if (!shell) return;
    cancelFlightFrame(shellFlightFrameRef);
    setShellFlight(buildFlight(shell, "minimize", "shell", shell.status));
    setShell((current) => current ? { ...current, dockState: "minimized" } : current);
  }, [shell]);

  const restoreShell = useCallback(() => {
    if (!shell) return;
    cancelFlightFrame(shellFlightFrameRef);
    setShellFlight(buildFlight(shell, "restore", "shell", shell.status));
  }, [shell]);

  const openShellTarget = useCallback((target: ShellTarget) => {
    const currentShell = shell;
    if (currentShell?.targetKey === target.key && isSocketActive(socketRef.current)) {
      const preserveGeometry = currentShell.dockState === "minimized";
      cancelFlightFrame(shellFlightFrameRef);
      setShellFlight(null);
      fitWithoutSnapRef.current = preserveGeometry;
      setShell((current) => current ? {
        ...current,
        title: target.title,
        shellUrl: target.url,
        dockState: "normal",
      } : current);
      window.setTimeout(() => {
        fitTerminal({ snapHeight: !preserveGeometry });
        terminalRef.current?.focus();
      }, 0);
      return;
    }

    cancelFlightFrame(shellFlightFrameRef);
    setShellFlight(null);
    disposeShellResources();

    setShell({
      connectionKey: connectionKeyRef.current + 1,
      shellUrl: target.url,
      targetKey: target.key,
      title: target.title,
      dockState: "normal",
      status: "connecting",
      isMaximized: false,
      restoreRect: null,
      x: Math.max(24, window.innerWidth - DEFAULT_WINDOW_WIDTH - 36),
      y: Math.max(92, window.innerHeight - DEFAULT_WINDOW_HEIGHT - 36),
      width: DEFAULT_WINDOW_WIDTH,
      height: DEFAULT_WINDOW_HEIGHT,
    });
    connectionKeyRef.current += 1;
  }, [disposeShellResources, fitTerminal, shell]);

  const openShell = useCallback((container: SandboxContainer) => {
    if (container.status !== SANDBOX_CONTAINER_STATUS.RUNNING || container.control_proxy_host_port <= 0) return;

    openShellTarget({
      key: `container:${container.id}`,
      title: container.container_name,
      url: buildContainerShellUrl(container.id),
    });
  }, [openShellTarget]);

  const openHostShell = useCallback((host: ManagedHost) => {
    openShellTarget({
      key: `host:${host.id}`,
      title: `${host.host_account}@${host.ip_address}`,
      url: buildHostShellUrl(host.id),
    });
  }, [openShellTarget]);

  const closeNoVNC = useCallback(() => {
    cancelFlightFrame(noVNCFlightFrameRef);
    noVNCDragRef.current = null;
    setNoVNCFlight(null);
    setNoVNC(null);
  }, []);

  const minimizeNoVNC = useCallback(() => {
    if (!noVNC) return;
    cancelFlightFrame(noVNCFlightFrameRef);
    setNoVNCFlight(buildFlight(noVNC, "minimize", "novnc", "screen"));
    setNoVNC((current) => current ? { ...current, dockState: "minimized" } : current);
  }, [noVNC]);

  const restoreNoVNC = useCallback(() => {
    if (!noVNC) return;
    cancelFlightFrame(noVNCFlightFrameRef);
    setNoVNCFlight(buildFlight(noVNC, "restore", "novnc", "screen"));
  }, [noVNC]);

  const openNoVNC = useCallback((container: SandboxContainer) => {
    try {
      const url = buildContainerNoVNCUrl(container);
      cancelFlightFrame(noVNCFlightFrameRef);
      setNoVNCFlight(null);
      setNoVNC((current) => {
        if (current?.containerId === container.id && current.url === url) {
          return { ...current, title: container.container_name, containerName: container.container_name, dockState: "normal" };
        }

        return {
          containerId: container.id,
          title: container.container_name,
          containerName: container.container_name,
          dockState: "normal",
          url,
          ...getInitialNoVNCRect(),
        };
      });
    } catch (error) {
      showApiError(error);
    }
  }, []);

  const closeFileManager = useCallback(() => {
    cancelFlightFrame(fileManagerFlightFrameRef);
    fileManagerDragRef.current = null;
    setFileManagerFlight(null);
    setFileManager(null);
  }, []);

  const minimizeFileManager = useCallback(() => {
    if (!fileManager) return;
    cancelFlightFrame(fileManagerFlightFrameRef);
    setFileManagerFlight(buildFlight(fileManager, "minimize", "filemanager", "files"));
    setFileManager((current) => current ? { ...current, dockState: "minimized" } : current);
  }, [fileManager]);

  const restoreFileManager = useCallback(() => {
    if (!fileManager) return;
    cancelFlightFrame(fileManagerFlightFrameRef);
    setFileManagerFlight(buildFlight(fileManager, "restore", "filemanager", "files"));
  }, [fileManager]);

  const toggleMaximizeFileManager = useCallback(() => {
    cancelFlightFrame(fileManagerFlightFrameRef);
    fileManagerDragRef.current = null;
    resizeRef.current = null;
    setFileManagerFlight(null);
    setFileManager((current) => {
      if (!current) return current;
      if (current.isMaximized) {
        const restoreRect = current.restoreRect ?? getWindowRect(current);
        return { ...current, ...restoreRect, isMaximized: false, restoreRect: null };
      }

      return {
        ...current,
        ...getMaximizedRect(),
        isMaximized: true,
        restoreRect: getWindowRect(current),
      };
    });
  }, []);

  const openFileManager = useCallback((container: SandboxContainer) => {
    if (container.status !== SANDBOX_CONTAINER_STATUS.RUNNING || container.control_proxy_host_port <= 0) return;

    cancelFlightFrame(fileManagerFlightFrameRef);
    setFileManagerFlight(null);
    setFileManager((current) => {
      if (current?.containerId === container.id) {
        return { ...current, title: container.container_name, containerName: container.container_name, dockState: "normal" };
      }

      return {
        containerId: container.id,
        title: container.container_name,
        containerName: container.container_name,
        dockState: "normal",
        isMaximized: false,
        restoreRect: null,
        ...getInitialFileManagerRect(),
      };
    });
  }, []);

  const syncContainerWindows = useCallback((container: SandboxContainer | null) => {
    if (shell?.targetKey.startsWith("container:")) {
      if (container && container.status === SANDBOX_CONTAINER_STATUS.RUNNING && container.control_proxy_host_port > 0) {
        openShell(container);
      } else {
        closeShell();
      }
    }

    if (fileManager) {
      if (container && container.status === SANDBOX_CONTAINER_STATUS.RUNNING && container.control_proxy_host_port > 0) {
        openFileManager(container);
      } else {
        closeFileManager();
      }
    }

    if (noVNC) {
      if (container && canOpenContainerNoVNC(container)) {
        openNoVNC(container);
      } else {
        closeNoVNC();
      }
    }
  }, [closeFileManager, closeNoVNC, closeShell, fileManager, noVNC, openFileManager, openNoVNC, openShell, shell]);

  useEffect(() => {
    if (!activeShellUrl || activeConnectionKey === null || terminalRef.current || !terminalHostRef.current) return;

    let canceled = false;
    let terminal: Terminal | null = null;
    let fit: FitAddon | null = null;
    let socket: WebSocket | null = null;
    let disposable: { dispose: () => void } | null = null;

    const cleanup = () => {
      disposable?.dispose();
      if (socket) {
        socket.removeEventListener("close", onSocketTerminated);
        socket.removeEventListener("error", onSocketTerminated);
        socket.close();
      }
      terminal?.dispose();
      if (socketRef.current === socket) socketRef.current = null;
      if (terminalRef.current === terminal) terminalRef.current = null;
      if (fitRef.current === fit) fitRef.current = null;
      disposable = null;
      socket = null;
      terminal = null;
      fit = null;
    };

    const onSocketTerminated = () => {
      setShell((current) => current ? { ...current, status: "closed" } : current);
    };

    void loadXterm()
      .then(({ Terminal, FitAddon }) => {
        if (canceled || !terminalHostRef.current) return;

        terminal = new Terminal({
          cursorBlink: true,
          convertEol: true,
          fontFamily: "JetBrains Mono, SFMono-Regular, Consolas, monospace",
          fontSize: 13,
          theme: {
            background: "#0b1018",
            foreground: "#b7c6d7",
            cursor: "#ffffff",
            selectionBackground: "rgba(59, 130, 246, 0.24)",
          },
        });
        fit = new FitAddon();
        terminal.loadAddon(fit);
        terminal.open(terminalHostRef.current);
        terminalRef.current = terminal;
        fitRef.current = fit;
        window.setTimeout(fitTerminal, 0);

        try {
          socket = new WebSocket(activeShellUrl);
        } catch (error) {
          cleanup();
          showApiError(error);
          setShell((current) => current ? { ...current, status: "closed" } : current);
          return;
        }

        socket.binaryType = "arraybuffer";
        socketRef.current = socket;

        disposable = terminal.onData((data) => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "input", data }));
          }
        });

        socket.addEventListener("open", () => {
          setShell((current) => current ? { ...current, status: "open" } : current);
          terminal?.focus();
          fitTerminal({ snapHeight: false });
        });
        socket.addEventListener("message", (event) => {
          if (!terminal) return;
          if (typeof event.data === "string") {
            terminal.write(event.data);
            return;
          }
          terminal.write(SHELL_OUTPUT_DECODER.decode(event.data as ArrayBuffer));
        });
        socket.addEventListener("close", onSocketTerminated);
        socket.addEventListener("error", onSocketTerminated);
      })
      .catch((error) => {
        if (canceled) return;
        showApiError(error);
        setShell((current) => current ? { ...current, status: "closed" } : current);
      });

    return () => {
      canceled = true;
      cleanup();
    };
  }, [activeConnectionKey, activeShellUrl, fitTerminal]);

  useEffect(() => () => closeShell(), [closeShell]);

  useEffect(() => () => closeNoVNC(), [closeNoVNC]);

  useEffect(() => () => closeFileManager(), [closeFileManager]);

  useEffect(() => () => {
    cancelFlightFrame(shellFlightFrameRef);
    cancelFlightFrame(noVNCFlightFrameRef);
    cancelFlightFrame(fileManagerFlightFrameRef);
  }, []);

  useEffect(() => {
    if (!shellFlight || !shellFlightRef.current) return;
    return animateWindowFlight(shellFlightRef.current, shellFlight, shellFlightFrameRef, () => {
      if (shellFlight.direction === "restore") {
        fitWithoutSnapRef.current = true;
        setShell((current) => current ? { ...current, dockState: "normal" } : current);
      }
      setShellFlight(null);
    });
  }, [shellFlight]);

  useEffect(() => {
    if (!noVNCFlight || !noVNCFlightRef.current) return;
    return animateWindowFlight(noVNCFlightRef.current, noVNCFlight, noVNCFlightFrameRef, () => {
      if (noVNCFlight.direction === "restore") {
        setNoVNC((current) => current ? { ...current, dockState: "normal" } : current);
      }
      setNoVNCFlight(null);
    });
  }, [noVNCFlight]);

  useEffect(() => {
    if (!fileManagerFlight || !fileManagerFlightRef.current) return;
    return animateWindowFlight(fileManagerFlightRef.current, fileManagerFlight, fileManagerFlightFrameRef, () => {
      if (fileManagerFlight.direction === "restore") {
        setFileManager((current) => current ? { ...current, dockState: "normal" } : current);
      }
      setFileManagerFlight(null);
    });
  }, [fileManagerFlight]);

  useEffect(() => {
    if (!shell || shell.dockState !== "normal") return;
    const snapHeight = !fitWithoutSnapRef.current;
    fitWithoutSnapRef.current = false;
    window.setTimeout(() => fitTerminal({ snapHeight }), 0);
  }, [fitTerminal, shell?.dockState, shell?.height, shell?.width]);

  useEffect(() => {
    const onWindowResize = () => {
      setShell((current) => current?.isMaximized ? { ...current, ...getMaximizedRect() } : current);
      setNoVNC((current) => current ? {
        ...current,
        x: clamp(current.x, 8, window.innerWidth - 80),
        y: clamp(current.y, 8, window.innerHeight - 80),
      } : current);
      setFileManager((current) => {
        if (!current) return current;
        if (current.isMaximized) return { ...current, ...getMaximizedRect() };
        return clampWindowToViewport(current);
      });
      if (shell?.dockState === "normal") window.setTimeout(fitTerminal, 0);
    };
    window.addEventListener("resize", onWindowResize);
    return () => window.removeEventListener("resize", onWindowResize);
  }, [fitTerminal, shell?.dockState]);

  const onPointerMove = useCallback((event: PointerEvent) => {
    const drag = dragRef.current;
    if (drag) {
      setShell((current) => current ? {
        ...current,
        ...getDraggedWindowPosition(drag, event),
      } : current);
      return;
    }

    const noVNCDrag = noVNCDragRef.current;
    if (noVNCDrag) {
      setNoVNC((current) => current ? {
        ...current,
        ...getDraggedWindowPosition(noVNCDrag, event),
      } : current);
      return;
    }

    const fmDrag = fileManagerDragRef.current;
    if (fmDrag) {
      setFileManager((current) => current ? {
        ...current,
        ...getDraggedWindowPosition(fmDrag, event),
      } : current);
      return;
    }

    const resize = resizeRef.current;
    if (resize) {
      const nextSize = getResizedWindowSize(resize, event);
      if (resize.target === "shell") {
        setShell((current) => current ? { ...current, ...nextSize } : current);
        return;
      }
      setFileManager((current) => current ? { ...current, ...nextSize } : current);
    }
  }, []);

  const stopPointerAction = useCallback(() => {
    dragRef.current = null;
    noVNCDragRef.current = null;
    fileManagerDragRef.current = null;
    resizeRef.current = null;
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopPointerAction);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopPointerAction);
    };
  }, [onPointerMove, stopPointerAction]);

  const contextValue = useMemo<ContainerShellContextValue>(
    () => ({ openFileManager, openHostShell, openNoVNC, openShell, syncContainerWindows }),
    [openFileManager, openHostShell, openNoVNC, openShell, syncContainerWindows],
  );
  const shellFlightStyle = shellFlight ? buildWindowFlightStyle(shellFlight) : undefined;
  const noVNCFlightStyle = noVNCFlight ? buildWindowFlightStyle(noVNCFlight) : undefined;
  const fileManagerFlightStyle = fileManagerFlight ? buildWindowFlightStyle(fileManagerFlight) : undefined;

  return (
    <ContainerShellContext.Provider value={contextValue}>
      {children}
      {shell ? (
        <FloatingWindowLayer
          actions={(
            <WindowControls
              closeAriaLabel="Close shell"
              isMaximized={shell.isMaximized}
              maximizeAriaLabel="Maximize shell"
              minimizeAriaLabel="Minimize shell"
              onClose={closeShell}
              onMaximize={toggleMaximizeShell}
              onMinimize={minimizeShell}
              restoreAriaLabel="Restore shell size"
            />
          )}
          flight={shellFlight}
          flightIcon={<SquareTerminal size={15} />}
          flightRef={shellFlightRef}
          flightStyle={shellFlightStyle}
          icon={<SquareTerminal size={16} />}
          meta={shell.status}
          minimizedAriaLabel="Restore shell"
          minimizedIcon={<SquareTerminal size={20} />}
          onHeaderPointerDown={(event) => {
            if (shell.isMaximized) return;
            dragRef.current = beginWindowDrag(shell, event);
          }}
          onRestore={restoreShell}
          resizeHandle={(
            <div
              className="shell-resize-handle"
              onPointerDown={(event) => {
                if (shell.isMaximized) return;
                resizeRef.current = beginWindowResize("shell", shell, event);
              }}
            />
          )}
          state={shell}
        >
          <div ref={terminalHostRef} className="shell-terminal" />
        </FloatingWindowLayer>
      ) : null}
      {noVNC ? (
        <FloatingWindowLayer
          actions={(
            <WindowControls
              closeAriaLabel="Close noVNC"
              minimizeAriaLabel="Minimize noVNC"
              onClose={closeNoVNC}
              onMinimize={minimizeNoVNC}
            />
          )}
          flight={noVNCFlight}
          flightIcon={<Monitor size={15} />}
          flightRef={noVNCFlightRef}
          flightStyle={noVNCFlightStyle}
          icon={<Monitor size={16} />}
          meta="screen"
          minimizedAriaLabel="Restore noVNC"
          minimizedClassName="novnc-minimized-button"
          minimizedIcon={<Monitor size={20} />}
          onHeaderPointerDown={(event) => {
            noVNCDragRef.current = beginWindowDrag(noVNC, event, { capturePointer: true });
          }}
          onRestore={restoreNoVNC}
          state={noVNC}
        >
          <div className="novnc-body">
            <iframe className="novnc-frame" src={noVNC.url} title={`noVNC ${noVNC.containerName}`} />
          </div>
        </FloatingWindowLayer>
      ) : null}
      {fileManager ? (
        <FloatingWindowLayer
          actions={(
            <WindowControls
              closeAriaLabel="Close file manager"
              isMaximized={fileManager.isMaximized}
              maximizeAriaLabel="Maximize file manager"
              minimizeAriaLabel="Minimize file manager"
              onClose={closeFileManager}
              onMaximize={toggleMaximizeFileManager}
              onMinimize={minimizeFileManager}
              restoreAriaLabel="Restore file manager size"
            />
          )}
          flight={fileManagerFlight}
          flightIcon={<FolderOpen size={15} />}
          flightRef={fileManagerFlightRef}
          flightStyle={fileManagerFlightStyle}
          icon={<FolderOpen size={16} />}
          meta="files"
          minimizedAriaLabel="Restore file manager"
          minimizedClassName="filemanager-minimized-button"
          minimizedIcon={<FolderOpen size={20} />}
          onHeaderPointerDown={(event) => {
            if (fileManager.isMaximized) return;
            fileManagerDragRef.current = beginWindowDrag(fileManager, event, { capturePointer: true });
          }}
          onRestore={restoreFileManager}
          resizeHandle={(
            <div
              className="shell-resize-handle"
              onPointerDown={(event) => {
                if (fileManager.isMaximized) return;
                resizeRef.current = beginWindowResize("filemanager", fileManager, event);
              }}
            />
          )}
          state={fileManager}
        >
          <Suspense fallback={<div className="file-manager-loading">Loading files...</div>}>
            <ContainerFileManager containerId={fileManager.containerId} />
          </Suspense>
        </FloatingWindowLayer>
      ) : null}
    </ContainerShellContext.Provider>
  );
}

function FloatingWindowLayer({
  actions,
  children,
  flight,
  flightIcon,
  flightRef,
  flightStyle,
  icon,
  meta,
  minimizedAriaLabel,
  minimizedClassName,
  minimizedIcon,
  onHeaderPointerDown,
  onRestore,
  resizeHandle,
  state,
}: FloatingWindowLayerProps) {
  return (
    <>
      <FloatingWindow
        actions={actions}
        dockState={state.dockState}
        icon={icon}
        isMaximized={state.isMaximized}
        meta={meta}
        rect={state}
        title={state.title}
        onHeaderPointerDown={onHeaderPointerDown}
        resizeHandle={resizeHandle}
      >
        {children}
      </FloatingWindow>
      {state.dockState === "minimized" && !flight ? (
        <MinimizedWindowButton className={minimizedClassName} ariaLabel={minimizedAriaLabel} icon={minimizedIcon} onClick={onRestore} />
      ) : null}
      {flight ? (
        <FloatingWindowFlight frameRef={flightRef} flight={flight} icon={flightIcon} style={flightStyle} />
      ) : null}
    </>
  );
}

function WindowControls({
  closeAriaLabel,
  isMaximized = false,
  maximizeAriaLabel,
  minimizeAriaLabel,
  onClose,
  onMaximize,
  onMinimize,
  restoreAriaLabel,
}: WindowControlsProps) {
  return (
    <>
      <Button icon={<Minus size={14} />} theme="borderless" type="tertiary" onClick={onMinimize} aria-label={minimizeAriaLabel} />
      {onMaximize ? (
        <Button icon={isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />} theme="borderless" type="tertiary" onClick={onMaximize} aria-label={isMaximized ? restoreAriaLabel : maximizeAriaLabel} />
      ) : null}
      <Button icon={<X size={14} />} theme="borderless" type="tertiary" onClick={onClose} aria-label={closeAriaLabel} />
    </>
  );
}

function FloatingWindow({
  actions,
  children,
  className,
  dockState,
  icon,
  isMaximized = false,
  meta,
  onHeaderPointerDown,
  rect,
  resizeHandle,
  title,
}: FloatingWindowProps) {
  return (
    <div className={buildWindowClassName(className, dockState, isMaximized)} style={buildWindowStyle(rect)}>
      <FloatingWindowHeader
        actions={actions}
        icon={icon}
        meta={meta}
        title={title}
        onPointerDown={onHeaderPointerDown}
      />
      {children}
      {resizeHandle}
    </div>
  );
}

function FloatingWindowHeader({
  actions,
  icon,
  meta,
  onPointerDown,
  title,
}: Pick<FloatingWindowProps, "actions" | "icon" | "meta" | "title"> & {
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div className="shell-window-header" onPointerDown={onPointerDown}>
      <div className="shell-window-title">
        {icon}
        <span>{title}</span>
        <em>{meta}</em>
      </div>
      <div className="shell-window-actions" onPointerDown={(event) => event.stopPropagation()}>
        {actions}
      </div>
    </div>
  );
}

function FloatingWindowFlight({ flight, frameRef, icon, style }: FloatingWindowFlightProps) {
  return (
    <div ref={frameRef} className={cx("shell-flight", `shell-flight-${flight.direction}`)} style={style}>
      <div className="shell-flight-header">
        {icon}
        <span>{flight.title}</span>
        <em>{flight.meta}</em>
      </div>
      <div className="shell-flight-body" />
    </div>
  );
}

function MinimizedWindowButton({ ariaLabel, className, icon, onClick }: MinimizedWindowButtonProps) {
  return (
    <button className={cx("shell-minimized-button", className)} type="button" onClick={onClick} aria-label={ariaLabel}>
      {icon}
    </button>
  );
}

function buildWindowClassName(className: string | undefined, dockState: DockState, isMaximized: boolean) {
  return cx(
    "shell-window",
    className,
    dockState === "minimized" && "shell-window-hidden",
    isMaximized && "shell-window-maximized",
  );
}

function beginWindowDrag(
  rect: Rect,
  event: ReactPointerEvent<HTMLDivElement>,
  options: { capturePointer?: boolean } = {},
): DragState {
  if (options.capturePointer) event.currentTarget.setPointerCapture(event.pointerId);
  return { x: rect.x, y: rect.y, startX: event.clientX, startY: event.clientY };
}

function beginWindowResize(
  target: ResizeState["target"],
  rect: Rect,
  event: ReactPointerEvent<HTMLDivElement>,
): ResizeState {
  event.currentTarget.setPointerCapture(event.pointerId);
  return { target, width: rect.width, height: rect.height, startX: event.clientX, startY: event.clientY };
}

function buildWindowStyle(rect: Rect) {
  return {
    left: rect.x,
    top: rect.y,
    width: rect.width,
    height: rect.height,
  } satisfies CSSProperties;
}

function closeSocket(socket: WebSocket | null) {
  if (!socket || socket.readyState === WebSocket.CLOSED || socket.readyState === WebSocket.CLOSING) return;
  socket.close();
}

function isSocketActive(socket: WebSocket | null) {
  return socket !== null && socket.readyState !== WebSocket.CLOSED && socket.readyState !== WebSocket.CLOSING;
}

function snapShellHeightToRows(
  host: HTMLDivElement,
  terminal: Terminal,
  setShell: (value: (current: ShellWindowState | null) => ShellWindowState | null) => void,
) {
  const cellHeight = getTerminalCellHeight(terminal);
  if (!cellHeight || !terminal.element) return;

  const terminalStyle = window.getComputedStyle(terminal.element);
  const terminalPaddingY = cssNumber(terminalStyle, "padding-top") + cssNumber(terminalStyle, "padding-bottom");
  const visibleHostHeight = host.getBoundingClientRect().height;
  const targetHostHeight = Math.ceil((terminal.rows * cellHeight) + terminalPaddingY);
  const delta = targetHostHeight - visibleHostHeight;
  if (Math.abs(delta) < 1) return;

  setShell((current) => current && !current.isMaximized ? {
    ...current,
    height: clamp(current.height + delta, MIN_WINDOW_HEIGHT, window.innerHeight - 24),
  } : current);
}

function getTerminalCellHeight(terminal: Terminal) {
  const dimensions = (terminal as unknown as {
    _core?: { _renderService?: { dimensions?: { css?: { cell?: { height?: number } } } } };
  })._core?._renderService?.dimensions;
  const height = dimensions?.css?.cell?.height;
  return typeof height === "number" && Number.isFinite(height) && height > 0 ? height : null;
}

function cssNumber(style: CSSStyleDeclaration, property: string) {
  const value = Number.parseFloat(style.getPropertyValue(property));
  return Number.isFinite(value) ? value : 0;
}
