import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

export function AuthDesktopSuccess() {
  const [searchParams] = useSearchParams();
  const ticket = searchParams.get("ticket");

  useEffect(() => {
    // Attempt to focus or trigger deep link in desktop
    try {
      window.location.href = `bodhcode://auth-success?ticket=${ticket || ""}`;
    } catch {
      // Ignore if protocol is not registered
    }
  }, [ticket]);

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center p-6 text-center">
      <div className="w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-2xl p-8 shadow-2xl space-y-5">
        <div className="w-16 h-16 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center text-3xl mx-auto border border-emerald-500/40">
          ✓
        </div>

        <div className="space-y-2">
          <h1 className="text-xl font-bold tracking-tight text-white">
            Authentication Successful!
          </h1>
          <p className="text-sm text-neutral-400">
            Your account has been connected to BodhCode Studio. You can now close this Chrome tab and return to the desktop app.
          </p>
        </div>

        <div className="pt-2">
          <a
            href={`bodhcode://auth-success?ticket=${ticket || ""}`}
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-xs font-semibold shadow-lg shadow-orange-500/20 transition-transform active:scale-95"
          >
            <span>Return to BodhCode Studio</span>
            <span>&rarr;</span>
          </a>
        </div>
      </div>
    </div>
  );
}
