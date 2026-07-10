import { Button, Toast } from "@douyinfe/semi-ui";
import { Download, Edit3, Save, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { downloadContainerFiles, readContainerFile, writeContainerFile } from "../../shared/api/sandboxContainers";
import { showApiError } from "../../shared/api/feedback";
import type { ContainerFileInfo } from "../../shared/api/types";

const CodeEditor = lazy(() => import("./CodeEditor").then((module) => ({ default: module.CodeEditor })));

type ViewerType = "text" | "image" | "binary";

type Props = {
  containerId: number;
  file: ContainerFileInfo;
  onClose: () => void;
};

const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "json", "xml", "yaml", "yml", "toml", "ini", "cfg",
  "conf", "log", "csv", "tsv", "env", "gitignore", "dockerignore", "editorconfig",
  "ts", "tsx", "js", "jsx", "mjs", "cjs", "py", "pyx", "go", "rs", "java", "c",
  "cpp", "cc", "cxx", "h", "hpp", "hh", "hxx", "sh", "bash", "zsh", "fish",
  "ps1", "bat", "cmd", "Makefile", "Dockerfile", "sql", "html", "htm", "css",
  "scss", "less", "vue", "svelte", "graphql", "gql", "proto", "tf", "tfvars",
  "rb", "php", "swift", "kt", "scala", "lua", "r", "pl", "pm", "patch", "diff",
  "lock", "nix", "ex", "exs", "erl", "hs", "elm", "nim", "zig", "v", "wren",
  "rst", "tex", "bib", "cfg", "cnf", "service", "socket", "timer", "desktop",
  "svg",
]);

const IMAGE_EXTENSIONS = new Set([
  "png", "jpg", "jpeg", "gif", "webp", "ico", "bmp", "tiff", "tif", "avif",
]);

const IMAGE_MIME: Record<string, string> = {
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif",
  webp: "image/webp", ico: "image/x-icon", bmp: "image/bmp",
  tiff: "image/tiff", tif: "image/tiff", avif: "image/avif",
};

function ext(name: string): string {
  const dot = name.lastIndexOf(".");
  if (dot < 0) return "";
  return name.slice(dot + 1).toLowerCase();
}

function determineViewerType(file: ContainerFileInfo): ViewerType {
  if (file.type === "directory") return "binary";
  const e = ext(file.name);
  if (IMAGE_EXTENSIONS.has(e)) return "image";
  if (TEXT_EXTENSIONS.has(e)) return "text";
  // heuristic: if size < 1MB and no null bytes → treat as text, else binary
  if (file.size > 1_000_000) return "binary";
  return "text";
}

export function FileViewer({ containerId, file, onClose }: Props) {
  const viewerType = useMemo(() => determineViewerType(file), [file]);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: { path: string; base64?: boolean } = { path: file.path };
      if (viewerType === "image") params.base64 = true;
      const response = await readContainerFile(containerId, params);
      setContent(response.data?.content ?? "");
    } catch (err) {
      setError("Failed to read file");
      showApiError(err);
    } finally {
      setLoading(false);
    }
  }, [containerId, file.path, viewerType]);

  useEffect(() => { void load(); }, [load]);

  const imageSrc = useMemo(() => {
    if (viewerType !== "image" || !content) return "";
    const mime = IMAGE_MIME[ext(file.name)] || "image/png";
    // content may include newlines from base64; strip them for data URI
    return `data:${mime};base64,${content.replace(/\s/g, "")}`;
  }, [viewerType, content, file.name]);

  const lineCount = useMemo(() => {
    if (viewerType !== "text") return 0;
    return content.split("\n").length;
  }, [viewerType, content]);

  const handleEdit = useCallback(() => {
    setEditContent(content);
    setEditing(true);
  }, [content]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await writeContainerFile(containerId, { path: file.path, content: editContent });
      Toast.success("File saved");
      setContent(editContent);
      setEditing(false);
    } catch (err) {
      showApiError(err);
    } finally {
      setSaving(false);
    }
  }, [containerId, file.path, editContent]);

  const handleCancelEdit = useCallback(() => {
    setEditContent("");
    setEditing(false);
  }, []);

  const handleDownload = useCallback(async () => {
    try {
      const { blob, filename } = await downloadContainerFiles(containerId, { path: [file.path] });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showApiError(err);
    }
  }, [containerId, file.path]);

  return (
    <div className="fv-body">
      <div className="fv-toolbar">
        <span className="fv-title">{file.name}</span>
        <span className="fv-meta">
          {viewerType === "text" ? "Text" : viewerType === "image" ? "Image" : "Binary"}
          {" · "}{file.size.toLocaleString()} bytes
          {viewerType === "text" ? ` · ${lineCount} lines` : ""}
        </span>
        <span className="fv-spacer" />
        {viewerType === "text" && !editing && (
          <Button icon={<Edit3 size={14} />} theme="borderless" type="tertiary" size="small" onClick={handleEdit}>Edit</Button>
        )}
        {!editing && (
          <Button icon={<Download size={14} />} theme="borderless" type="tertiary" size="small" onClick={() => void handleDownload()}>Download</Button>
        )}
        <Button icon={<X size={14} />} theme="borderless" size="small" type="tertiary" onClick={onClose}>Close</Button>
      </div>

      {loading ? (
        <div className="fv-loading">Loading...</div>
      ) : error ? (
        <div className="fv-error">{error}</div>
      ) : viewerType === "image" ? (
        <div className="fv-image-viewer">
          {imageSrc ? (
            <img src={imageSrc} alt={file.name} className="fv-image" />
          ) : (
            <div className="fv-error">Failed to render image</div>
          )}
        </div>
      ) : viewerType === "text" ? (
        editing ? (
          <div className="fv-editor">
            <div className="fv-editor-cm">
              <Suspense fallback={<div className="fv-loading">Loading editor...</div>}>
                <CodeEditor
                  value={editContent}
                  onChange={setEditContent}
                  filename={file.name}
                />
              </Suspense>
            </div>
            <div className="fv-editor-actions">
              <Button icon={<Save size={14} />} size="small" type="primary" loading={saving} onClick={() => void handleSave()}>Save</Button>
              <Button icon={<X size={14} />} size="small" type="tertiary" disabled={saving} onClick={handleCancelEdit}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="fv-preview">
            <Suspense fallback={<div className="fv-loading">Loading preview...</div>}>
              <CodeEditor
                value={content}
                readOnly
                filename={file.name}
              />
            </Suspense>
          </div>
        )
      ) : (
        <div className="fv-binary">
          <div className="fv-binary-icon" />
          <p>Binary file cannot be previewed</p>
          <span>{file.size.toLocaleString()} bytes</span>
        </div>
      )}
    </div>
  );
}
