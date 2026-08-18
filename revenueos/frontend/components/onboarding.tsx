"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Database, Sparkles, Upload } from "lucide-react";
import { post, refreshWorkspace } from "@/lib/api";
import { Button, Card } from "@/components/ui";

/**
 * First-run screen. Two doors: bring your own data, or see the product working
 * on a realistic boutique in one click.
 */
export function Onboarding() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDemo = async () => {
    setLoading(true);
    setError(null);
    try {
      await post("/data/demo");
      await refreshWorkspace();
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the demo.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl py-10">
      <div className="animate-fade-up text-center">
        <div className="mx-auto mb-6 grid size-14 place-items-center rounded-[16px] text-[20px] font-bold text-white"
          style={{
            background: "linear-gradient(140deg,#7d7bfa,#5a4fe0)",
            boxShadow: "0 0 40px rgba(109,107,245,.28)",
          }}
        >
          R
        </div>
        <div className="eyebrow mb-3">Welcome to RevenueOS</div>
        <h1 className="text-[32px] font-semibold leading-[1.15] tracking-[-0.03em]">
          Turn your customer and inventory data
          <br />
          into daily revenue opportunities.
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-[14px] leading-relaxed text-[var(--color-ink-3)]">
          RevenueOS reads your existing exports — whatever their column names — works out who
          is worth contacting today, what to recommend them, and which stock is quietly
          turning into dead money.
        </p>
      </div>

      <div className="mt-9 grid gap-4 sm:grid-cols-2">
        <Card className="flex flex-col">
          <div className="mb-3 grid size-9 place-items-center rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)]">
            <Upload className="size-4 text-[var(--color-accent)]" />
          </div>
          <h2 className="text-[15px] font-semibold">Upload my data</h2>
          <p className="mt-1.5 flex-1 text-[12.5px] leading-relaxed text-[var(--color-ink-3)]">
            CSV or Excel exports from your POS or e-commerce. Any column names, any
            delimiter, any date format — the importer works them out and shows you what it
            found before anything is loaded.
          </p>
          <Button
            variant="primary"
            className="mt-5 w-full"
            icon={<ArrowRight className="size-3.5" />}
            onClick={() => router.push("/data")}
          >
            Start importing
          </Button>
        </Card>

        <Card className="flex flex-col">
          <div className="mb-3 grid size-9 place-items-center rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)]">
            <Database className="size-4 text-[var(--color-positive)]" />
          </div>
          <h2 className="text-[15px] font-semibold">Explore the demo boutique</h2>
          <p className="mt-1.5 flex-1 text-[12.5px] leading-relaxed text-[var(--color-ink-3)]">
            165 customers, 320 products and 1,600+ real transactions from a simulated Milan
            boutique. Every score you see is computed from that ledger — nothing in the demo
            is hardcoded.
          </p>
          <Button className="mt-5 w-full" loading={loading} onClick={loadDemo}
            icon={<Sparkles className="size-3.5" />}>
            {loading ? "Analysing…" : "Load demo boutique"}
          </Button>
        </Card>
      </div>

      {error ? (
        <p className="mt-4 text-center text-[12.5px] text-[var(--color-danger)]">{error}</p>
      ) : null}

      <div className="mt-10 grid gap-3 sm:grid-cols-3">
        {[
          ["Who to contact", "Ranked by value, urgency and how far past their own rhythm they are."],
          ["What to recommend", "Matched on category, brand, price, size and colour — with reasons."],
          ["What is at risk", "Stock ageing into dead money, and the clients who would still buy it."],
        ].map(([title, body]) => (
          <div key={title} className="rounded-[11px] border border-[var(--color-line)] px-4 py-3.5">
            <div className="text-[12.5px] font-medium">{title}</div>
            <div className="mt-1 text-[11.5px] leading-relaxed text-[var(--color-ink-4)]">
              {body}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
