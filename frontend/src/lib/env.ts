const rawApiUrl = import.meta.env.VITE_API_URL;

if (!rawApiUrl || typeof rawApiUrl !== "string" || !rawApiUrl.trim()) {
  throw new Error(
    "Missing required environment variable: VITE_API_URL. Please set VITE_API_URL in frontend/.env",
  );
}

export const VITE_API_URL: string = rawApiUrl.trim().replace(/\/+$/, "");
