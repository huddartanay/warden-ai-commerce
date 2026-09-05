import type { ScenarioEnvelope } from "@/lib/types";

type StageState = "idle" | "active" | "ok" | "warn" | "bad" | "skipped";

interface Stage {
  label: string;
  helper: string;
  state: StageState;
}

function statesForEnvelope(env: ScenarioEnvelope | null): Stage[] {
  if (!env?.action) {
    return [
      { label: "AI Buyer", helper: "Proposes cart", state: "idle" },
      { label: "Warden", helper: "Authorizes", state: "idle" },
      { label: "Razorpay", helper: "Executes payment", state: "idle" },
      { label: "Audit", helper: "Records event", state: "idle" },
    ];
  }
  const decision = env.decision?.result;
  const razorpayCalled = (env.razorpay_refs?.length ?? 0) > 0;
  const status = env.action.status;
  const auditWritten = (env.audit?.length ?? 0) > 0;

  const buyer: StageState = env.agent ? "ok" : "skipped";

  let warden: StageState = "idle";
  if (decision === "ALLOW") warden = "ok";
  else if (decision === "STEP_UP") warden = "warn";
  else if (decision === "BLOCK") warden = "bad";

  let razorpay: StageState = "idle";
  if (decision === "BLOCK") razorpay = "skipped";
  else if (razorpayCalled) {
    if (status === "PAYMENT_FAILED" || status === "PENDING_UNRESOLVED")
      razorpay = "warn";
    else razorpay = "ok";
  } else if (decision === "STEP_UP") razorpay = "skipped";

  const audit: StageState = auditWritten ? "ok" : "idle";

  const razorpayHelper =
    decision === "BLOCK"
      ? "Not called — Warden blocked"
      : razorpayCalled
        ? status === "PENDING_UNRESOLVED"
          ? "Capture uncertain — pending"
          : status === "PAYMENT_FAILED"
          ? "Capture failed"
          : "Test order created"
        : decision === "STEP_UP"
          ? "Waiting for human"
          : "Executes payment";

  return [
    {
      label: "AI Buyer",
      helper: env.agent ? "Cart proposed" : "Direct proposal",
      state: buyer,
    },
    {
      label: "Warden",
      helper:
        decision === "ALLOW"
          ? "All checks passed"
          : decision === "STEP_UP"
            ? "Human approval needed"
            : decision === "BLOCK"
              ? env.decision?.reason_code ?? "Blocked"
              : "Evaluating",
      state: warden,
    },
    {
      label: "Razorpay",
      helper: razorpayHelper,
      state: razorpay,
    },
    {
      label: "Audit",
      helper: auditWritten ? "Chain updated" : "Records event",
      state: audit,
    },
  ];
}

function StageBadge({ state }: { state: StageState }) {
  if (state === "ok")
    return (
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--ok-soft)] text-[color:var(--ok)] border border-[color:var(--ok-border)] text-[11px] font-bold">
        ✓
      </span>
    );
  if (state === "bad")
    return (
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--bad-soft)] text-[color:var(--bad)] border border-[color:var(--bad-border)] text-[11px] font-bold">
        ✕
      </span>
    );
  if (state === "warn")
    return (
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--warn-soft)] text-[color:var(--warn)] border border-[color:var(--warn-border)] text-[11px] font-bold">
        !
      </span>
    );
  if (state === "skipped")
    return (
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--neutral-soft)] text-[color:var(--text-3)] border border-[color:var(--border)] text-[11px] font-bold">
        —
      </span>
    );
  return (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-white text-[color:var(--text-4)] border border-[color:var(--border)] text-[11px] font-bold">
      ○
    </span>
  );
}

export function FlowIndicator({ env }: { env: ScenarioEnvelope | null }) {
  const stages = statesForEnvelope(env);
  return (
    <div className="card p-3.5">
      <div className="flex items-center gap-2 mb-2">
        <span className="eyebrow">Transaction flow</span>
        {env?.scenario ? (
          <span className="text-[11px] text-[color:var(--text-3)]">
            · scenario: <span className="mono">{env.scenario}</span>
          </span>
        ) : null}
      </div>
      <div className="flex items-stretch gap-2 overflow-x-auto scroll-slim">
        {stages.map((s, i) => (
          <div key={s.label} className="flex items-stretch gap-2 flex-1 min-w-[150px]">
            <div className="flex flex-col gap-1 flex-1">
              <div className="flex items-center gap-2">
                <StageBadge state={s.state} />
                <span className="text-[13px] font-semibold text-[color:var(--text)]">
                  {s.label}
                </span>
              </div>
              <span className="text-[11px] text-[color:var(--text-3)] pl-8 leading-snug">
                {s.helper}
              </span>
            </div>
            {i < stages.length - 1 ? (
              <span
                className="text-[color:var(--text-4)] self-center hidden sm:inline"
                aria-hidden
              >
                →
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
