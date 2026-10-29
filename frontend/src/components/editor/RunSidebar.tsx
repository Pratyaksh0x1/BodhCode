import { useState } from "react";
import { api } from "../../lib/api";

interface RunSidebarProps {
  repoId: number | string;
  onExecuteCommand?: (cmd: string) => void;
}

interface CommandRunResult {
  stdout: string;
  stderr: string;
  returncode: number;
  duration_ms: number;
}

const COMMON_COMMANDS = [
  { label: "Run Unit Tests", cmd: "npm test", desc: "Execute Jest / Vitest test runner" },
  { label: "Build Project", cmd: "npm run build", desc: "Run Vite / Webpack / TypeScript build" },
  { label: "Lint Codebase", cmd: "npm run lint", desc: "Run ESLint or Ruff static analysis" },
  { label: "Git Status", cmd: "git status", desc: "Inspect changed files in working tree" },
  { label: "Install Packages", cmd: "npm install", desc: "Install node package dependencies" },
];

export function RunSidebar({ repoId, onExecuteCommand }: RunSidebarProps) {
  const [customCmd, setCustomCmd] = useState("");
  const [runningCmd, setRunningCmd] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<CommandRunResult | null>(null);

  const runCommand = async (command: string) => {
    if (!command.trim() || runningCmd) return;
    setRunningCmd(command);

    if (onExecuteCommand) {
      onExecuteCommand(command);
    }

    try {
      const res = await api<CommandRunResult>(`/repos/${repoId}/terminal/exec`, {
        method: "POST",
        body: JSON.stringify({ command }),
      });
      setLastResult(res);
    } catch (err: unknown) {
      setLastResult({
        stdout: "",
        stderr: err instanceof Error ? err.message : "Execution failed",
        returncode: -1,
        duration_ms: 0,
      });
    } finally {
      setRunningCmd(null);
    }
  };

  return (
    <div className="w-80 bg-neutral-900 border-r border-neutral-800 flex flex-col h-full text-xs text-neutral-300 overflow-hidden select-none">
      {/* Header */}
      <div className="px-4 py-3 border-b border-neutral-800 bg-neutral-900/90 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-orange-400 font-bold">▶️</span>
          <span className="font-semibold uppercase tracking-wider text-[11px] text-neutral-200">
            Run &amp; Debug
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Custom CLI command runner */}
        <div className="space-y-1.5">
          <label htmlFor="custom-cmd-input" className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
            Run Command in Repo Root
          </label>
          <div className="flex items-center gap-1.5">
            <input
              id="custom-cmd-input"
              type="text"
              placeholder="e.g. node index.js or npm test"
              value={customCmd}
              onChange={(e) => setCustomCmd(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") runCommand(customCmd);
              }}
              className="flex-1 px-2.5 py-1.5 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-200 font-mono text-[11px] focus:outline-none focus:border-orange-500"
            />
            <button
              type="button"
              onClick={() => runCommand(customCmd)}
              disabled={!customCmd.trim() || runningCmd !== null}
              className="px-3 py-1.5 rounded-lg bg-orange-500 hover:bg-orange-600 text-white font-semibold text-[11px] disabled:opacity-50 cursor-pointer"
            >
              Run
            </button>
          </div>
        </div>

        {/* Standard Scripts */}
        <div className="space-y-2">
          <div className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
            Common Scripts
          </div>
          <div className="space-y-1.5">
            {COMMON_COMMANDS.map((item) => (
              <div
                key={item.cmd}
                className="p-2.5 rounded-xl bg-neutral-950/60 border border-neutral-800 hover:border-neutral-700 transition-colors flex items-center justify-between"
              >
                <div>
                  <h4 className="font-semibold text-neutral-200 text-[11px]">{item.label}</h4>
                  <p className="text-[10px] text-neutral-500 font-mono">{item.cmd}</p>
                </div>
                <button
                  type="button"
                  onClick={() => runCommand(item.cmd)}
                  disabled={runningCmd !== null}
                  className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-orange-500 hover:text-white text-neutral-300 font-semibold text-[10px] transition-colors cursor-pointer disabled:opacity-50"
                >
                  {runningCmd === item.cmd ? "Running..." : "Execute"}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Execution Output Preview */}
        {lastResult && (
          <div className="p-3 rounded-xl bg-neutral-950 border border-neutral-800 space-y-2">
            <div className="flex items-center justify-between text-[11px]">
              <span
                className={`font-semibold ${
                  lastResult.returncode === 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                Exit Code: {lastResult.returncode}
              </span>
              <span className="text-neutral-500 font-mono">{lastResult.duration_ms}ms</span>
            </div>
            <pre className="font-mono text-[10px] bg-black/60 p-2.5 rounded-lg border border-neutral-850 overflow-x-auto max-h-36 whitespace-pre-wrap text-neutral-300">
              {lastResult.stdout || lastResult.stderr || "(No output produced)"}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

