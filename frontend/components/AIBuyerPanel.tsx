import type { ScenarioEnvelope } from "@/lib/types";
import { formatRupees } from "@/lib/api";
import { Pill, Section, TrustNote } from "./atoms";

function safeSummary(rationale?: string | null): string {
  if (!rationale) return "";
  // Never expose raw chain-of-thought. Take the first sentence.
  const firstSentence = rationale.split(/[.!?]/)[0]?.trim();
  return firstSentence
    ? firstSentence.length > 90
      ? firstSentence.slice(0, 90) + "…"
      : firstSentence
    : "";
}

export function AIBuyerPanel({ env }: { env: ScenarioEnvelope | null }) {
  const agent = env?.agent ?? null;
  const cart = env?.cart ?? null;
  const decision = env?.decision?.result ?? null;

  const agentStatus =
    decision === "ALLOW"
      ? { label: "Proposal accepted", tone: "ok" as const }
      : decision === "STEP_UP"
        ? { label: "Awaiting human approval", tone: "warn" as const }
        : decision === "BLOCK"
          ? { label: "Proposal blocked", tone: "bad" as const }
          : { label: "Idle", tone: "neutral" as const };

  const summary = safeSummary(agent?.parsed_intent?.rationale);

  return (
    <Section
      eyebrow="AI Buyer"
      title="Customer's shopping agent"
      right={
        agent ? (
          <Pill tone={agentStatus.tone}>{agentStatus.label}</Pill>
        ) : null
      }
      className="h-full"
    >
      {agent ? (
        <div className="flex flex-col gap-4">
          <div>
            <div className="eyebrow mb-1.5">Customer intent</div>
            <p className="text-[13.5px] text-[color:var(--text)] leading-snug">
              “{agent.intent_text}”
            </p>
          </div>

          <div>
            <div className="eyebrow mb-2">Product discovery</div>
            {agent.selected.length ? (
              <div className="flex flex-col gap-1">
                {agent.selected.map((s) => {
                  const c = agent.candidates.find(
                    (x) => x.id === s.catalog_item_id,
                  );
                  return (
                    <div
                      key={s.catalog_item_id}
                      className="flex items-center justify-between text-[13px] py-1.5 border-b border-[color:var(--border-inset)] last:border-b-0"
                    >
                      <span className="truncate">
                        {c?.name ?? s.catalog_item_id}
                        {s.quantity > 1 ? (
                          <span className="text-[color:var(--text-3)]">
                            {" "}
                            × {s.quantity}
                          </span>
                        ) : null}
                      </span>
                      <span className="mono text-[12px] tabular-nums text-[color:var(--text-2)]">
                        {formatRupees(s.unit_price)}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-[12px] text-[color:var(--text-3)]">
                No products selected.
              </p>
            )}
          </div>

          {cart ? (
            <div className="card-flat p-3 flex items-center justify-between">
              <div>
                <div className="eyebrow">Proposed cart</div>
                <div className="text-[11.5px] text-[color:var(--text-3)] mt-0.5">
                  {cart.items.length} item{cart.items.length === 1 ? "" : "s"}
                </div>
              </div>
              <div className="text-[22px] font-semibold tabular-nums tracking-tight">
                {formatRupees(cart.total_amount)}
              </div>
            </div>
          ) : null}

          {summary ? (
            <div>
              <div className="eyebrow mb-1.5">Agent status</div>
              <p className="text-[12.5px] text-[color:var(--text-2)] leading-snug">
                {summary}.
              </p>
            </div>
          ) : null}

          <div className="mt-auto pt-3">
            <TrustNote>Agent proposes only. Never authorizes payment.</TrustNote>
          </div>
        </div>
      ) : env?.action ? (
        <div className="flex flex-col gap-4">
          <div>
            <div className="eyebrow mb-1.5">Direct proposal</div>
            <p className="text-[13.5px] text-[color:var(--text)] leading-snug">
              A payment proposal was submitted directly to Warden (no AI buyer
              in this scenario).
            </p>
          </div>
          <div className="card-flat p-3 flex items-center justify-between">
            <div>
              <div className="eyebrow">Amount</div>
              <div className="text-[11.5px] text-[color:var(--text-3)] mt-0.5 mono">
                {env.action.id}
              </div>
            </div>
            <div className="text-[22px] font-semibold tabular-nums tracking-tight">
              {formatRupees(env.action.amount)}
            </div>
          </div>
          <div className="mt-auto pt-3">
            <TrustNote>All proposals — AI or human — pass through Warden.</TrustNote>
          </div>
        </div>
      ) : (
        <EmptyState />
      )}
    </Section>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center gap-3 py-4">
      <div className="flex items-center gap-1.5 text-[color:var(--text-4)]">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--neutral-soft)] border border-[color:var(--border)] text-[10px]">
          ○
        </span>
        <span className="text-[11px]">→</span>
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--neutral-soft)] border border-[color:var(--border)] text-[10px]">
          ○
        </span>
      </div>
      <div>
        <div className="text-[13px] font-medium text-[color:var(--text-2)]">
          Waiting for an AI purchase proposal
        </div>
        <div className="text-[11.5px] text-[color:var(--text-3)] mt-1 max-w-[220px]">
          Run a demo scenario to see the buyer agent build a cart.
        </div>
      </div>
    </div>
  );
}
