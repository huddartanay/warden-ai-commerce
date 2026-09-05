import type {
  ActionDetail,
  AuditListResponse,
  AuditVerifyResponse,
  DemoSummary,
  ScenarioEnvelope,
} from "./types";

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

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText, path);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  status: number;
  path: string;
  constructor(status: number, message: string, path: string) {
    super(`${status} ${path}: ${message}`);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

// ---- Health --------------------------------------------------------------

export function fetchReadiness(): Promise<ReadinessResponse | { error: string }> {
  return jsonFetch<ReadinessResponse>("/health/ready").catch((e) => ({
    error: e instanceof Error ? e.message : "Unknown error",
  }));
}

// ---- Demo ----------------------------------------------------------------

export const SCENARIO_NAMES = [
  "successful_purchase",
  "cap_exceeded",
  "step_up",
  "duplicate",
  "price_drift",
  "payment_failure",
] as const;
export type ScenarioName = (typeof SCENARIO_NAMES)[number];

export const SCENARIO_LABELS: Record<ScenarioName, string> = {
  successful_purchase: "Run Successful Purchase",
  cap_exceeded: "Run Cap Exceeded",
  step_up: "Run Step-Up",
  duplicate: "Run Duplicate",
  price_drift: "Run Price Drift",
  payment_failure: "Run Payment Failure",
};

export function runScenario(name: ScenarioName): Promise<ScenarioEnvelope> {
  return jsonFetch<ScenarioEnvelope>(`/demo/scenario/${name}`, {
    method: "POST",
  });
}

export function resetDemo(): Promise<{ ok: boolean; note: string }> {
  return jsonFetch(`/demo/reset`, { method: "POST" });
}

export function fetchDemoSummary(): Promise<DemoSummary> {
  return jsonFetch<DemoSummary>(`/demo/summary`);
}

// ---- Warden --------------------------------------------------------------

export function fetchAction(actionId: string): Promise<ActionDetail> {
  return jsonFetch<ActionDetail>(`/warden/action/${actionId}`);
}

export function approveAction(actionId: string): Promise<unknown> {
  return jsonFetch(`/warden/approve/${actionId}`, { method: "POST" });
}

export function revokeMandate(mandateId: string): Promise<unknown> {
  return jsonFetch(`/warden/revoke-mandate/${mandateId}`, { method: "POST" });
}

// ---- Audit ---------------------------------------------------------------

export function fetchAuditForAction(actionId: string): Promise<AuditListResponse> {
  return jsonFetch<AuditListResponse>(`/audit/action/${actionId}`);
}

export function fetchAuditForMandate(mandateId: string): Promise<AuditListResponse> {
  return jsonFetch<AuditListResponse>(`/audit/mandate/${mandateId}`);
}

export function verifyAuditChain(): Promise<AuditVerifyResponse> {
  return jsonFetch<AuditVerifyResponse>(`/audit/verify`);
}

export function resolveAction(
  actionId: string,
  body: {
    new_action_status?: string;
    note?: string;
    resolved_by?: string;
  },
): Promise<unknown> {
  return jsonFetch(`/audit/resolve/${actionId}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---- Formatting helpers -------------------------------------------------

export function formatRupees(raw: string | number | null | undefined): string {
  if (raw === null || raw === undefined || raw === "") return "—";
  const n = typeof raw === "number" ? raw : Number(raw);
  if (Number.isNaN(n)) return String(raw);
  return `₹${n.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function shortHash(h: string | null | undefined, n = 10): string {
  if (!h) return "—";
  return `${h.slice(0, n)}…`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}
