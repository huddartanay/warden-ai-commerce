import type { ScenarioEnvelope } from "@/lib/types";
import { formatRupees } from "@/lib/api";
import { CheckLine, DecisionBadge, Section, Tone } from "./atoms";

interface CheckRow {
  label: string;
  value: string;
  tone: Tone;
  detail?: string;
}

/**
 * Distills the raw WARDEN_EVALUATED audit event into the 7 pillar checks the
 * dashboard highlights. Falls back to a generic mapping when the audit
 * payload isn't populated (e.g. AGENT_AUTH_FAILED, which bypasses the engine
 * and has no `checks_performed`).
 */
function summarizePillars(env: ScenarioEnvelope | null): CheckRow[] {
  if (!env?.audit?.length) return [];
  const wardenEvt = env.audit.find((e) => e.event_type === "WARDEN_EVALUATED");
  const rawChecks = ((wardenEvt?.event_data?.checks as unknown[]) ?? []) as Array<{
    name: string;
    ok: boolean;
    verdict: string;
    reason_code: string | null;
    detail: string;
  }>;
  const map = new Map(rawChecks.map((c) => [c.name, c]));

  const mandate = env.mandate;
  const spendVal =
    mandate?.current_period_spend && mandate?.max_amount
      ? `${formatRupees(mandate.current_period_spend)} / ${formatRupees(mandate.max_amount)}`
      : "—";
  const velocityVal = mandate
    ? `${mandate.current_period_transactions} / ${mandate.transaction_limit}`
    : "—";

  const toneForCheck = (name: string): Tone => {
    const c = map.get(name);
    if (!c) return "neutral";
    if (c.verdict === "STEP_UP") return "warn";
    return c.ok ? "ok" : "bad";
  };

  const detailForCheck = (name: string): string | undefined => {
    const c = map.get(name);
    return c?.detail;
  };

  return [
    {
      label: "Mandate",
      value: map.get("mandate_status")?.ok ? "Valid" : "Invalid",
      tone: toneForCheck("mandate_status"),
      detail: detailForCheck("mandate_status"),
    },
    {
      label: "Customer",
      value: map.get("customer_match")?.ok ? "Verified" : "Mismatch",
      tone: toneForCheck("customer_match"),
      detail: detailForCheck("customer_match"),
    },
    {
      label: "Category",
      value: map.get("category_allowed")?.ok ? "Allowed" : "Out of scope",
      tone: toneForCheck("category_allowed"),
      detail: detailForCheck("category_allowed"),
    },
    {
      label: "Spend",
      value: spendVal,
      tone: toneForCheck("amount_within_cap"),
      detail: detailForCheck("amount_within_cap"),
    },
    {
      label: "Velocity",
      value: velocityVal,
      tone: toneForCheck("transaction_frequency"),
      detail: detailForCheck("transaction_frequency"),
    },
    {
      label: "Price",
      value: map.get("price_drift")?.ok ? "No drift" : "Drift",
      tone: toneForCheck("price_drift"),
      detail: detailForCheck("price_drift"),
    },
    {
      label: "Idempotency",
      value: env.action?.idempotency_key ? "Unique key" : "—",
      tone: env.audit?.some((e) => e.event_type === "DUPLICATE_DETECTED")
        ? "warn"
        : "ok",
      detail: env.audit?.some((e) => e.event_type === "DUPLICATE_DETECTED")
        ? "Duplicate submission — returned the original decision"
        : env.action?.idempotency_key,
    },
  ];
}

export function WardenPanel({ env }: { env: ScenarioEnvelope | null }) {
  const decision = env?.decision;
  const rows = summarizePillars(env);

  return (
    <div className="card-hero p-5 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="section-label">Warden</div>
          <div className="text-lg font-semibold tracking-tight">
            Deterministic authorization
          </div>
        </div>
        {env?.scenario ? (
          <span className="mono text-[11px] text-[color:var(--text-3)]">
            scenario · {env.scenario}
          </span>
        ) : null}
      </div>

      {rows.length ? (
        <div className="flex flex-col divide-y divide-[color:var(--border)] mb-5">
          {rows.map((r) => (
            <CheckLine key={r.label} {...r} />
          ))}
        </div>
      ) : (
        <div className="text-[13px] text-[color:var(--text-3)] mb-5">
          No decision yet. Click a demo scenario to see Warden's checks run.
        </div>
      )}

      {decision ? (
        <DecisionBadge
          result={decision.result}
          reason={decision.reason_code}
          className="mt-auto"
        />
      ) : (
        <div className="mt-auto border border-dashed border-[color:var(--border-strong)] rounded-lg px-4 py-6 text-center text-[color:var(--text-3)] text-sm">
          Awaiting proposal
        </div>
      )}

      {decision?.explanation ? (
        <p className="text-[12px] text-[color:var(--text-2)] mt-3 leading-snug">
          {decision.explanation}
        </p>
      ) : null}
    </div>
  );
}
