"use client";

import Link from "next/link";
import type { AuditEntry, ScenarioEnvelope } from "@/lib/types";
import { formatTimestamp, shortHash } from "@/lib/api";
import { Pill, Section, Tone } from "./atoms";

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

function AuditRow({ entry }: { entry: AuditEntry }) {
  const tone = eventTone[entry.event_type] ?? "neutral";
  const body = (
    <div className="flex items-start gap-3 py-2.5">
      <span className="mono text-[10px] text-[color:var(--text-3)] w-8 text-right pt-0.5 tabular-nums">
        #{entry.seq}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Pill tone={tone} className="!px-1.5 !py-[1px] !text-[10px]">
            {entry.event_type}
          </Pill>
          <span className="text-[11px] text-[color:var(--text-3)] mono">
            {formatTimestamp(entry.timestamp)}
          </span>
        </div>
        <div className="mono text-[10.5px] text-[color:var(--text-3)] mt-1 truncate">
          prev {shortHash(entry.previous_hash, 8)} → curr {shortHash(entry.current_hash, 8)}
        </div>
      </div>
    </div>
  );
  if (entry.action_id) {
    return (
      <Link
        href={`/transaction/${entry.action_id}`}
        className="block hover:bg-[color:var(--surface-2)] rounded px-1 -mx-1 transition-colors"
      >
        {body}
      </Link>
    );
  }
  return body;
}

export function AuditPanel({
  env,
  chainValid,
}: {
  env: ScenarioEnvelope | null;
  chainValid: boolean | null;
}) {
  const entries = env?.audit ?? [];
  return (
    <Section
      title="Audit Trail"
      right={
        chainValid === null ? null : (
          <Pill tone={chainValid ? "ok" : "bad"}>
            chain {chainValid ? "✓ valid" : "✕ broken"}
          </Pill>
        )
      }
      className="h-full min-h-0"
    >
      <div className="flex-1 overflow-y-auto scroll-slim divide-y divide-[color:var(--border)] -mx-1 px-1">
        {entries.length === 0 ? (
          <p className="text-[13px] text-[color:var(--text-3)] py-4">
            No events yet. Run a demo scenario to fill the audit trail — every
            row is hash-chained and clickable.
          </p>
        ) : (
          entries.map((e) => <AuditRow key={e.seq} entry={e} />)
        )}
      </div>
    </Section>
  );
}
