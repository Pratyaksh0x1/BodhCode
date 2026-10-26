import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useMe } from "../lib/auth";

interface RequireAuthProps {
  children?: ReactNode;
}

export function RequireAuth({ children }: RequireAuthProps) {
  const { data: user, isLoading } = useMe();
  const location = useLocation();

  if (isLoading) {
    return (
      <div id="auth-loading-skeleton" className="space-y-6 max-w-4xl mx-auto py-8 animate-pulse" aria-busy="true">
        <div className="h-8 bg-slate-800/60 rounded-md w-1/3" />
        <div className="h-4 bg-slate-800/40 rounded w-1/2" />
        <div className="h-48 bg-slate-900/50 border border-slate-800 rounded-lg p-6 space-y-4">
          <div className="h-5 bg-slate-800/60 rounded w-1/4" />
          <div className="h-4 bg-slate-800/40 rounded w-3/4" />
          <div className="h-4 bg-slate-800/30 rounded w-2/3" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <Navigate
        to="/?auth_required=1"
        replace
        state={{ from: location.pathname, notice: "Sign in to continue" }}
      />
    );
  }

  return children ? <>{children}</> : <Outlet />;
}
