import React, { useEffect } from "react";
import { useRateLimitStore } from "../../store/rateLimitStore";

export function RateLimitBanner(): React.ReactElement | null {
  const { active, secondsRemaining, message, tick, dismiss } = useRateLimitStore();

  useEffect(() => {
    if (!active || secondsRemaining <= 0) return;

    const interval = setInterval(() => {
      tick();
    }, 1000);

    return () => clearInterval(interval);
  }, [active, secondsRemaining, tick]);

  if (!active || secondsRemaining <= 0) {
    return null;
  }

  return (
    <div
      role="alert"
      data-testid="rate-limit-banner"
      className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-lg w-[90%] bg-amber-950/90 border border-amber-500/60 text-amber-100 rounded-lg shadow-xl p-4 backdrop-blur-md transition-all duration-300 animate-in fade-in slide-in-from-top-4"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-amber-500/20 text-amber-400 rounded-md shrink-0">
          <svg
            className="w-5 h-5 animate-spin"
            style={{ animationDuration: "3s" }}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-semibold text-sm text-amber-200">
              Please Slow Down
            </h4>
            <span className="px-2 py-0.5 text-xs font-mono font-bold bg-amber-500/30 text-amber-300 rounded border border-amber-500/40">
              {secondsRemaining}s
            </span>
          </div>
          <p className="text-xs text-amber-200/90 mt-1 leading-relaxed">
            {message}
          </p>
          <p className="text-[11px] text-amber-300/70 mt-1">
            Actions will resume automatically in {secondsRemaining} second{secondsRemaining !== 1 ? "s" : ""}.
          </p>
        </div>

        <button
          onClick={dismiss}
          className="text-amber-400 hover:text-amber-200 p-1 rounded transition-colors shrink-0"
          aria-label="Dismiss rate limit notice"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
