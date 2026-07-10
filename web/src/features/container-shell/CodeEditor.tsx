import { basicSetup } from "codemirror";
import { EditorView } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import type { Extension } from "@codemirror/state";
import { useEffect, useMemo, useRef, useState } from "react";

type Props = {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  filename?: string;
};

async function resolveLanguage(filename: string): Promise<Extension[] | null> {
  if (!filename) return null;
  const base = filename.split("/").pop() || filename;
  const e = base.includes(".") ? base.slice(base.lastIndexOf(".") + 1).toLowerCase() : "";
  const key = base === "Dockerfile" ? "Dockerfile" : base === "Makefile" ? "Makefile" : e;
  if (!key) return null;

  switch (key) {
    case "js": case "jsx": case "mjs": case "cjs": {
      const { javascript } = await import("@codemirror/lang-javascript");
      return [javascript()];
    }
    case "ts": {
      const { javascript } = await import("@codemirror/lang-javascript");
      return [javascript({ typescript: true })];
    }
    case "tsx": {
      const { javascript } = await import("@codemirror/lang-javascript");
      return [javascript({ typescript: true, jsx: true })];
    }
    case "py": case "pyx": {
      const { python } = await import("@codemirror/lang-python");
      return [python()];
    }
    case "json": {
      const { json } = await import("@codemirror/lang-json");
      return [json()];
    }
    case "html": case "htm": {
      const { html } = await import("@codemirror/lang-html");
      return [html()];
    }
    case "css": case "scss": case "less": {
      const { css } = await import("@codemirror/lang-css");
      return [css()];
    }
    case "xml": case "svg": {
      const { xml } = await import("@codemirror/lang-xml");
      return [xml()];
    }
    case "sql": {
      const { sql } = await import("@codemirror/lang-sql");
      return [sql()];
    }
    case "md": case "markdown": {
      const { markdown } = await import("@codemirror/lang-markdown");
      return [markdown()];
    }
    case "yaml": case "yml": {
      const [{ StreamLanguage }, { yaml }] = await Promise.all([
        import("@codemirror/language"),
        import("@codemirror/legacy-modes/mode/yaml"),
      ]);
      return [StreamLanguage.define(yaml)];
    }
    case "rs": {
      const { rust } = await import("@codemirror/lang-rust");
      return [rust()];
    }
    case "go": {
      const { go } = await import("@codemirror/lang-go");
      return [go()];
    }
    case "java": {
      const { java } = await import("@codemirror/lang-java");
      return [java()];
    }
    case "c": case "cpp": case "cc": case "cxx": case "h": case "hpp": case "hh": case "hxx": {
      const { cpp } = await import("@codemirror/lang-cpp");
      return [cpp()];
    }
    case "php": {
      const { php } = await import("@codemirror/lang-php");
      return [php()];
    }
    case "sh": case "bash": case "zsh": {
      const [{ StreamLanguage }, { shell }] = await Promise.all([
        import("@codemirror/language"),
        import("@codemirror/legacy-modes/mode/shell"),
      ]);
      return [StreamLanguage.define(shell)];
    }
    case "Dockerfile": {
      const [{ StreamLanguage }, { dockerFile }] = await Promise.all([
        import("@codemirror/language"),
        import("@codemirror/legacy-modes/mode/dockerfile"),
      ]);
      return [StreamLanguage.define(dockerFile)];
    }
    default: return null;
  }
}

export function CodeEditor({ value, onChange, readOnly = false, filename }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const [languageExtensions, setLanguageExtensions] = useState<Extension[]>([]);
  onChangeRef.current = onChange;

  const updateListener = useMemo(
    () => EditorView.updateListener.of((update) => {
      if (update.docChanged) onChangeRef.current?.(update.state.doc.toString());
    }),
    [],
  );

  useEffect(() => {
    let canceled = false;
    resolveLanguage(filename || "")
      .then((extensions) => {
        if (!canceled) setLanguageExtensions(extensions ?? []);
      })
      .catch(() => {
        if (!canceled) setLanguageExtensions([]);
      });
    return () => { canceled = true; };
  }, [filename]);

  useEffect(() => {
    if (!hostRef.current) return;

    const exts: Extension[] = [
      basicSetup,
      oneDark,
      updateListener,
      EditorView.lineWrapping,
      ...languageExtensions,
    ];
    if (readOnly) {
      exts.push(EditorState.readOnly.of(true));
      exts.push(EditorView.editable.of(false));
    }

    const view = new EditorView({
      doc: value,
      extensions: exts,
      parent: hostRef.current,
    });
    viewRef.current = view;
    return () => view.destroy();
  }, [readOnly, updateListener, languageExtensions]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.hasFocus) return;
    const current = view.state.doc.toString();
    if (value !== current) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: value } });
    }
  }, [value]);

  return <div ref={hostRef} className="cm-host" />;
}
