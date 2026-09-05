import type { DemoSummary } from "@/lib/types";
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
        <span className="inline-flex items-center justify-center w-9 h-9 rounded-md bg-[color:var(--accent)] text-white font-semibold shadow-sm">
          W
        </span>
        <div>
          <div className="text-[18px] font-semibold tracking-tight leading-none text-[color:var(--text)]">
            Warden
          </div>
          <div className="text-[11.5px] text-[color:var(--text-3)] mt-1">
            Trust infrastructure for AI commerce ·{" "}
            <span className="text-[color:var(--text-2)]">
              AI proposes. Warden authorizes.
            </span>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-[color:var(--ok)]">
          <span className="pulse" aria-hidden />
          LIVE DEMO
        </span>
        <span className="text-[color:var(--text-4)]">·</span>
        <Pill tone="info">Razorpay Test Mode</Pill>
        <Pill tone={backendUp ? "ok" : "bad"}>
          {backendUp ? "✓ Backend connected" : "Backend unreachable"}
        </Pill>
        {summary ? (
          <Pill tone={summary.audit_chain_valid ? "ok" : "bad"}>
            {summary.audit_chain_valid
              ? "✓ Audit verified"
              : "✕ Audit tampered"}
          </Pill>
        ) : null}
      </div>
    </header>
  );
}
