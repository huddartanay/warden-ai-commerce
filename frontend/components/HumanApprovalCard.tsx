"use client";

import { useState } from "react";
import { approveAction, formatRupees, resolveAction } from "@/lib/api";
import type { ScenarioEnvelope } from "@/lib/types";
import { Pill } from "./atoms";

type Mode = "step_up" | "pending_unresolved" | null;

function detectMode(env: ScenarioEnvelope | null): Mode {
  if (!env?.action) return null;
  if (env.action.status === "STEP_UP_PENDING") return "step_up";
  if (env.action.status === "PENDING_UNRESOLVED") return "pending_unresolved";
  return null;
}

export function HumanApprovalCard({
  env,
  onDone,
}: {
  env: ScenarioEnvelope | null;
  onDone: () => void;
}) {
  const mode = detectMode(env);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (!mode || !env?.action) return null;

  const amount = formatRupees(env.action.amount);
  const description =
    env.cart?.items?.length === 1
      ? env.cart.items[0].name
      : env.cart?.items?.length
        ? `Cart of ${env.cart.items.length} items`
        : "AI purchase";

  const call = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setErr(null);
    try {
      await fn();
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (mode === "step_up") {
    return (
      <div className="card-hero border-[color:var(--warn-border)] p-5 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="eyebrow text-[color:var(--warn)]">
              Review required
            </div>
            <div className="text-[16px] font-semibold text-[color:var(--text)] mt-1">
              AI buyer requested a purchase
            </div>
            <div className="mt-3 flex items-center gap-4 flex-wrap">
              <div>
                <div className="eyebrow">Description</div>
                <div className="text-[13.5px] mt-0.5">{description}</div>
              </div>
              <div>
                <div className="eyebrow">Amount</div>
                <div className="text-[16px] font-semibold tabular-nums mt-0.5">
                  {amount}
                </div>
              </div>
              <div>
                <div className="eyebrow">Reason</div>
                <div className="mono text-[12px] mt-0.5 text-[color:var(--text-2)]">
                  {env.decision?.reason_code ?? "APPROVAL_REQUIRED"}
                </div>
              </div>
            </div>
          </div>
          <Pill tone="warn">STEP-UP</Pill>
        </div>
        {env.decision?.explanation ? (
          <p className="text-[12.5px] text-[color:var(--text-3)] leading-snug">
            {env.decision.explanation}
          </p>
        ) : null}
        {err ? (
          <p className="text-[11px] text-[color:var(--bad)] mono">{err}</p>
        ) : null}
        <div className="flex items-center gap-2">
          <button
            disabled={busy !== null}
            onClick={() => call("approve", () => approveAction(env.action!.id))}
            className="flex-1 rounded-md px-4 py-2.5 text-[13px] font-semibold bg-[color:var(--ok)] text-white hover:brightness-110 disabled:opacity-50"
          >
            {busy === "approve" ? "Approving…" : "Approve purchase"}
          </button>
          <button
            disabled={busy !== null}
            onClick={() =>
              call("block", () =>
                resolveAction(env.action!.id, {
                  note: "Human rejected the step-up",
                  resolved_by: "judge",
                }),
              )
            }
            className="rounded-md px-4 py-2.5 text-[13px] font-semibold border border-[color:var(--bad-border)] text-[color:var(--bad)] bg-white hover:bg-[color:var(--bad-soft)] disabled:opacity-50"
          >
            {busy === "block" ? "Rejecting…" : "Block"}
          </button>
        </div>
      </div>
    );
  }

  // PENDING_UNRESOLVED
  return (
    <div className="card-hero border-[color:var(--warn-border)] p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="eyebrow text-[color:var(--warn)]">
            Pending human review
          </div>
          <div className="text-[16px] font-semibold text-[color:var(--text)] mt-1">
            {amount} payment had an uncertain outcome
          </div>
          <p className="text-[12.5px] text-[color:var(--text-3)] leading-snug mt-2 max-w-xl">
            Warden preserved the mandate reservation because it doesn't know
            whether the charge went through on Razorpay. Reconcile from what
            the Razorpay dashboard shows.
          </p>
        </div>
        <Pill tone="warn">PENDING_UNRESOLVED</Pill>
      </div>
      {err ? (
        <p className="text-[11px] text-[color:var(--bad)] mono">{err}</p>
      ) : null}
      <div className="grid grid-cols-2 gap-2">
        <button
          disabled={busy !== null}
          onClick={() =>
            call("failed", () =>
              resolveAction(env.action!.id, {
                new_action_status: "PAYMENT_FAILED",
                note: "Confirmed no capture. Rolling back.",
                resolved_by: "judge",
              }),
            )
          }
          className="rounded-md px-4 py-2.5 text-[13px] font-semibold border border-[color:var(--bad-border)] text-[color:var(--bad)] bg-white hover:bg-[color:var(--bad-soft)] disabled:opacity-50"
        >
          {busy === "failed" ? "Resolving…" : "Mark FAILED (rollback)"}
        </button>
        <button
          disabled={busy !== null}
          onClick={() =>
            call("completed", () =>
              resolveAction(env.action!.id, {
                new_action_status: "PAYMENT_COMPLETED",
                note: "Confirmed capture on Razorpay dashboard.",
                resolved_by: "judge",
              }),
            )
          }
          className="rounded-md px-4 py-2.5 text-[13px] font-semibold bg-[color:var(--ok)] text-white hover:brightness-110 disabled:opacity-50"
        >
          {busy === "completed" ? "Resolving…" : "Mark COMPLETED"}
        </button>
      </div>
    </div>
  );
}
