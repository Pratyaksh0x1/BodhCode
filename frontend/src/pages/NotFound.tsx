import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="text-center py-16 space-y-4">
      <h1 className="text-4xl font-extrabold text-slate-100">404</h1>
      <p className="text-slate-400">The requested page could not be found.</p>
      <div>
        <Link
          to="/"
          className="inline-block px-4 py-2 text-sm font-medium rounded-md bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
        >
          Return Home
        </Link>
      </div>
    </div>
  );
}
