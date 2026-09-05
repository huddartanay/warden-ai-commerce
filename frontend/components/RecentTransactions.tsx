"use client";

import Link from "next/link";
import type { RecentAction } from "@/lib/types";
import { formatRupees, formatTimestamp, shortHash } from "@/lib/api";
import { ActionStatusPill, Pill, Section, Tone } from "./atoms";

const decisionTone: Record<string, Tone> = {
  ALLOW: "ok",
  STEP_UP: "warn",
  BLOCK: "bad",
};

export function RecentTransactions({
  actions,
}: {
  actions: RecentAction[] | null;
}) {
  const rows = actions ?? [];
  return (
    <Section
      eyebrow="Recent transactions"
      title="Every proposal Warden has evaluated"
    >
      {rows.length === 0 ? (
        <p className="text-[12.5px] text-[color:var(--text-3)] py-3">
          No transactions yet. Run a demo scenario above.
        </p>
      ) : (
        <div className="overflow-x-auto scroll-slim -mx-2">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-[color:var(--text-3)]">
                <th className="font-medium px-2 py-2 border-b border-[color:var(--border)]">
                  Time
                </th>
                <th className="font-medium px-2 py-2 border-b border-[color:var(--border)]">
                  Action
                </th>
                <th className="font-medium px-2 py-2 border-b border-[color:var(--border)] text-right">
                  Amount
                </th>
                <th className="font-medium px-2 py-2 border-b border-[color:var(--border)]">
                  Decision
                </th>
                <th className="font-medium px-2 py-2 border-b border-[color:var(--border)]">
                  Reason
                </th>
                <th className="font-medium px-2 py-2 border-b border-[color:var(--border)]">
                  Razorpay
                </th>
                <th className="font-medium px-2 py-2 border-b border-[color:var(--border)]">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.action_id}
                  className="hover:bg-[color:var(--surface-2)] transition-colors"
                >
                  <td className="px-2 py-2 border-b border-[color:var(--border-inset)] mono text-[11.5px] text-[color:var(--text-3)] tabular-nums">
                    {formatTimestamp(r.created_at)}
                  </td>
                  <td className="px-2 py-2 border-b border-[color:var(--border-inset)]">
                    <Link
                      href={`/transaction/${r.action_id}`}
                      className="text-[color:var(--brand-blue)] hover:underline mono text-[11.5px]"
                    >
                      {shortHash(r.action_id, 12)}
                    </Link>
                  </td>
                  <td className="px-2 py-2 border-b border-[color:var(--border-inset)] tabular-nums text-right font-medium">
                    {formatRupees(r.amount)}
                  </td>
                  <td className="px-2 py-2 border-b border-[color:var(--border-inset)]">
                    {r.decision_result ? (
                      <Pill tone={decisionTone[r.decision_result] ?? "neutral"}>
                        {r.decision_result === "STEP_UP"
                          ? "STEP-UP"
                          : r.decision_result}
                      </Pill>
                    ) : (
                      <span className="text-[color:var(--text-3)]">—</span>
                    )}
                  </td>
                  <td className="px-2 py-2 border-b border-[color:var(--border-inset)] mono text-[11px] text-[color:var(--text-2)]">
                    {r.reason_code ?? "—"}
                  </td>
                  <td className="px-2 py-2 border-b border-[color:var(--border-inset)] mono text-[11px] text-[color:var(--text-2)]">
                    {r.razorpay_order_id ? (
                      shortHash(r.razorpay_order_id, 14)
                    ) : (
                      <span className="text-[color:var(--text-3)]">
                        Not called
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2 border-b border-[color:var(--border-inset)]">
                    <ActionStatusPill status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
