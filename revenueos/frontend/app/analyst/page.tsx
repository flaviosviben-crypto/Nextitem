"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Database, Sparkles } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { Badge, Card, Skeleton, Td, Th } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { money, num } from "@/lib/format";

type Answer = {
  answer: string;
  engine: "claude" | "computed";
  tool_calls?: { tool: string; input: Record<string, unknown> }[];
  data_used?: string[];
  title?: string;
  rows?: Record<string, unknown>[];
  note?: string;
};

type Turn = { role: "user" | "assistant"; content: string; result?: Answer };

const SUGGESTIONS = [
  "Who should I contact today?",
  "What are my biggest inventory problems?",
  "Which VIPs have not bought recently?",
  "What should I do to make €5,000 more this week?",
  "Which category performs best?",
  "Who would buy my slowest-moving stock?",
];

export default function AnalystPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const status = useApi<{ available: boolean; model: string | null; reason: string | null }>("/ai/status");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  const send = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setInput("");
    const history = turns.map((t) => ({ role: t.role, content: t.content }));
    setTurns((prev) => [...prev, { role: "user", content: text }]);
    setBusy(true);
    try {
      const result = await api.post<Answer>("/ai/ask", { question: text, history });
      setTurns((prev) => [...prev, { role: "assistant", content: result.answer, result }]);
    } catch (err) {
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          content: err instanceof Error ? err.message : "The analyst is unavailable right now.",
          result: { answer: "", engine: "computed" },
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <PageHeader
        eyebrow="AI Analyst"
        title="Ask your data"
        subtitle="Every answer is computed from your imported data. The analyst runs the same analytics that power this app — it never estimates a number on its own."
        actions={
          status.data && (
            <Badge color={status.data.available ? "var(--good)" : "var(--warning)"}>
              {status.data.available ? `Live · ${status.data.model}` : "Computed mode"}
            </Badge>
          )
        }
      />

      {status.data && !status.data.available && (
        <Card className="mb-5 border-[color-mix(in_srgb,var(--warning)_35%,transparent)]">
          <div className="flex gap-3">
            <Database size={16} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div>
              <p className="text-[13px] font-medium">Conversational answers are off</p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--ink-2)]">
                {status.data.reason} You still get real, computed answers below — they are just
                returned as data rather than prose.
              </p>
            </div>
          </div>
        </Card>
      )}

      <Card padded={false} className="flex min-h-[62vh] flex-col">
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {turns.length === 0 && (
            <div className="py-8 text-center">
              <Sparkles size={22} className="mx-auto mb-3 text-[var(--accent)]" />
              <p className="text-[14px] font-medium">What would you like to know?</p>
              <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-[var(--ink-2)]">
                Ask about customers, stock, revenue or what to do next. Answers cite the actual
                records behind them.
              </p>
              <div className="mx-auto mt-6 flex max-w-2xl flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border border-[var(--line)] px-3 py-1.5 text-[12.5px] text-[var(--ink-2)] transition-colors hover:border-[var(--line-strong)] hover:text-[var(--ink)]"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn, i) =>
            turn.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[75%] rounded-2xl rounded-br-md bg-[var(--accent-soft)] px-4 py-2.5 text-[13.5px]">
                  {turn.content}
                </div>
              </div>
            ) : (
              <AssistantTurn key={i} turn={turn} />
            ),
          )}

          {busy && (
            <div className="flex gap-3">
              <Sparkles size={15} className="mt-1 shrink-0 text-[var(--accent)]" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3.5 w-[70%]" />
                <Skeleton className="h-3.5 w-[85%]" />
                <Skeleton className="h-3.5 w-[45%]" />
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="border-t border-[var(--line)] p-3"
        >
          <div className="flex items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--raised)] p-2 focus-within:border-[var(--accent)]">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              rows={1}
              placeholder="Ask about customers, inventory, revenue…"
              className="max-h-28 min-h-[38px] flex-1 resize-none bg-transparent px-2 py-2 text-[13.5px] outline-none placeholder:text-[var(--ink-3)]"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] text-white transition-opacity disabled:opacity-40"
            >
              <ArrowUp size={16} />
            </button>
          </div>
          <p className="mt-2 px-1 text-[11px] text-[var(--ink-3)]">
            Customer contact details are never sent to the model. Figures are estimates where labelled.
          </p>
        </form>
      </Card>
    </Page>
  );
}

function AssistantTurn({ turn }: { turn: Turn }) {
  const result = turn.result;
  return (
    <div className="flex gap-3">
      <Sparkles size={15} className="mt-1 shrink-0 text-[var(--accent)]" />
      <div className="min-w-0 flex-1">
        {turn.content && (
          <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed">{turn.content}</div>
        )}

        {result?.rows && result.rows.length > 0 && (
          <div className="mt-3 overflow-hidden rounded-xl border border-[var(--line)]">
            {result.title && (
              <div className="border-b border-[var(--line)] bg-[var(--raised)] px-3.5 py-2 text-[12px] font-medium">
                {result.title}
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    {Object.keys(result.rows[0]).map((key) => (
                      <Th key={key}>{key.replace(/_/g, " ")}</Th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i}>
                      {Object.entries(row).map(([key, value]) => (
                        <Td key={key} align={typeof value === "number" ? "right" : "left"}>
                          {renderCell(key, value)}
                        </Td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {result?.note && (
          <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--ink-3)]">{result.note}</p>
        )}

        {result?.data_used && result.data_used.length > 0 && (
          <details className="mt-2.5">
            <summary className="cursor-pointer text-[11.5px] text-[var(--ink-3)] hover:text-[var(--ink-2)]">
              Based on {result.data_used.length} data{" "}
              {result.data_used.length === 1 ? "query" : "queries"}
            </summary>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {result.data_used.map((tool, i) => (
                <span
                  key={i}
                  className="rounded-md bg-[var(--raised)] px-2 py-1 font-mono text-[10.5px] text-[var(--ink-2)]"
                >
                  {tool}
                </span>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

function renderCell(key: string, value: unknown) {
  if (value === null || value === undefined) return <span className="text-[var(--ink-3)]">—</span>;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (/value|spend|revenue|impact|potential/i.test(key)) return money(value);
    return num(value);
  }
  return String(value);
}
