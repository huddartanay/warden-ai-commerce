export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ReadinessResponse = {
  status: "ok" | "degraded";
  service: string;
  checks: {
    database: {
      ok: boolean;
      error: string | null;
    };
  };
};

export async function fetchReadiness(): Promise<ReadinessResponse | { error: string }> {
  try {
    const res = await fetch(`${API_BASE_URL}/health/ready`, { cache: "no-store" });
    if (!res.ok) return { error: `HTTP ${res.status}` };
    return (await res.json()) as ReadinessResponse;
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Unknown error" };
  }
}
