"use client";

import Link from "next/link";
import { use, useCallback } from "react";
import {
  approveAction,
  fetchAction,
  fetchAuditForAction,
  formatRupees,
  formatTimestamp,
  resolveAction,
  shortHash,
} from "@/lib/api";
import type {
  ActionDetail,
  AuditListResponse,
} from "@/lib/types";
import { usePolling } from "@/lib/polling";
import {
  ActionStatusPill,
  DecisionBadge,
  KV,
  Pill,
  Section,
} from "@/components/atoms";

type Params = { actionId: string };

export default function TransactionDetailPage(
  props: { params: Promise<Params> },
) {
  const { actionId } = use(props.params);
  const {
    data: detail,
    error: detailError,
    refresh: refreshDetail,
  } = usePolling<ActionDetail>(
    () => fetchAction(actionId),
    3000,
    [actionId],
  );
  const {
    data: audit,
    error: auditError,
    refresh: refreshAudit,
  } = usePolling<AuditListResponse>(
    () => fetchAuditForAction(actionId),
    3000,
    [actionId],
  );

  const refresh = useCallback(() => {
    refreshDetail();
    refreshAudit();
  }, [refreshDetail, refreshAudit]);

  const approve = async () => {
    await approveAction(actionId).catch(() => undefined);
    refresh();
  };
  const resolvePayFailed = async () => {
    await resolveAction(actionId, {
      new_action_status: "PAYMENT_FAILED",
      resolved_by: "judge",
      note: "Confirmed via Razorpay: no capture. Rolling back.",
    }).catch(() => undefined);
    refresh();
  };
  const resolvePayCompleted = async () => {
    await resolveAction(actionId, {
      new_action_status: "PAYMENT_COMPLETED",
      resolved_by: "judge",
      note: "Confirmed via Razorpay: charge succeeded.",
    }).catch(() => undefined);
    refresh();
  };

  if (detailError && !detail) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <Link
          href="/"
          className="text-[12px] text-[color:var(--text-3)] hover:underline"
        >
          ← Dashboard
        </Link>
        <div className="card p-4 mt-4">
          <div className="section-label">Transaction not found</div>
          <p className="text-sm text-[color:var(--text-2)] mt-2">
            {detailError.message}
          </p>
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="max-w-3xl mx-auto p-6 text-[color:var(--text-3)] text-sm">
        Loading transaction {actionId}…
      </div>
    );
  }

  const { action, decision, razorpay_refs } = detail;
  const entries = audit?.entries ?? [];

  const showApprove = action.status === "STEP_UP_PENDING";
  const showReconcile = action.status === "PENDING_UNRESOLVED";

  return (
    <div className="min-h-screen mx-auto max-w-[1200px] px-4 py-4 flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="text-[12px] text-[color:var(--text-3)] hover:underline"
          >
            ← Dashboard
          </Link>
          <div>
            <div className="section-label">Transaction</div>
            <div className="mono text-[13px]">{action.id}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ActionStatusPill status={action.status} />
          {audit ? <Pill tone="neutral">{audit.count} audit entries</Pill> : null}
        </div>
      </div>

      {decision ? (
        <DecisionBadge result={decision.result} reason={decision.reason_code} />
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Section title="Action" className="lg:col-span-1">
          <KV k="ID" v={action.id} mono />
          <KV k="Mandate" v={action.mandate_id} mono />
          <KV k="Cart" v={action.cart_id ?? "—"} mono />
          <KV k="Amount" v={formatRupees(action.amount)} />
          <KV k="Currency" v={action.currency} />
          <KV k="Idempotency key" v={action.idempotency_key} mono />
          <KV k="Created" v={formatTimestamp(action.created_at)} />
          <KV k="Updated" v={formatTimestamp(action.updated_at)} />
        </Section>

        <Section title="Warden decision" className="lg:col-span-2">
          {decision ? (
            <>
              <KV k="Result" v={decision.result} />
              <KV k="Reason" v={decision.reason_code} mono />
              <KV k="Recorded" v={formatTimestamp(decision.created_at)} />
              <p className="text-[13px] text-[color:var(--text-2)] mt-2 leading-snug">
                {decision.explanation}
              </p>
            </>
          ) : (
            <p className="text-[13px] text-[color:var(--text-3)]">
              No decision recorded for this action.
            </p>
          )}
          {(showApprove || showReconcile) && (
            <div className="mt-4 pt-3 hairline flex flex-col gap-2">
              {showApprove ? (
                <button
                  onClick={approve}
                  className="rounded px-3 py-2 text-sm font-medium bg-[color:var(--ok)] text-black hover:brightness-110"
                >
                  Approve step-up
                </button>
              ) : null}
              {showReconcile ? (
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={resolvePayFailed}
                    className="rounded px-3 py-2 text-sm bg-[color:var(--bad)]/90 text-white hover:brightness-110"
                  >
                    Mark FAILED
                  </button>
                  <button
                    onClick={resolvePayCompleted}
                    className="rounded px-3 py-2 text-sm bg-[color:var(--ok)] text-black hover:brightness-110"
                  >
                    Mark COMPLETED
                  </button>
                </div>
              ) : null}
            </div>
          )}
        </Section>

        <Section title="Razorpay refs" className="lg:col-span-3">
          {razorpay_refs.length === 0 ? (
            <p className="text-[13px] text-[color:var(--text-3)]">
              No Razorpay calls were made for this action.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {razorpay_refs.map((r) => (
                <div key={r.id} className="card p-3">
                  <div className="flex items-center justify-between mb-1">
                    <Pill tone="info">{r.ref_type}</Pill>
                    <Pill tone="neutral">{r.status ?? "unknown"}</Pill>
                  </div>
                  <div className="mono text-[11px] break-all">{r.razorpay_id}</div>
                  <div className="text-[11px] text-[color:var(--text-3)] mt-2">
                    {formatTimestamp(r.created_at)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>

        <Section title="Audit chain" className="lg:col-span-3">
          {auditError ? (
            <p className="text-[12px] text-[color:var(--bad)] mono">
              {auditError.message}
            </p>
          ) : null}
          <div className="flex flex-col divide-y divide-[color:var(--border)]">
            {entries.length === 0 ? (
              <p className="text-[13px] text-[color:var(--text-3)] py-2">
                No audit entries.
              </p>
            ) : (
              entries.map((e) => (
                <div key={e.seq} className="py-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="mono text-[11px] text-[color:var(--text-3)] tabular-nums">
                      #{e.seq}
                    </span>
                    <Pill tone="neutral">{e.event_type}</Pill>
                    <span className="mono text-[11px] text-[color:var(--text-3)]">
                      {formatTimestamp(e.timestamp)}
                    </span>
                  </div>
                  <div className="mono text-[10.5px] text-[color:var(--text-3)] mt-1">
                    prev {shortHash(e.previous_hash, 12)} → curr{" "}
                    {shortHash(e.current_hash, 12)}
                  </div>
                  <pre className="mono text-[10.5px] text-[color:var(--text-2)] mt-2 overflow-x-auto scroll-slim bg-[color:var(--surface-2)] border border-[color:var(--border)] rounded p-2">
                    {JSON.stringify(e.event_data, null, 2)}
                  </pre>
                </div>
              ))
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}
