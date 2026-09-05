import type { ScenarioEnvelope } from "@/lib/types";
import { formatRupees } from "@/lib/api";
import {
  CheckLine,
  DecisionBadge,
  KV,
  Pill,
  Section,
  Tone,
  TrustNote,
} from "./atoms";

interface CheckRow {
  label: string;
  value: string;
  tone: Tone;
  detail?: string;
}

function summarizePillars(env: ScenarioEnvelope | null): CheckRow[] {
  if (!env?.audit?.length) return [];
  const wardenEvt = env.audit.find(
    (e) => e.event_type === "WARDEN_EVALUATED" && e.action_id === env.action?.id,
  );
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
      label: "Mandate valid",
      value: map.get("mandate_status")?.ok ? "Active" : "Invalid",
      tone: toneForCheck("mandate_status"),
      detail: detailForCheck("mandate_status"),
    },
    {
      label: "Customer verified",
      value: map.get("customer_match")?.ok ? "Verified" : "Mismatch",
      tone: toneForCheck("customer_match"),
      detail: detailForCheck("customer_match"),
    },
    {
      label: "Merchant verified",
      value: map.get("merchant_match")?.ok ? "Verified" : "Mismatch",
      tone: toneForCheck("merchant_match"),
      detail: detailForCheck("merchant_match"),
    },
    {
      label: "Category allowed",
      value: map.get("category_allowed")?.ok ? "In scope" : "Out of scope",
      tone: toneForCheck("category_allowed"),
      detail: detailForCheck("category_allowed"),
    },
    {
      label: "Spend limit",
      value: spendVal,
      tone: toneForCheck("amount_within_cap"),
      detail: detailForCheck("amount_within_cap"),
    },
    {
      label: "Velocity limit",
      value: velocityVal,
      tone: toneForCheck("transaction_frequency"),
      detail: detailForCheck("transaction_frequency"),
    },
    {
      label: "Price unchanged",
      value: map.get("price_drift")?.ok ? "No drift" : "Drift detected",
      tone: toneForCheck("price_drift"),
      detail: detailForCheck("price_drift"),
    },
    {
      label: "Duplicate check",
      value: env.audit?.some((e) => e.event_type === "DUPLICATE_DETECTED")
        ? "Duplicate replay"
        : "Unique",
      tone: env.audit?.some((e) => e.event_type === "DUPLICATE_DETECTED")
        ? "warn"
        : "ok",
      detail: env.audit?.some((e) => e.event_type === "DUPLICATE_DETECTED")
        ? "Idempotency short-circuit returned the original decision"
        : env.action?.idempotency_key,
    },
  ];
}

function razorpayLine(env: ScenarioEnvelope | null): {
  label: string;
  tone: "ok" | "warn" | "bad" | "neutral";
} {
  if (!env?.action) return { label: "Not called", tone: "neutral" };
  const decision = env.decision?.result;
  const refs = env.razorpay_refs ?? [];
  if (decision === "BLOCK") return { label: "Not called (blocked)", tone: "neutral" };
  if (decision === "STEP_UP")
    return { label: "Waiting for human approval", tone: "warn" };
  if (refs.some((r) => r.ref_type === "order")) {
    if (env.action.status === "PENDING_UNRESOLVED")
      return { label: "Capture uncertain", tone: "warn" };
    if (env.action.status === "PAYMENT_FAILED")
      return { label: "Capture failed", tone: "bad" };
    if (env.action.status === "PAYMENT_COMPLETED")
      return { label: "Payment completed", tone: "ok" };
    return { label: "Test order created", tone: "ok" };
  }
  return { label: "Not called", tone: "neutral" };
}

function whyList(rows: CheckRow[], decision: string | undefined): {
  glyph: string;
  text: string;
  tone: Tone;
}[] {
  if (decision === "BLOCK") {
    const failing = rows.find((r) => r.tone === "bad");
    if (failing) {
      return [
        { glyph: "✕", tone: "bad", text: failing.detail || failing.label },
      ];
    }
  }
  if (decision === "STEP_UP") {
    const stepUp = rows.find((r) => r.tone === "warn");
    if (stepUp) {
      return [
        {
          glyph: "!",
          tone: "warn",
          text: stepUp.detail || "Requires human approval",
        },
      ];
    }
  }
  // ALLOW: list top pass reasons
  return rows
    .filter((r) => r.tone === "ok")
    .slice(0, 5)
    .map((r) => ({ glyph: "✓", tone: "ok" as const, text: `${r.label}: ${r.value}` }));
}

