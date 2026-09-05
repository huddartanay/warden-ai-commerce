"use client";

import { useState } from "react";
import {
  ScenarioName,
  SCENARIO_LABELS,
  SCENARIO_NAMES,
  resetDemo,
  runScenario,
  verifyAuditChain,
} from "@/lib/api";
import type { AuditVerifyResponse, ScenarioEnvelope } from "@/lib/types";

const scenarioTone: Record<ScenarioName, string> = {
  successful_purchase:
    "border-[color:var(--ok)]/40 hover:bg-[var(--ok-soft)] hover:text-[color:var(--ok)]",
  cap_exceeded:
    "border-[color:var(--bad)]/40 hover:bg-[var(--bad-soft)] hover:text-[color:var(--bad)]",
  step_up:
    "border-[color:var(--warn)]/40 hover:bg-[var(--warn-soft)] hover:text-[color:var(--warn)]",
  duplicate:
    "border-[color:var(--warn)]/40 hover:bg-[var(--warn-soft)] hover:text-[color:var(--warn)]",
  price_drift:
    "border-[color:var(--bad)]/40 hover:bg-[var(--bad-soft)] hover:text-[color:var(--bad)]",
  payment_failure:
    "border-[color:var(--warn)]/40 hover:bg-[var(--warn-soft)] hover:text-[color:var(--warn)]",
};

export function DemoControls({
  onScenario,
  onVerify,
  onReset,
  busy,
}: {
  onScenario: (env: ScenarioEnvelope) => void;
  onVerify: (v: AuditVerifyResponse) => void;
  onReset: () => void;
  busy: boolean;
}) {
  const [pending, setPending] = useState<ScenarioName | "reset" | "verify" | null>(
    null,
  );
  const [lastError, setLastError] = useState<string | null>(null);

  const run = async (name: ScenarioName) => {
    setPending(name);
    setLastError(null);
    try {
      const env = await runScenario(name);
      onScenario(env);
    } catch (e) {
      setLastError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(null);
    }
  };

  const doReset = async () => {
    setPending("reset");
    setLastError(null);
    try {
      await resetDemo();
      onReset();
    } catch (e) {
      setLastError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(null);
    }
  };

  const doVerify = async () => {
    setPending("verify");
    setLastError(null);
    try {
      const v = await verifyAuditChain();
      onVerify(v);
    } catch (e) {
      setLastError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(null);
    }
  };

  const anyPending = pending !== null || busy;

  return (
    <div className="card p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="section-label">Demo Control Panel</div>
          <div className="text-[11px] text-[color:var(--text-3)] mt-0.5">
            Each scenario runs the full stack — agent + Warden + Razorpay Test
            + audit — server-side. No fake logic in this UI.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={doVerify}
            disabled={anyPending}
            className="text-[12px] px-3 py-1.5 rounded border border-[color:var(--border-strong)] hover:bg-[color:var(--surface-2)] disabled:opacity-50"
          >
            {pending === "verify" ? "verifying…" : "Verify chain"}
          </button>
          <button
            onClick={doReset}
            disabled={anyPending}
            className="text-[12px] px-3 py-1.5 rounded border border-[color:var(--border-strong)] hover:bg-[color:var(--surface-2)] disabled:opacity-50"
          >
            {pending === "reset" ? "resetting…" : "Reset demo"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mt-1">
        {SCENARIO_NAMES.map((n) => (
          <button
            key={n}
            onClick={() => run(n)}
            disabled={anyPending}
            className={`text-[12px] font-medium tracking-tight px-3 py-2 rounded border bg-[color:var(--surface-2)] text-[color:var(--text)] ${scenarioTone[n]} disabled:opacity-50`}
          >
            {pending === n ? "running…" : SCENARIO_LABELS[n]}
          </button>
        ))}
      </div>

      {lastError ? (
        <div className="text-[11px] text-[color:var(--bad)] mt-1 mono truncate">
          {lastError}
        </div>
      ) : null}
    </div>
  );
}
