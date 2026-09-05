import type { ScenarioEnvelope } from "@/lib/types";
import { formatRupees } from "@/lib/api";
import { KV, Pill, Section } from "./atoms";

export function AIBuyerPanel({ env }: { env: ScenarioEnvelope | null }) {
  const agent = env?.agent ?? null;
  const cart = env?.cart ?? null;

  return (
    <Section
      title="AI Buyer"
      right={
        agent ? (
          <Pill
            tone={
              agent.confidence >= 0.7 ? "ok" : agent.confidence >= 0.4 ? "warn" : "bad"
            }
          >
            conf {agent.confidence.toFixed(2)}
          </Pill>
        ) : null
      }
      className="h-full"
    >
      <div className="flex flex-col gap-4 min-h-0">
        <div>
          <div className="section-label mb-1">Intent</div>
          <p className="text-[13px] text-[color:var(--text)] leading-snug">
            {agent?.intent_text ?? env?.decision?.explanation ?? (
              <span className="text-[color:var(--text-3)]">
                Click a demo button to run a scenario end-to-end. The AI Buyer's
                intent will land here.
              </span>
            )}
          </p>
        </div>

        {agent?.parsed_intent ? (
          <div className="card p-3">
            <div className="section-label mb-2">Agent reasoning</div>
            <KV k="Category" v={agent.parsed_intent.desired_category} />
            <KV
              k="Max spend"
              v={agent.parsed_intent.max_spend ? formatRupees(agent.parsed_intent.max_spend) : "unbounded"}
            />
            <KV k="Urgency" v={agent.parsed_intent.urgency} />
            <p className="text-[11px] text-[color:var(--text-3)] mt-2 leading-snug">
              {agent.parsed_intent.rationale}
            </p>
          </div>
        ) : null}

        {agent?.selected?.length ? (
          <div>
            <div className="section-label mb-2">Selected products</div>
            <div className="flex flex-col gap-1.5">
              {agent.selected.map((s) => {
                const c = agent.candidates.find((x) => x.id === s.catalog_item_id);
                return (
                  <div
                    key={s.catalog_item_id}
                    className="flex items-center justify-between text-[13px] py-1"
                  >
                    <span className="truncate">
                      {c?.name ?? s.catalog_item_id}{" "}
                      <span className="text-[color:var(--text-3)]">× {s.quantity}</span>
                    </span>
                    <span className="mono text-[12px] tabular-nums">
                      {formatRupees(s.unit_price)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {cart ? (
          <div className="mt-auto pt-3 hairline flex items-center justify-between">
            <div>
              <div className="section-label">Cart total</div>
              <div className="mono text-[11px] text-[color:var(--text-3)]">
                {cart.id}
              </div>
            </div>
            <div className="text-2xl font-semibold tracking-tight tabular-nums">
              {formatRupees(cart.total_amount)}
            </div>
          </div>
        ) : null}

        {env?.action ? (
          <div className="hairline pt-3">
            <div className="section-label mb-1">Current action</div>
            <div className="mono text-[11px] text-[color:var(--text-3)] break-all">
              {env.action.id}
            </div>
          </div>
        ) : null}
      </div>
    </Section>
  );
}
