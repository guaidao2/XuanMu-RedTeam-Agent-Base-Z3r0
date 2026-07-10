import { Button, Popconfirm, Tag, Toast, Tooltip } from "@douyinfe/semi-ui";
import {
  ArrowLeft, ArrowRight, ArrowUp, Clipboard, ClipboardPaste,
  Copy, Download, File, FilePlus, Folder, FolderOpen, FolderPlus, Grid3X3, List,
  RefreshCw, Scissors, Trash2, Upload,
} from "lucide-react";
import { type CSSProperties, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  copyContainerFiles, createContainerDirectory, deleteContainerFiles,
  downloadContainerFiles, listContainerFiles, moveContainerFiles, uploadContainerFiles, writeContainerFile,
} from "../../shared/api/sandboxContainers";
import { showApiError } from "../../shared/api/feedback";
import type { ContainerFileInfo } from "../../shared/api/types";
import { formatDateTime } from "../../shared/lib/date";
import { formatBytes } from "../../shared/lib/number";
import { UI_TEXT } from "../../shared/lib/uiText";
import { cx } from "../../shared/lib/className";

const FileViewer = lazy(() => import("./FileViewer").then((module) => ({ default: module.FileViewer })));

type ViewMode = "list" | "icon";
type ClipboardState = { action: "copy" | "cut"; paths: string[]; sourceDir: string } | null;

type Props = {
  containerId: number;
};

