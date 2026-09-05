import type { ReactNode } from "react";
import type { DecisionResult, ActionStatus } from "@/lib/types";

// ---- Status pill ---------------------------------------------------------

export type Tone = "ok" | "warn" | "bad" | "neutral" | "info";

const toneClass: Record<Tone, string> = {
  ok: "bg-[var(--ok-soft)] text-[color:var(--ok)] border-[color:var(--ok)]/30",
  warn: "bg-[var(--warn-soft)] text-[color:var(--warn)] border-[color:var(--warn)]/30",
  bad: "bg-[var(--bad-soft)] text-[color:var(--bad)] border-[color:var(--bad)]/30",
  neutral: "bg-[color:var(--surface-2)] text-[color:var(--text-2)] border-[color:var(--border)]",
  info: "bg-[color:var(--accent)]/10 text-[color:var(--accent)] border-[color:var(--accent)]/30",
};

export function Pill({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${toneClass[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

// ---- Check line ----------------------------------------------------------

export function CheckLine({
  label,
  value,
  tone = "ok",
  detail,
}: {
  label: string;
  value: string;
  tone?: Tone;
  detail?: string;
}) {
  const glyph =
    tone === "ok" ? "✓" : tone === "warn" ? "!" : tone === "bad" ? "✕" : "•";
  const glyphColor =
    tone === "ok"
      ? "text-[color:var(--ok)]"
      : tone === "warn"
        ? "text-[color:var(--warn)]"
        : tone === "bad"
          ? "text-[color:var(--bad)]"
          : "text-[color:var(--text-3)]";
  return (
    <div className="flex items-start justify-between gap-3 py-2">
      <div className="flex items-start gap-2 min-w-0">
        <span className={`mt-0.5 text-sm font-bold ${glyphColor}`}>{glyph}</span>
        <div className="min-w-0">
          <div className="section-label">{label}</div>
          {detail ? (
            <div className="text-[11px] text-[color:var(--text-3)] mt-0.5 leading-snug">
              {detail}
            </div>
          ) : null}
        </div>
      </div>
      <div className="text-sm text-[color:var(--text)] font-medium tabular-nums text-right">
        {value}
      </div>
    </div>
  );
}

// ---- Decision badge ------------------------------------------------------

export function DecisionBadge({
  result,
  reason,
  className = "",
}: {
  result: DecisionResult;
  reason?: string;
  className?: string;
}) {
  const conf =
    result === "ALLOW"
      ? {
          bg: "bg-[var(--ok-soft)] text-[color:var(--ok)] border-[color:var(--ok)]/40",
          icon: "●",
          label: "ALLOW",
        }
      : result === "STEP_UP"
        ? {
            bg: "bg-[var(--warn-soft)] text-[color:var(--warn)] border-[color:var(--warn)]/40",
            icon: "●",
            label: "STEP-UP",
          }
        : {
            bg: "bg-[var(--bad-soft)] text-[color:var(--bad)] border-[color:var(--bad)]/40",
            icon: "●",
            label: "BLOCK",
          };
  return (
    <div
      className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${conf.bg} ${className}`}
    >
      <span className="text-2xl leading-none">{conf.icon}</span>
      <div className="flex flex-col leading-tight">
        <span className="text-[10px] uppercase tracking-widest opacity-70">
          Decision
        </span>
        <span className="text-2xl font-semibold tracking-tight">
          {conf.label}
        </span>
      </div>
      {reason ? (
        <span className="ml-auto mono text-[11px] tracking-tight opacity-80">
          {reason}
        </span>
      ) : null}
    </div>
  );
}

// ---- Action status pill --------------------------------------------------

const actionStatusTone: Record<ActionStatus, Tone> = {
  PROPOSED: "neutral",
  ALLOWED: "ok",
  BLOCKED: "bad",
  STEP_UP_PENDING: "warn",
  STEP_UP_APPROVED: "ok",
  STEP_UP_REJECTED: "bad",
  PAYMENT_INITIATED: "info",
  PAYMENT_COMPLETED: "ok",
  PAYMENT_FAILED: "bad",
  PENDING_UNRESOLVED: "warn",
  REFUNDED: "neutral",
};

export function ActionStatusPill({ status }: { status: ActionStatus }) {
  return <Pill tone={actionStatusTone[status]}>{status.replace(/_/g, " ")}</Pill>;
}

// ---- Section container ---------------------------------------------------

export function Section({
  title,
  right,
  children,
  className = "",
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`card p-4 flex flex-col ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="section-label">{title}</span>
        {right ? <div>{right}</div> : null}
      </div>
      {children}
    </div>
  );
}

// ---- Muted key/value row --------------------------------------------------

export function KV({
  k,
  v,
  mono = false,
}: {
  k: string;
  v: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-[11px] uppercase tracking-widest text-[color:var(--text-3)]">
        {k}
      </span>
      <span
        className={`text-sm text-[color:var(--text)] text-right truncate ${
          mono ? "mono text-[12px]" : ""
        }`}
      >
        {v}
      </span>
    </div>
  );
}
