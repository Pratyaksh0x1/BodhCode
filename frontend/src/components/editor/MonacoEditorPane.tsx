import { useEffect, useRef } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type { EditorTab } from "./tabState";
import type { ResolvedEditorTheme } from "../../lib/theme";

type EditorInstance = Parameters<OnMount>[0];

export interface AiSelectionAction {
  path: string;
  start_line: number;
  end_line: number;
  text: string;
  action: "ask" | "edit";
}

interface MonacoEditorPaneProps {
  activeTab: EditorTab | null;
  onChangeContent: (content: string) => void;
  onSave: () => void;
  onCursorChange: (pos: { line: number; col: number }) => void;
  theme: ResolvedEditorTheme;
  saveStatus: "idle" | "saving" | "saved" | "error";
  errorMessage: string | null;
  onAskAiWithSelection?: (selection: AiSelectionAction) => void;
}

function getMonacoLanguage(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "ts":
    case "mts":
    case "cts":
    case "tsx":
      return "typescript";
    case "js":
    case "mjs":
    case "cjs":
    case "jsx":
      return "javascript";
    case "json":
      return "json";
    case "css":
      return "css";
    case "scss":
      return "scss";
    case "html":
      return "html";
    case "md":
    case "mdx":
      return "markdown";
    case "yml":
    case "yaml":
      return "yaml";
    case "toml":
      return "ini";
    case "svg":
    case "xml":
      return "xml";
    case "py":
      return "python";
    default:
      return "plaintext";
  }
}

export function MonacoEditorPane({
  activeTab,
  onChangeContent,
  onSave,
  onCursorChange,
  theme,
  saveStatus,
  errorMessage,
  onAskAiWithSelection,
}: MonacoEditorPaneProps) {
  const editorRef = useRef<EditorInstance | null>(null);
  const activeTabRef = useRef(activeTab);
  const onAskAiRef = useRef(onAskAiWithSelection);

  useEffect(() => {
    activeTabRef.current = activeTab;
    onAskAiRef.current = onAskAiWithSelection;
  }, [activeTab, onAskAiWithSelection]);

  const handleEditorMount: OnMount = (ed, monaco) => {
    editorRef.current = ed;

    // Track cursor changes
    ed.onDidChangeCursorPosition((e) => {
      onCursorChange({
        line: e.position.lineNumber,
        col: e.position.column,
      });
    });

    // Add Ctrl+S / Cmd+S save action directly in Monaco
    ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      onSave();
    });

    // Context menu actions for AI
    ed.addAction({
      id: "bodhcode.askAiAboutSelection",
      label: "Ask AI about selection",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 4,
      run: (editor) => {
        const sel = editor.getSelection();
        if (sel && !sel.isEmpty() && activeTabRef.current) {
          const model = editor.getModel();
          const text = model?.getValueInRange(sel) || "";
          onAskAiRef.current?.({
            path: activeTabRef.current.path,
            start_line: sel.startLineNumber,
            end_line: sel.endLineNumber,
            text,
            action: "ask",
          });
        }
      },
    });

    ed.addAction({
      id: "bodhcode.askAiToEditSelection",
      label: "Ask AI to edit selection",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 5,
      run: (editor) => {
        const sel = editor.getSelection();
        if (sel && !sel.isEmpty() && activeTabRef.current) {
          const model = editor.getModel();
          const text = model?.getValueInRange(sel) || "";
          onAskAiRef.current?.({
            path: activeTabRef.current.path,
            start_line: sel.startLineNumber,
            end_line: sel.endLineNumber,
            text,
            action: "edit",
          });
        }
      },
    });
  };

  // Sync cursor position on tab switch
  useEffect(() => {
    if (editorRef.current) {
      const pos = editorRef.current.getPosition();
      if (pos) {
        onCursorChange({ line: pos.lineNumber, col: pos.column });
      }
    }
  }, [activeTab?.path, onCursorChange]);

  if (!activeTab) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-neutral-950 text-neutral-500 gap-3 select-none">
        <svg className="w-12 h-12 text-neutral-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <p className="text-sm font-medium">Select a file from the explorer or press <kbd className="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-300 font-mono text-xs">Ctrl+P</kbd> to search</p>
      </div>
    );
  }

  const language = getMonacoLanguage(activeTab.path);

  return (
    <div className="relative h-full w-full flex flex-col overflow-hidden bg-neutral-950">
      {/* Toast Save Status Banner */}
      {saveStatus === "saved" && (
        <div className="absolute top-2 right-4 z-20 px-3 py-1 rounded bg-emerald-900/90 text-emerald-200 text-xs font-semibold shadow-lg border border-emerald-700/80 animate-fade-in flex items-center gap-1.5">
          <span>✓</span>
          <span>Saved</span>
        </div>
      )}

      {saveStatus === "saving" && (
        <div className="absolute top-2 right-4 z-20 px-3 py-1 rounded bg-neutral-800 text-neutral-200 text-xs font-medium shadow-lg border border-neutral-700 flex items-center gap-1.5">
          <div className="w-3 h-3 border-2 border-orange-400 border-t-transparent rounded-full animate-spin" />
          <span>Saving...</span>
        </div>
      )}

      {/* Error Banner */}
      {errorMessage && (
        <div className="p-3 bg-rose-950/80 border-b border-rose-800 text-rose-200 text-xs flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <span className="font-bold">Error:</span>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Monaco Editor Component */}
      <div className="flex-1 w-full overflow-hidden">
        <Editor
          key={activeTab.path}
          path={activeTab.path}
          value={activeTab.content}
          language={language}
          theme={theme}
          onChange={(value) => {
            onChangeContent(value ?? "");
          }}
          onMount={handleEditorMount}
          options={{
            minimap: { enabled: true },
            wordWrap: "off",
            fontLigatures: false,
            tabSize: 2,
            automaticLayout: true,
            scrollBeyondLastLine: false,
            fontSize: 13,
            lineNumbers: "on",
            renderWhitespace: "selection",
          }}
        />
      </div>
    </div>
  );
}
