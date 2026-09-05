import type { DemoSummary } from "@/lib/types";
import { API_BASE_URL } from "@/lib/api";
import { Pill } from "./atoms";

export function TopBar({
  summary,
  backendUp,
}: {
  summary: DemoSummary | null;
  backendUp: boolean;
}) {
  return (
    <header className="flex items-center justify-between gap-4 flex-wrap">
      <div className="flex items-center gap-3">
        <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border-strong)] font-semibold">
          W
        </span>
        <div>
          <div className="text-lg font-semibold tracking-tight leading-none">
            Warden
          </div>
          <div className="text-[11px] text-[color:var(--text-3)] mt-0.5">
            Deterministic authorization for AI-driven commerce
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <Pill tone={backendUp ? "ok" : "bad"}>
          backend {backendUp ? "up" : "unreachable"}
        </Pill>
        {summary ? (
          <>
            <Pill tone={summary.audit_chain_valid ? "ok" : "bad"}>
              audit {summary.audit_chain_valid ? "✓ verified" : "✕ broken"}
            </Pill>
            <Pill tone="neutral">
              {summary.action_count} actions
            </Pill>
            <Pill tone={summary.pending_review_count > 0 ? "warn" : "neutral"}>
              {summary.pending_review_count} pending review
            </Pill>
          </>
        ) : null}
        <span className="mono text-[10px] text-[color:var(--text-3)] hidden sm:inline">
          {API_BASE_URL}
        </span>
      </div>
    </header>
  );
}
