"use client";

import Link from "next/link";
import type { AuditEntry, ScenarioEnvelope } from "@/lib/types";
import { formatTimestamp, shortHash } from "@/lib/api";
import { Pill, Section, Tone, TrustNote } from "./atoms";

const eventTone: Record<string, Tone> = {
  MANDATE_CREATED: "neutral",
  MANDATE_REVOKED: "bad",
  INTENT_RECEIVED: "neutral",
  CART_CREATED: "neutral",
  WARDEN_EVALUATED: "info",
  BLOCKED: "bad",
  STEP_UP_REQUESTED: "warn",
  DUPLICATE_DETECTED: "warn",
  HUMAN_APPROVED: "ok",
  PAYMENT_CREATED: "info",
  PAYMENT_LINK_CREATED: "info",
  PAYMENT_LINK_FAILED: "bad",
  PAYMENT_COMPLETED: "ok",
  PAYMENT_FAILED: "bad",
  PAYMENT_PENDING_UNRESOLVED: "warn",
  REFUND_REQUESTED: "info",
  REFUND_COMPLETED: "ok",
  RESOLUTION_APPLIED: "ok",
  AGENT_AUTH_FAILED: "bad",
  SYSTEM_ERROR: "bad",
};

const eventShortLabel: Record<string, string> = {
  MANDATE_CREATED: "Mandate created",
  MANDATE_REVOKED: "Mandate revoked",
  INTENT_RECEIVED: "Intent received",
  CART_CREATED: "Cart created",
  WARDEN_EVALUATED: "Warden evaluated",
  BLOCKED: "Decision: BLOCK",
  STEP_UP_REQUESTED: "Decision: STEP-UP",
  DUPLICATE_DETECTED: "Duplicate detected",
  HUMAN_APPROVED: "Human approved",
  PAYMENT_CREATED: "Razorpay order created",
  PAYMENT_LINK_CREATED: "Payment link created",
  PAYMENT_LINK_FAILED: "Payment link failed",
  PAYMENT_COMPLETED: "Payment completed",
  PAYMENT_FAILED: "Payment failed",
  PAYMENT_PENDING_UNRESOLVED: "Payment unresolved",
  REFUND_REQUESTED: "Refund requested",
  REFUND_COMPLETED: "Refund completed",
  RESOLUTION_APPLIED: "Resolution applied",
  AGENT_AUTH_FAILED: "Agent auth failed",
  SYSTEM_ERROR: "System error",
};

function AuditRow({
  entry,
  isLast,
  scenarioActionId,
}: {
  entry: AuditEntry;
  isLast: boolean;
  scenarioActionId?: string | null;
}) {
  const tone = eventTone[entry.event_type] ?? "neutral";
  const dot =
    tone === "ok"
      ? "bg-[color:var(--ok)]"
      : tone === "bad"
        ? "bg-[color:var(--bad)]"
        : tone === "warn"
          ? "bg-[color:var(--warn)]"
          : tone === "info"
            ? "bg-[color:var(--brand-blue)]"
            : "bg-[color:var(--text-4)]";
  const highlight = scenarioActionId && entry.action_id === scenarioActionId;
  const shortLabel = eventShortLabel[entry.event_type] ?? entry.event_type;
  const body = (
    <div
      className={`flex items-start gap-3 py-2 ${
        highlight ? "" : "opacity-90"
      }`}
    >
      <div className="flex flex-col items-center pt-1 shrink-0">
        <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
        {isLast ? null : (
          <span
            className="w-px flex-1 bg-[color:var(--border)] mt-1"
            style={{ minHeight: 18 }}
          />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[12.5px] font-medium text-[color:var(--text)]">
            {shortLabel}
          </span>
          <span className="mono text-[10.5px] text-[color:var(--text-3)]">
            #{entry.seq} · {formatTimestamp(entry.timestamp)}
          </span>
        </div>
        <div className="mono text-[10px] text-[color:var(--text-3)] mt-0.5 truncate">
          {shortHash(entry.previous_hash, 8)} → {shortHash(entry.current_hash, 8)}
        </div>
      </div>
    </div>
  );
  if (entry.action_id) {
    return (
      <Link
        href={`/transaction/${entry.action_id}`}
        className="block hover:bg-[color:var(--surface-2)] -mx-2 px-2 rounded transition-colors"
      >
        {body}
      </Link>
    );
  }
  return body;
}

export function AuditPanel({
  env,
  auditEntries,
  chainValid,
  entriesChecked,
  onVerify,
  verifying,
}: {
  env: ScenarioEnvelope | null;
  auditEntries: AuditEntry[];
  chainValid: boolean | null;
  entriesChecked: number | null;
  onVerify: () => void;
  verifying: boolean;
}) {
  const entries = auditEntries.length ? auditEntries : env?.audit ?? [];
  return (
    <Section
      eyebrow="Audit trail"
      title="Every decision is recorded"
      right={
        chainValid === null ? null : (
          <Pill tone={chainValid ? "ok" : "bad"}>
            {chainValid ? "✓ Chain verified" : "✕ Chain broken"}
          </Pill>
        )
      }
      className="h-full min-h-0"
    >
      <div className="flex-1 overflow-y-auto scroll-slim -mx-1 px-1 min-h-0">
        {entries.length === 0 ? (
          <EmptyAudit />
        ) : (
          entries.map((e, i) => (
            <AuditRow
              key={e.seq}
              entry={e}
              isLast={i === entries.length - 1}
              scenarioActionId={env?.action?.id}
            />
          ))
        )}
      </div>

      <div className="mt-3 pt-3 hairline flex items-center justify-between gap-2">
        <div className="text-[11px] text-[color:var(--text-3)]">
          {entriesChecked !== null && chainValid !== null
            ? chainValid
              ? `✓ ${entriesChecked} entries verified`
              : `✕ ${entriesChecked} entries checked · tamper detected`
            : "Hash-chained. Click Verify to re-hash the log."}
        </div>
        <button
          onClick={onVerify}
          disabled={verifying}
          className="text-[11.5px] px-2.5 py-1 rounded-md border border-[color:var(--border-strong)] bg-white hover:bg-[color:var(--surface-2)] disabled:opacity-50 font-medium"
        >
          {verifying ? "Verifying…" : "Verify chain"}
        </button>
      </div>
      <div className="pt-3">
        <TrustNote>Each row is hash-chained. Click to view the transaction.</TrustNote>
      </div>
    </Section>
  );
}

function EmptyAudit() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center gap-2 py-4">
      <div className="inline-flex items-center gap-1.5 text-[color:var(--text-4)]">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-[color:var(--text-4)]" />
        <span className="w-8 h-px bg-[color:var(--border)]" />
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-[color:var(--text-4)]" />
        <span className="w-8 h-px bg-[color:var(--border)]" />
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-[color:var(--text-4)]" />
      </div>
      <div className="text-[13px] font-medium text-[color:var(--text-2)]">
        No events yet
      </div>
      <div className="text-[11.5px] text-[color:var(--text-3)] max-w-[220px]">
        Run a scenario to fill the audit trail — every row is hash-chained and
        clickable.
      </div>
    </div>
  );
}
