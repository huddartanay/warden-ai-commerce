"use client";

import { useState } from "react";
import {
  ScenarioName,
  SCENARIO_NAMES,
  resetDemo,
  runScenario,
} from "@/lib/api";
import type { ScenarioEnvelope } from "@/lib/types";
import { Section } from "./atoms";

interface ScenarioSpec {
  name: ScenarioName;
  label: string;
  glyph: string;
  helper: string;
  primary?: boolean;
  tone: "ok" | "bad" | "warn" | "info";
}

const SPECS: ScenarioSpec[] = [
  {
    name: "successful_purchase",
    label: "Successful Purchase",
    glyph: "✓",
    helper: "AI proposes valid coffee restock",
    primary: true,
    tone: "ok",
  },
  {
    name: "cap_exceeded",
    label: "Cap Exceeded",
    glyph: "✕",
    helper: "Amount over remaining limit",
    tone: "bad",
  },
  {
    name: "step_up",
    label: "Step-Up",
    glyph: "!",
    helper: "Human approval required",
    tone: "warn",
  },
  {
    name: "duplicate",
    label: "Duplicate",
    glyph: "↻",
    helper: "Same idempotency key twice",
    tone: "warn",
  },
  {
    name: "price_drift",
    label: "Price Drift",
    glyph: "⚠",
    helper: "Current price ≠ quoted price",
    tone: "bad",
  },
  {
    name: "payment_failure",
    label: "Payment Failure",
    glyph: "×",
    helper: "Capture fails — pending review",
    tone: "warn",
  },
];

const toneClass: Record<ScenarioSpec["tone"], string> = {
  ok: "hover:bg-[color:var(--ok-soft)] hover:border-[color:var(--ok-border)]",
  bad: "hover:bg-[color:var(--bad-soft)] hover:border-[color:var(--bad-border)]",
  warn: "hover:bg-[color:var(--warn-soft)] hover:border-[color:var(--warn-border)]",
  info: "hover:bg-[color:var(--brand-blue-soft)] hover:border-[color:var(--brand-blue)]",
};

const glyphColor: Record<ScenarioSpec["tone"], string> = {
  ok: "text-[color:var(--ok)]",
  bad: "text-[color:var(--bad)]",
  warn: "text-[color:var(--warn)]",
  info: "text-[color:var(--brand-blue)]",
};

export function DemoControls({
  onScenario,
  onReset,
  busy,
}: {
  onScenario: (env: ScenarioEnvelope) => void;
  onReset: () => void;
  busy: boolean;
}) {
  const [pending, setPending] = useState<ScenarioName | "reset" | null>(null);
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

  const anyPending = pending !== null || busy;

  return (
    <Section
      eyebrow="Demo scenarios"
      title="Run the complete backend workflow"
      right={
        <div className="flex items-center gap-2">
          {pending && pending !== "reset" ? (
            <span className="text-[11.5px] text-[color:var(--text-2)] flex items-center gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-[color:var(--brand-blue)] animate-pulse" />
              Running scenario…
            </span>
          ) : null}
          <button
            onClick={doReset}
            disabled={anyPending}
            className="text-[11.5px] px-3 py-1.5 rounded-md border border-[color:var(--border-strong)] bg-white hover:bg-[color:var(--surface-2)] disabled:opacity-50 font-medium"
          >
            {pending === "reset" ? "Resetting…" : "Reset demo"}
          </button>
        </div>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {SPECS.map((s) => (
          <button
            key={s.name}
            onClick={() => run(s.name)}
            disabled={anyPending}
            className={`text-left px-3.5 py-3 rounded-lg border border-[color:var(--border)] bg-white ${
              s.primary ? "ring-1 ring-[color:var(--ok-border)]" : ""
            } ${toneClass[s.tone]} disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-start gap-2.5`}
          >
            <span
              className={`inline-flex items-center justify-center w-6 h-6 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-2)] ${glyphColor[s.tone]} font-bold text-[12px] shrink-0`}
            >
              {s.glyph}
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold text-[color:var(--text)] flex items-center gap-2">
                {s.label}
                {s.primary ? (
                  <span className="text-[9.5px] font-medium text-[color:var(--ok)] uppercase tracking-wider">
                    primary
                  </span>
                ) : null}
                {pending === s.name ? (
                  <span className="text-[10px] text-[color:var(--text-3)]">
                    running…
                  </span>
                ) : null}
              </div>
              <div className="text-[11.5px] text-[color:var(--text-3)] mt-0.5 leading-snug">
                {s.helper}
              </div>
            </div>
          </button>
        ))}
      </div>

      {lastError ? (
        <div className="text-[11.5px] text-[color:var(--bad)] mt-3 mono">
          {lastError}
        </div>
      ) : null}
    </Section>
  );
}
