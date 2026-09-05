"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchAuditForAction,
  fetchDemoSummary,
  fetchReadiness,
  verifyAuditChain,
} from "@/lib/api";
import type {
  AuditEntry,
  AuditVerifyResponse,
  DemoSummary,
  ScenarioEnvelope,
} from "@/lib/types";
import { usePolling } from "@/lib/polling";
import { AIBuyerPanel } from "@/components/AIBuyerPanel";
import { AuditPanel } from "@/components/AuditPanel";
import { DemoControls } from "@/components/DemoControls";
import { FlowIndicator } from "@/components/FlowIndicator";
import { HumanApprovalCard } from "@/components/HumanApprovalCard";
import { KPICards } from "@/components/KPICards";
import { RecentTransactions } from "@/components/RecentTransactions";
import { TopBar } from "@/components/TopBar";
import { WardenPanel } from "@/components/WardenPanel";

export default function DashboardPage() {
  const [envelope, setEnvelope] = useState<ScenarioEnvelope | null>(null);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResponse | null>(
    null,
  );
  const [verifying, setVerifying] = useState(false);
  const [freshAudit, setFreshAudit] = useState<AuditEntry[]>([]);

  const { data: summary } = usePolling<DemoSummary>(fetchDemoSummary, 3000);
  const [backendUp, setBackendUp] = useState(true);
  useEffect(() => {
    fetchReadiness().then((r) => setBackendUp(!("error" in r)));
    const id = window.setInterval(
      () => fetchReadiness().then((r) => setBackendUp(!("error" in r))),
      5000,
    );
    return () => window.clearInterval(id);
  }, []);

  // While a scenario is on-screen, refresh its audit entries every 3 seconds
  // (so human-approve / resolve interactions update the trail live).
  const currentActionId = envelope?.action?.id ?? null;
  useEffect(() => {
    if (!currentActionId) {
      setFreshAudit([]);
      return;
    }
    let cancelled = false;
    const load = () =>
      fetchAuditForAction(currentActionId)
        .then((r) => {
          if (!cancelled) setFreshAudit(r.entries);
        })
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [currentActionId]);

  const onScenario = useCallback((env: ScenarioEnvelope) => {
    setEnvelope(env);
    setVerifyResult(null);
    setFreshAudit(env.audit ?? []);
  }, []);

  const onReset = useCallback(() => {
    setEnvelope(null);
    setVerifyResult(null);
    setFreshAudit([]);
  }, []);

  const onVerify = useCallback(async () => {
    setVerifying(true);
    try {
      const v = await verifyAuditChain();
      setVerifyResult(v);
    } finally {
      setVerifying(false);
    }
  }, []);

  // The audit panel prefers freshAudit (per-action) when a scenario is active,
  // and falls back to envelope.audit (global last-40) when a scenario just ran.
  const mergedAudit = envelope
    ? envelope.audit?.length
      ? envelope.audit
      : freshAudit
    : [];

  const chainValid = verifyResult
    ? verifyResult.valid
    : (summary?.audit_chain_valid ?? null);
  const chainChecked = verifyResult ? verifyResult.entries_checked : null;

  return (
    <div className="min-h-screen mx-auto max-w-[1440px] px-6 py-5 flex flex-col gap-4">
      <TopBar summary={summary} backendUp={backendUp} />

      <KPICards summary={summary} />

      <FlowIndicator env={envelope} />

      <HumanApprovalCard env={envelope} onDone={() => undefined} />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[520px]">
        <div className="lg:col-span-3 flex flex-col">
          <AIBuyerPanel env={envelope} />
        </div>
        <div className="lg:col-span-6 flex flex-col">
          <WardenPanel env={envelope} />
        </div>
        <div className="lg:col-span-3 flex flex-col min-h-0">
          <AuditPanel
            env={envelope}
            auditEntries={mergedAudit}
            chainValid={chainValid}
            entriesChecked={chainChecked}
            onVerify={onVerify}
            verifying={verifying}
          />
        </div>
      </div>

      {verifyResult && !verifyResult.valid && verifyResult.first_invalid_entry ? (
        <div className="card border-[color:var(--bad-border)] p-3 text-[12px]">
          <span className="mono text-[color:var(--bad)] font-semibold">
            Chain broken —
          </span>{" "}
          <span className="text-[color:var(--text-2)]">
            first invalid seq{" "}
            {String(
              (verifyResult.first_invalid_entry as { seq?: number }).seq,
            )}{" "}
            ·{" "}
            {String(
              (verifyResult.first_invalid_entry as { reason?: string }).reason,
            )}
          </span>
        </div>
      ) : null}

      <DemoControls
        onScenario={onScenario}
        onReset={onReset}
        busy={verifying}
      />

      <RecentTransactions actions={summary?.recent_actions ?? null} />
    </div>
  );
}
