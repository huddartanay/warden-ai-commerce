import type { DemoSummary } from "@/lib/types";
import { formatRupees } from "@/lib/api";
import { Metric } from "./atoms";

export function KPICards({ summary }: { summary: DemoSummary | null }) {
  const s = summary;
  const protected_ = s ? formatRupees(s.protected_value) : "—";
  const blocked = s ? formatRupees(s.blocked_value) : "—";
  const total = s ? s.allowed_count + s.blocked_count + s.step_up_count : 0;
  const successRate =
    s && total > 0 ? Math.round((s.allowed_count / total) * 100) : null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <Metric
        label="Protected value"
        value={protected_}
        helper={s ? "AI-driven purchases authorized" : "no activity yet"}
        tone="ok"
      />
      <Metric
        label="Allowed"
        value={s?.allowed_count ?? "—"}
        helper="AI purchases Warden let through"
        tone="ok"
      />
      <Metric
        label="Blocked"
        value={s?.blocked_count ?? "—"}
        helper={s ? `${blocked} refused` : "AI overreach caught"}
        tone="bad"
      />
      <Metric
        label="Pending review"
        value={s?.pending_review_count ?? "—"}
        helper="Awaiting human decision"
        tone={s && s.pending_review_count > 0 ? "warn" : "neutral"}
      />
      <Metric
        label="Success rate"
        value={successRate === null ? "—" : `${successRate}%`}
        helper={
          s
            ? `${s.action_count} action${s.action_count === 1 ? "" : "s"} evaluated`
            : "no data"
        }
      />
    </div>
  );
}