export function WardenPanel({ env }: { env: ScenarioEnvelope | null }) {
  const decision = env?.decision;
  const rows = summarizePillars(env);
  const mandate = env?.mandate;
  const rzp = razorpayLine(env);
  const why = whyList(rows, decision?.result);

  return (
    <div className="card-hero p-6 flex flex-col h-full">
      <div className="flex items-start justify-between mb-5 gap-3">
        <div>
          <div className="eyebrow">Warden Core</div>
          <div className="text-[19px] font-semibold tracking-tight text-[color:var(--text)] mt-0.5">
            Deterministic authorization
          </div>
          <div className="text-[11.5px] text-[color:var(--text-3)] mt-1">
            Financial decisions are deterministic. No LLM in this path.
          </div>
        </div>
        <Pill tone="info">No LLM authorization</Pill>
      </div>

      {mandate ? (
        <div className="card-inset p-3 mb-4">
          <div className="flex items-center justify-between gap-3 mb-2">
            <div className="flex items-center gap-2">
              <span className="eyebrow">Mandate</span>
              <span className="mono text-[11.5px] text-[color:var(--text-2)]">
                {mandate.id}
              </span>
            </div>
            <Pill tone={mandate.status === "ACTIVE" ? "ok" : mandate.status === "EXHAUSTED" || mandate.status === "REVOKED" || mandate.status === "EXPIRED" ? "bad" : "warn"}>
              {mandate.status}
            </Pill>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            <KV k="Customer" v={mandate.customer_id} mono />
            <KV k="Merchant" v="Priya's Coffee" />
            <KV
              k="Spend limit"
              v={`${formatRupees(mandate.current_period_spend)} / ${formatRupees(mandate.max_amount)}`}
            />
            <KV
              k="Frequency"
              v={`${mandate.current_period_transactions} / ${mandate.transaction_limit} txns`}
            />
          </div>
        </div>
      ) : null}

      {rows.length ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
          {rows.map((r) => (
            <CheckLine key={r.label} {...r} animated />
          ))}
        </div>
      ) : (
        <div className="text-[12.5px] text-[color:var(--text-3)] mb-5">
          {env?.action
            ? "Warden's checks will appear here once the WARDEN_EVALUATED event is written."
            : "No decision yet. Run a scenario to watch Warden's checks."}
        </div>
      )}

      {decision ? (
        <div className="mt-5">
          <DecisionBadge
            result={decision.result}
            reason={decision.reason_code}
            detail={decision.explanation}
          />
          {why.length ? (
            <div className="mt-4">
              <div className="eyebrow mb-2">
                {decision.result === "BLOCK"
                  ? "Why this was blocked"
                  : decision.result === "STEP_UP"
                    ? "Why review is required"
                    : "Why this was allowed"}
              </div>
              <ul className="flex flex-col gap-1.5">
                {why.map((w, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-[12.5px] text-[color:var(--text-2)] leading-snug"
                  >
                    <span
                      className={
                        w.tone === "ok"
                          ? "text-[color:var(--ok)] font-bold"
                          : w.tone === "warn"
                            ? "text-[color:var(--warn)] font-bold"
                            : "text-[color:var(--bad)] font-bold"
                      }
                    >
                      {w.glyph}
                    </span>
                    <span>{w.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-4 flex items-center gap-4 flex-wrap">
            {env?.action ? (
              <>
                <span className="text-[11.5px] text-[color:var(--text-3)]">
                  Amount{" "}
                  <span className="text-[color:var(--text)] font-medium mono">
                    {formatRupees(env.action.amount)}
                  </span>
                </span>
                {mandate ? (
                  <span className="text-[11.5px] text-[color:var(--text-3)]">
                    Limit{" "}
                    <span className="text-[color:var(--text)] font-medium mono">
                      {formatRupees(mandate.max_amount)}
                    </span>
                  </span>
                ) : null}
                <span className="text-[11.5px] text-[color:var(--text-3)]">
                  Razorpay{" "}
                  <span
                    className={
                      rzp.tone === "ok"
                        ? "text-[color:var(--ok)] font-medium"
                        : rzp.tone === "warn"
                          ? "text-[color:var(--warn)] font-medium"
                          : rzp.tone === "bad"
                            ? "text-[color:var(--bad)] font-medium"
                            : "text-[color:var(--text-2)] font-medium"
                    }
                  >
                    {rzp.label}
                  </span>
                </span>
              </>
            ) : null}
          </div>
        </div>
      ) : (
        <WardenEmptyState />
      )}
      <div className="mt-auto pt-4">
        <TrustNote>
          AI proposes. Warden authorizes. Every decision is deterministic and
          auditable.
        </TrustNote>
      </div>
    </div>
  );
}

function WardenEmptyState() {
  return (
    <div className="mt-6 rounded-lg border border-dashed border-[color:var(--border-strong)] px-6 py-10 text-center">
      <div className="mx-auto inline-flex items-center gap-2 text-[color:var(--text-3)] mb-3">
        <span className="inline-block w-2 h-2 rounded-full bg-[color:var(--text-4)]" />
        <span className="text-[11px] uppercase tracking-widest font-semibold">
          Warden is ready
        </span>
      </div>
      <div className="text-[16px] font-semibold text-[color:var(--text)]">
        Awaiting an AI purchase proposal
      </div>
      <p className="text-[12.5px] text-[color:var(--text-3)] mt-2 max-w-[380px] mx-auto">
        Run a scenario to watch an AI purchase move through deterministic
        authorization — mandate, spend limits, category, velocity, price drift,
        and idempotency.
      </p>
      <div className="mt-4 flex items-center justify-center gap-2 text-[11px] text-[color:var(--text-4)]">
        <span>AI Buyer</span>
        <span>→</span>
        <span>Warden</span>
        <span>→</span>
        <span>Razorpay</span>
        <span>→</span>
        <span>Audit</span>
      </div>
    </div>
  );
}