export function ContainerFileManager({ containerId }: Props) {
  const [path, setPath] = useState("/");
  const [files, setFiles] = useState<ContainerFileInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [clipboard, setClipboard] = useState<ClipboardState>(null);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [pathHistory, setPathHistory] = useState<string[]>(["/"]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [viewingFile, setViewingFile] = useState<ContainerFileInfo | null>(null);
  const [createType, setCreateType] = useState<"file" | "dir" | null>(null);
  const requestIdRef = useRef(0);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  const loadFiles = useCallback(async (dir: string) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    try {
      const response = await listContainerFiles(containerId, { path: dir });
      if (requestIdRef.current !== requestId) return;
      const fileList = response.data?.files ?? [];
      fileList.sort((a, b) => {
        if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      setFiles(fileList);
      setPath(dir);
      setSelectedPaths(new Set());
    } catch (error) {
      if (requestIdRef.current === requestId) {
        showApiError(error);
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [containerId]);

  useEffect(() => {
    requestIdRef.current += 1;
    setPath("/");
    setFiles([]);
    setClipboard(null);
    setSelectedPaths(new Set());
    setPathHistory(["/"]);
    setHistoryIndex(0);
    setViewingFile(null);
    setCreateType(null);
    void loadFiles("/");
  }, [containerId, loadFiles]);

  const navigateTo = useCallback((dir: string) => {
    const newHistory = pathHistory.slice(0, historyIndex + 1);
    newHistory.push(dir);
    setPathHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);
    void loadFiles(dir);
  }, [pathHistory, historyIndex, loadFiles]);

  const goBack = useCallback(() => {
    if (historyIndex <= 0) return;
    const newIndex = historyIndex - 1;
    setHistoryIndex(newIndex);
    void loadFiles(pathHistory[newIndex]);
  }, [historyIndex, pathHistory, loadFiles]);

  const goForward = useCallback(() => {
    if (historyIndex >= pathHistory.length - 1) return;
    const newIndex = historyIndex + 1;
    setHistoryIndex(newIndex);
    void loadFiles(pathHistory[newIndex]);
  }, [historyIndex, pathHistory, loadFiles]);

  const goUp = useCallback(() => {
    if (path === "/") return;
    const parent = path.replace(/\/[^/]*$/, "") || "/";
    navigateTo(parent);
  }, [path, navigateTo]);

  const refresh = useCallback(() => {
    void loadFiles(path);
  }, [path, loadFiles]);

  const runFileAction = useCallback(async (action: () => Promise<void>) => {
    setLoading(true);
    try {
      await action();
    } catch (error) {
      showApiError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleFileClick = useCallback((file: ContainerFileInfo, event: React.MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedPaths((prev) => {
        const next = new Set(prev);
        if (next.has(file.path)) next.delete(file.path);
        else next.add(file.path);
        return next;
      });
      return;
    }
    setSelectedPaths(new Set([file.path]));
  }, []);

  const openFileViewer = useCallback((file: ContainerFileInfo) => {
    setViewingFile(file);
  }, []);

  const handleFileDoubleClick = useCallback((file: ContainerFileInfo) => {
    if (file.type === "directory") {
      navigateTo(file.path);
      return;
    }
    openFileViewer(file);
  }, [navigateTo, openFileViewer]);

  const handleCopy = useCallback(() => {
    if (selectedPaths.size === 0) return;
    setClipboard({ action: "copy", paths: Array.from(selectedPaths), sourceDir: path });
    Toast.success(`${selectedPaths.size} item(s) copied to clipboard`);
  }, [selectedPaths, path]);

  const handleCut = useCallback(() => {
    if (selectedPaths.size === 0) return;
    setClipboard({ action: "cut", paths: Array.from(selectedPaths), sourceDir: path });
    Toast.success(`${selectedPaths.size} item(s) cut to clipboard`);
  }, [selectedPaths, path]);

  const handlePaste = useCallback(async () => {
    if (!clipboard) return;
    await runFileAction(async () => {
      if (clipboard.action === "copy") {
        await copyContainerFiles(containerId, { sources: clipboard.paths, destination: path });
      } else {
        await moveContainerFiles(containerId, { sources: clipboard.paths, destination: path });
        setClipboard(null);
      }
      Toast.success(`${clipboard.action === "copy" ? "Copied" : "Moved"} ${clipboard.paths.length} item(s)`);
      await loadFiles(path);
    });
  }, [clipboard, containerId, path, loadFiles, runFileAction]);

  const handleDelete = useCallback(async () => {
    if (selectedPaths.size === 0) return;
    await runFileAction(async () => {
      await deleteContainerFiles(containerId, { paths: Array.from(selectedPaths) });
      Toast.success(`${selectedPaths.size} item(s) deleted`);
      await loadFiles(path);
    });
  }, [selectedPaths, containerId, path, loadFiles, runFileAction]);

  const startCreate = useCallback((type: "file" | "dir") => {
    setCreateType(type);
    setSelectedPaths(new Set());
  }, []);

  const handleCreateConfirm = useCallback(async (name: string) => {
    if (!name.trim() || !createType) return;
    const itemPath = path.replace(/\/$/, "") + "/" + name.trim();
    await runFileAction(async () => {
      if (createType === "dir") {
        await createContainerDirectory(containerId, { path: itemPath });
      } else {
        await writeContainerFile(containerId, { path: itemPath, content: "" });
      }
      Toast.success(createType === "dir" ? "Directory created" : "File created");
      await loadFiles(path);
    });
      setCreateType(null);
  }, [createType, containerId, path, loadFiles, runFileAction]);

  const handleCreateCancel = useCallback(() => {
    setCreateType(null);
  }, []);

  const handleUploadClick = useCallback(() => {
    uploadInputRef.current?.click();
  }, []);

  const handleUploadChange = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const uploadFiles = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (uploadFiles.length === 0) return;

    await runFileAction(async () => {
      await uploadContainerFiles(containerId, path, uploadFiles, true);
      Toast.success(`${uploadFiles.length} file(s) uploaded`);
      await loadFiles(path);
    });
  }, [containerId, path, loadFiles, runFileAction]);

  const handleDownload = useCallback(async () => {
    if (selectedPaths.size === 0) return;
    await runFileAction(async () => {
      const { blob, filename } = await downloadContainerFiles(containerId, { path: Array.from(selectedPaths) });
      saveBlob(blob, filename);
    });
  }, [containerId, selectedPaths, runFileAction]);

  const breadcrumbs = useMemo(() => {
    if (path === "/") return [{ label: "/", path: "/" }];
    const parts = path.split("/").filter(Boolean);
    return [
      { label: "/", path: "/" },
      ...parts.map((part, i) => ({
        label: part,
        path: "/" + parts.slice(0, i + 1).join("/"),
      })),
    ];
  }, [path]);

  const toolbarDisabled = loading;
  const hasSelection = selectedPaths.size > 0;
  const canPaste = clipboard !== null && clipboard.sourceDir !== path;

  return (
    <div className="file-manager-body">
      <div className="file-manager-toolbar">
        <Button icon={<ArrowLeft size={15} />} theme="borderless" type="tertiary" disabled={historyIndex <= 0 || toolbarDisabled} onClick={goBack} aria-label="Back" />
        <Button icon={<ArrowRight size={15} />} theme="borderless" type="tertiary" disabled={historyIndex >= pathHistory.length - 1 || toolbarDisabled} onClick={goForward} aria-label="Forward" />
        <Button icon={<ArrowUp size={15} />} theme="borderless" type="tertiary" disabled={path === "/" || toolbarDisabled} onClick={goUp} aria-label="Up" />
        <Button icon={<RefreshCw size={15} />} theme="borderless" type="tertiary" disabled={toolbarDisabled} onClick={refresh} aria-label="Refresh" />
        <span className="file-manager-separator" />
        <Button icon={<FilePlus size={15} />} theme="borderless" type="tertiary" disabled={toolbarDisabled || createType !== null} onClick={() => startCreate("file")} aria-label="New file" />
        <Button icon={<FolderPlus size={15} />} theme="borderless" type="tertiary" disabled={toolbarDisabled || createType !== null} onClick={() => startCreate("dir")} aria-label="New folder" />
        <Tooltip content="Upload files">
          <Button icon={<Upload size={15} />} theme="borderless" type="tertiary" disabled={toolbarDisabled} onClick={handleUploadClick} aria-label="Upload files" />
        </Tooltip>
        <Tooltip content="Download selected">
          <Button icon={<Download size={15} />} theme="borderless" type="tertiary" disabled={!hasSelection || toolbarDisabled} onClick={() => void handleDownload()} aria-label="Download selected" />
        </Tooltip>
        <span className="file-manager-separator" />
        <Tooltip content="Copy selected">
          <Button icon={<Copy size={15} />} theme="borderless" type="tertiary" disabled={!hasSelection || toolbarDisabled} onClick={handleCopy} aria-label="Copy" />
        </Tooltip>
        <Tooltip content="Cut selected">
          <Button icon={<Scissors size={15} />} theme="borderless" type="tertiary" disabled={!hasSelection || toolbarDisabled} onClick={handleCut} aria-label="Cut" />
        </Tooltip>
        <Tooltip content={canPaste ? `Paste ${clipboard?.paths.length ?? 0} item(s)` : "Nothing to paste"}>
          <Button icon={<ClipboardPaste size={15} />} theme="borderless" type="tertiary" disabled={!canPaste || toolbarDisabled} onClick={() => void handlePaste()} aria-label="Paste" />
        </Tooltip>
        <Popconfirm title="Delete selected items" content={`Delete ${selectedPaths.size} selected item(s)?`} okType="danger" cancelText={UI_TEXT.cancel} onConfirm={() => void handleDelete()}>
          <Button icon={<Trash2 size={15} />} theme="borderless" type="danger" disabled={!hasSelection || toolbarDisabled} aria-label="Delete" />
        </Popconfirm>
        <span className="file-manager-separator" />
        <Tooltip content="List view">
          <Button icon={<List size={15} />} theme="borderless" type={viewMode === "list" ? "primary" : "tertiary"} disabled={toolbarDisabled} onClick={() => setViewMode("list")} aria-label="List view" />
        </Tooltip>
        <Tooltip content="Icon view">
          <Button icon={<Grid3X3 size={15} />} theme="borderless" type={viewMode === "icon" ? "primary" : "tertiary"} disabled={toolbarDisabled} onClick={() => setViewMode("icon")} aria-label="Icon view" />
        </Tooltip>
      </div>
      <input ref={uploadInputRef} className="file-manager-upload-input" type="file" multiple onChange={(event) => void handleUploadChange(event)} />

      <div className="file-manager-breadcrumb">
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.path}>
            {i > 1 && <span className="file-manager-breadcrumb-sep">/</span>}
            <button type="button" className="file-manager-breadcrumb-item" onClick={() => navigateTo(crumb.path)}>
              {crumb.label}
            </button>
          </span>
        ))}
      </div>

      {viewMode === "list" ? (
        <div className="file-manager-list">
          <FileListHeader />
          {createType && (
            <InlineCreateRow
              type={createType}
              onConfirm={handleCreateConfirm}
              onCancel={handleCreateCancel}
            />
          )}
          {files.length === 0 && !createType ? (
            <div className="file-manager-empty">{loading ? "Loading..." : "This directory is empty"}</div>
          ) : (
            files.map((file) => (
              <FileListRow
                key={file.path}
                file={file}
                selected={selectedPaths.has(file.path)}
                onClick={(e) => handleFileClick(file, e)}
                onDoubleClick={() => handleFileDoubleClick(file)}
              />
            ))
          )}
        </div>
      ) : (
        <div className="file-manager-icons">
          {createType && (
            <InlineCreateIcon
              type={createType}
              onConfirm={handleCreateConfirm}
              onCancel={handleCreateCancel}
            />
          )}
          {files.length === 0 && !createType ? (
            <div className="file-manager-empty">{loading ? "Loading..." : "This directory is empty"}</div>
          ) : (
            files.map((file) => (
              <FileIconItem
                key={file.path}
                file={file}
                selected={selectedPaths.has(file.path)}
                onClick={(e) => handleFileClick(file, e)}
                onDoubleClick={() => handleFileDoubleClick(file)}
              />
            ))
          )}
        </div>
      )}

      <div className="file-manager-statusbar">
        <span>{files.length} item(s)</span>
        {clipboard && (
          <span className="file-manager-clipboard-hint">
            <Clipboard size={12} /> {clipboard.action === "cut" ? "Cut" : "Copied"} {clipboard.paths.length} item(s) — <button type="button" onClick={() => setClipboard(null)}>clear</button>
          </span>
        )}
      </div>

      {viewingFile ? (
        <div className="file-manager-viewer-overlay">
          <Suspense fallback={<div className="file-manager-loading">Loading viewer...</div>}>
            <FileViewer
              containerId={containerId}
              file={viewingFile}
              onClose={() => setViewingFile(null)}
            />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}


const FILE_LIST_GRID_STYLE: CSSProperties = {
  gridTemplateColumns: "minmax(0, 1.2fr) 92px 168px 92px",
};

function FileListHeader() {
  return (
    <div className="file-manager-list-row file-manager-list-head" style={FILE_LIST_GRID_STYLE}>
      <div>Name</div>
      <div>Size</div>
      <div>Modified</div>
      <div>Perms</div>
    </div>
  );
}

function FileListRow({ file, selected, onClick, onDoubleClick }: {
  file: ContainerFileInfo;
  selected: boolean;
  onClick: (e: React.MouseEvent) => void;
  onDoubleClick: () => void;
}) {
  return (
    <div
      className={cx("file-manager-list-row", selected && "file-manager-list-row-selected")}
      style={FILE_LIST_GRID_STYLE}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
    >
      <div className="file-manager-name">
        {file.type === "directory" ? <Folder size={15} /> : file.type === "symlink" ? <File size={15} /> : <File size={15} />}
        <span>{file.name}</span>
      </div>
      <div className="file-manager-cell-muted">{file.type === "directory" ? "—" : formatBytes(file.size)}</div>
      <div className="file-manager-cell-muted">{formatDateTime(new Date(file.modified_at * 1000).toISOString())}</div>
      <div><Tag size="small">{file.permissions}</Tag></div>
    </div>
  );
}

function FileIconItem({ file, selected, onClick, onDoubleClick }: {
  file: ContainerFileInfo;
  selected: boolean;
  onClick: (e: React.MouseEvent) => void;
  onDoubleClick: () => void;
}) {
  return (
    <div
      className={cx("file-manager-icon-item", selected && "file-manager-icon-item-selected")}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      title={file.name}
    >
      {file.type === "directory" ? <FolderOpen size={32} /> : <File size={32} />}
      <span>{file.name}</span>
    </div>
  );
}

function InlineCreateInput({ type, onConfirm, onCancel, cancelOnBlur = false }: {
  type: "file" | "dir";
  onConfirm: (name: string) => void;
  onCancel: () => void;
  cancelOnBlur?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [name, setName] = useState("");

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const commit = () => {
    if (name.trim()) onConfirm(name);
    else onCancel();
  };

  return (
    <input
      ref={inputRef}
      className="file-manager-inline-input"
      value={name}
      onChange={(e) => setName(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") onCancel();
      }}
      onBlur={cancelOnBlur ? () => onCancel() : undefined}
      placeholder={type === "dir" ? "New folder" : "New file"}
    />
  );
}

function InlineCreateRow({ type, onConfirm, onCancel }: {
  type: "file" | "dir";
  onConfirm: (name: string) => void;
  onCancel: () => void;
}) {

  return (
    <div
      className="file-manager-list-row file-manager-create-row"
      style={FILE_LIST_GRID_STYLE}
    >
      <div className="file-manager-name">
        {type === "dir" ? <Folder size={15} /> : <File size={15} />}
        <InlineCreateInput type={type} onConfirm={onConfirm} onCancel={onCancel} />
      </div>
      <div className="file-manager-cell-muted">—</div>
      <div className="file-manager-cell-muted">—</div>
      <div className="file-manager-cell-muted">—</div>
    </div>
  );
}

function InlineCreateIcon({ type, onConfirm, onCancel }: {
  type: "file" | "dir";
  onConfirm: (name: string) => void;
  onCancel: () => void;
}) {
  return (
    <div className="file-manager-icon-item file-manager-create-row">
      {type === "dir" ? <FolderOpen size={32} /> : <File size={32} />}
      <InlineCreateInput type={type} onConfirm={onConfirm} onCancel={onCancel} cancelOnBlur />
    </div>
  );
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
