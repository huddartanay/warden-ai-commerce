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
      <div className="card-hero p-4 flex flex-col gap-3 border-[color:var(--warn)]/30">
        <div className="flex items-center justify-between">
          <div>
            <div className="section-label">Human approval required</div>
            <div className="text-[15px] font-medium mt-1">
              AI buyer requested {amount} purchase.
            </div>
          </div>
          <Pill tone="warn">STEP-UP</Pill>
        </div>
        <div className="text-[12px] text-[color:var(--text-2)]">
          Reason:{" "}
          <span className="mono">{env.decision?.reason_code ?? "APPROVAL_REQUIRED"}</span>
          {env.decision?.explanation ? (
            <span className="block mt-1 text-[color:var(--text-3)]">
              {env.decision.explanation}
            </span>
          ) : null}
        </div>
        {err ? <p className="text-[11px] text-[color:var(--bad)] mono">{err}</p> : null}
        <div className="flex gap-2 mt-1">
          <button
            disabled={busy !== null}
            onClick={() =>
              call("approve", () => approveAction(env.action!.id))
            }
            className="flex-1 rounded px-3 py-2 text-sm font-medium bg-[color:var(--ok)] text-black disabled:opacity-50 hover:brightness-110"
          >
            {busy === "approve" ? "approving…" : "Approve"}
          </button>
          <button
            disabled={busy !== null}
            onClick={() =>
              call("revoke", () =>
                resolveAction(env.action!.id, {
                  note: "Human rejected the step-up",
                  resolved_by: "judge",
                }),
              )
            }
            className="flex-1 rounded px-3 py-2 text-sm font-medium bg-[color:var(--bad)]/90 text-white disabled:opacity-50 hover:brightness-110"
          >
            {busy === "revoke" ? "rejecting…" : "Block"}
          </button>
        </div>
      </div>
    );
  }

  // PENDING_UNRESOLVED — human reconciles after an uncertain payment outcome.
  return (
    <div className="card-hero p-4 flex flex-col gap-3 border-[color:var(--warn)]/30">
      <div className="flex items-center justify-between">
        <div>
          <div className="section-label">Pending human review</div>
          <div className="text-[15px] font-medium mt-1">
            {amount} payment had an uncertain outcome.
          </div>
        </div>
        <Pill tone="warn">PENDING_UNRESOLVED</Pill>
      </div>
      <div className="text-[12px] text-[color:var(--text-2)]">
        Warden preserved the mandate reservation because it doesn't know
        whether the charge actually went through on Razorpay. Resolve based on
        what the Razorpay dashboard shows.
      </div>
      {err ? <p className="text-[11px] text-[color:var(--bad)] mono">{err}</p> : null}
      <div className="grid grid-cols-2 gap-2">
        <button
          disabled={busy !== null}
          onClick={() =>
            call("failed", () =>
              resolveAction(env.action!.id, {
                new_action_status: "PAYMENT_FAILED",
                note: "Confirmed no capture occurred; rolling back reservation.",
                resolved_by: "judge",
              }),
            )
          }
          className="rounded px-3 py-2 text-sm bg-[color:var(--bad)]/90 text-white disabled:opacity-50"
        >
          {busy === "failed" ? "resolving…" : "Mark FAILED (rollback)"}
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
          className="rounded px-3 py-2 text-sm bg-[color:var(--ok)] text-black disabled:opacity-50"
        >
          {busy === "completed" ? "resolving…" : "Mark COMPLETED"}
        </button>
      </div>
    </div>
  );
}
