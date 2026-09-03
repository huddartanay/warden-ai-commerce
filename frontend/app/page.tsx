import { API_BASE_URL, fetchReadiness } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const readiness = await fetchReadiness();

  const backendReachable = !("error" in readiness);
  const dbOk = backendReachable && readiness.checks.database.ok;

  return (
    <main className="mx-auto max-w-4xl px-6 py-16 space-y-10">
      <header className="space-y-3">
        <p className="text-xs uppercase tracking-widest text-zinc-500">
          Razorpay AI Builder Internship 2026 · Track 1
        </p>
        <h1 className="text-4xl font-semibold tracking-tight text-zinc-100">
          Warden
        </h1>
        <p className="text-zinc-400 max-w-2xl">
          Let AI create demand. Let Warden decide when money can move.
        </p>
      </header>

      <section className="rounded-lg border border-zinc-800 bg-zinc-950 p-6 space-y-4">
        <h2 className="text-sm uppercase tracking-widest text-zinc-500">
          System status
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <StatusTile
            label="Backend"
            ok={backendReachable}
            detail={
              backendReachable
                ? `reachable at ${API_BASE_URL}`
                : `unreachable · ${"error" in readiness ? readiness.error : ""}`
            }
          />
          <StatusTile
            label="Database"
            ok={dbOk}
            detail={
              !backendReachable
                ? "unknown (backend unreachable)"
                : dbOk
                  ? "connected"
                  : `unavailable · ${readiness.checks.database.error ?? "unknown"}`
            }
          />
        </div>

        <p className="text-xs text-zinc-500">
          Stage 1 shell. Judge dashboard (AI Buyer · Warden · Audit trail) lands in
          a later stage.
        </p>
      </section>
    </main>
  );
}

function StatusTile({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            ok ? "bg-emerald-400" : "bg-red-400"
          }`}
        />
        <span className="text-sm font-medium text-zinc-200">{label}</span>
      </div>
      <p className="mt-2 text-xs text-zinc-500 break-all">{detail}</p>
    </div>
  );
}
