import type { ReactNode } from "react";
import type { DecisionResult, ActionStatus } from "@/lib/types";

// ---- Status pill ---------------------------------------------------------

export type Tone = "ok" | "warn" | "bad" | "neutral" | "info";

const toneClass: Record<Tone, string> = {
  ok: "bg-[color:var(--ok-soft)] text-[color:var(--ok)] border-[color:var(--ok-border)]",
  warn: "bg-[color:var(--warn-soft)] text-[color:var(--warn)] border-[color:var(--warn-border)]",
  bad: "bg-[color:var(--bad-soft)] text-[color:var(--bad)] border-[color:var(--bad-border)]",
  neutral:
    "bg-[color:var(--neutral-soft)] text-[color:var(--text-2)] border-[color:var(--border)]",
  info: "bg-[color:var(--brand-blue-soft)] text-[color:var(--brand-blue)] border-[color:var(--brand-blue)]/25",
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
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-medium uppercase tracking-wide ${toneClass[tone]} ${className}`}
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
  animated = false,
}: {
  label: string;
  value: string;
  tone?: Tone;
  detail?: string;
  animated?: boolean;
}) {
  const dot =
    tone === "ok"
      ? "bg-[color:var(--ok)]"
      : tone === "warn"
        ? "bg-[color:var(--warn)]"
        : tone === "bad"
          ? "bg-[color:var(--bad)]"
          : "bg-[color:var(--text-4)]";
  const glyph =
    tone === "ok" ? "✓" : tone === "warn" ? "!" : tone === "bad" ? "✕" : "•";
  const glyphColor =
    tone === "ok"
      ? "text-[color:var(--ok)]"
      : tone === "warn"
        ? "text-[color:var(--warn)]"
        : tone === "bad"
          ? "text-[color:var(--bad)]"
          : "text-[color:var(--text-4)]";
  return (
    <div
      className={`flex items-start justify-between gap-3 py-2 ${
        animated ? "check-appear" : ""
      }`}
    >
      <div className="flex items-start gap-2 min-w-0">
        <span
          className={`mt-1 inline-flex items-center justify-center w-4 h-4 rounded-full ${dot} bg-opacity-15`}
        >
          <span className={`text-[10px] font-bold ${glyphColor}`}>{glyph}</span>
        </span>
        <div className="min-w-0">
          <div className="text-[12.5px] text-[color:var(--text)] font-medium">
            {label}
          </div>
          {detail ? (
            <div className="text-[11px] text-[color:var(--text-3)] mt-0.5 leading-snug">
              {detail}
            </div>
          ) : null}
        </div>
      </div>
      <div className="text-[12.5px] text-[color:var(--text)] font-medium tabular-nums text-right whitespace-nowrap">
        {value}
      </div>
    </div>
  );
}

// ---- Decision badge ------------------------------------------------------

export function DecisionBadge({
  result,
  reason,
  detail,
  className = "",
}: {
  result: DecisionResult;
  reason?: string;
  detail?: string;
  className?: string;
}) {
  const conf =
    result === "ALLOW"
      ? {
          border: "border-[color:var(--ok-border)]",
          bg: "bg-[color:var(--ok-soft)]",
          text: "text-[color:var(--ok)]",
          label: "ALLOWED",
          icon: "✓",
        }
      : result === "STEP_UP"
        ? {
            border: "border-[color:var(--warn-border)]",
            bg: "bg-[color:var(--warn-soft)]",
            text: "text-[color:var(--warn)]",
            label: "STEP-UP",
            icon: "!",
          }
        : {
            border: "border-[color:var(--bad-border)]",
            bg: "bg-[color:var(--bad-soft)]",
            text: "text-[color:var(--bad)]",
            label: "BLOCKED",
            icon: "✕",
          };
  return (
    <div
      className={`rounded-lg border ${conf.border} ${conf.bg} px-4 py-4 ${className}`}
    >
      <div className="flex items-center gap-3">
        <span
          className={`inline-flex items-center justify-center w-9 h-9 rounded-full ${conf.text} bg-white border ${conf.border} text-lg font-bold`}
        >
          {conf.icon}
        </span>
        <div className="flex flex-col leading-tight">
          <span className={`eyebrow ${conf.text} opacity-90`}>Decision</span>
          <span
            className={`text-2xl font-semibold tracking-tight ${conf.text}`}
          >
            {conf.label}
          </span>
        </div>
        {reason ? (
          <span className={`ml-auto mono text-[11px] ${conf.text} opacity-80`}>
            {reason}
          </span>
        ) : null}
      </div>
      {detail ? (
        <p className="text-[12.5px] text-[color:var(--text-2)] mt-3 leading-snug">
          {detail}
        </p>
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
  return (
    <Pill tone={actionStatusTone[status]}>{status.replace(/_/g, " ")}</Pill>
  );
}

// ---- Section container ---------------------------------------------------

export function Section({
  title,
  eyebrow,
  right,
  children,
  className = "",
  hero = false,
}: {
  title?: string;
  eyebrow?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  hero?: boolean;
}) {
  return (
    <div className={`${hero ? "card-hero" : "card"} p-5 flex flex-col ${className}`}>
      {(title || eyebrow || right) && (
        <div className="flex items-start justify-between mb-4 gap-3">
          <div className="min-w-0">
            {eyebrow ? <div className="eyebrow mb-1">{eyebrow}</div> : null}
            {title ? <div className="section-title">{title}</div> : null}
          </div>
          {right ? <div className="shrink-0">{right}</div> : null}
        </div>
      )}
      {children}
    </div>
  );
}

// ---- Key/value row --------------------------------------------------

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
      <span className="eyebrow">{k}</span>
      <span
        className={`text-[13px] text-[color:var(--text)] text-right truncate ${
          mono ? "mono text-[12px]" : ""
        }`}
      >
        {v}
      </span>
    </div>
  );
}

// ---- Metric card --------------------------------------------------

export function Metric({
  label,
  value,
  helper,
  tone = "neutral",
  className = "",
}: {
  label: string;
  value: ReactNode;
  helper?: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  const accent =
    tone === "ok"
      ? "text-[color:var(--ok)]"
      : tone === "warn"
        ? "text-[color:var(--warn)]"
        : tone === "bad"
          ? "text-[color:var(--bad)]"
          : "text-[color:var(--text)]";
  return (
    <div className={`card p-4 flex flex-col gap-1.5 ${className}`}>
      <span className="eyebrow">{label}</span>
      <span
        className={`text-[22px] font-semibold tracking-tight tabular-nums ${accent}`}
      >
        {value}
      </span>
      {helper ? (
        <span className="text-[11px] text-[color:var(--text-3)]">{helper}</span>
      ) : null}
    </div>
  );
}

// ---- Trust signal --------------------------------------------------------

export function TrustNote({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] text-[color:var(--text-3)] flex items-center gap-1.5 leading-snug">
      <span className="inline-block w-1 h-1 rounded-full bg-[color:var(--text-4)]" />
      {children}
    </p>
  );
}
