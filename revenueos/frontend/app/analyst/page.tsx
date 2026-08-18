"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowUp, Database, Sparkles, Table2 } from "lucide-react";
import { post, useApi } from "@/lib/api";
import { cx } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Note,
  PageHeader,
  Skeleton,
} from "@/components/ui";

type Status = {
  aiEnabled: boolean;
  aiModel: string | null;
  hasData: boolean;
  suggestions: string[];
  mode: string;
  notice: string | null;
};

type Answer = {
  answer: string;
  toolCalls: { tool: string; input: Record<string, unknown> }[];
  data: { tool: string; result: unknown }[];
  mode: string;
  notice: string | null;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  toolCalls?: { tool: string; input: Record<string, unknown> }[];
  mode?: string;
  notice?: string | null;
};

const TOOL_LABELS: Record<string, string> = {
  find_customers: "Queried customer metrics",
  recommend_products_for_customer: "Ran the matching engine",
  recommend_customers_for_product: "Ranked customers for a product",
  find_products: "Queried inventory",
  get_opportunities: "Read the opportunity engine",
  get_performance: "Computed revenue performance",
  get_segments: "Computed RFM segments",
  get_inventory_summary: "Computed inventory KPIs",
  simulate: "Ran a simulation",
};

function AnalystInner() {
  const params = useSearchParams();
  const { data: status } = useApi<Status>("/analyst/status");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const asked = useRef(false);

  const send = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setInput("");
    setMessages((previous) => [...previous, { role: "user", content: trimmed }]);
    setBusy(true);
    try {
      const history = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const answer = await post<Answer>("/analyst/ask", { question: trimmed, history });
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: answer.answer,
          toolCalls: answer.toolCalls,
          mode: answer.mode,
          notice: answer.notice,
        },
      ]);
    } catch (error) {
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content:
            error instanceof Error
              ? `That did not work: ${error.message}`
              : "Something went wrong.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const initial = params.get("q");
    if (initial && !asked.current) {
      asked.current = true;
      void send(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  if (!status) return <Skeleton className="h-96 w-full" />;

  if (!status.hasData) {
    return (
      <div>
        <PageHeader eyebrow="Revenue copilot" title="AI Analyst" />
        <EmptyState
          icon={<Database className="size-5" />}
          title="No data to analyse yet"
          description="Load the demo boutique or upload your exports, and the analyst can answer questions about them."
          action={
            <Link href="/data">
              <Button variant="primary">Go to Data</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Revenue copilot"
        title="AI Analyst"
        subtitle="Ask anything about your customers, stock and sales. Every figure in an answer is computed from your data — the model interprets, it never calculates."
        action={
          <Badge tone={status.aiEnabled ? "positive" : "warning"} dot>
            {status.aiEnabled ? status.aiModel : "Deterministic mode"}
          </Badge>
        }
      />

      {status.notice ? (
        <div className="mb-4">
          <Note tone="warning">{status.notice}</Note>
        </div>
      ) : null}

      <Card padded={false} className="flex min-h-[560px] flex-col overflow-hidden">
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {!messages.length ? (
            <div className="py-8">
              <div className="mx-auto mb-5 grid size-11 place-items-center rounded-[12px] border border-[var(--color-line)] bg-[var(--color-surface-2)]">
                <Sparkles className="size-5 text-[var(--color-accent)]" />
              </div>
              <p className="mb-6 text-center text-[13.5px] text-[var(--color-ink-3)]">
                What would you like to know?
              </p>
              <div className="mx-auto grid max-w-2xl gap-2 sm:grid-cols-2">
                {status.suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => send(suggestion)}
                    className="rounded-[10px] border border-[var(--color-line)] px-3.5 py-2.5 text-left text-[12.5px] text-[var(--color-ink-2)] transition-colors hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-2)]"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {messages.map((message, index) => (
            <MessageBubble key={index} message={message} />
          ))}

          {busy ? (
            <div className="flex items-center gap-2.5 text-[12.5px] text-[var(--color-ink-4)]">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="size-1.5 animate-pulse rounded-full bg-[var(--color-accent)]"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </span>
              Running the analysis…
            </div>
          ) : null}
          <div ref={endRef} />
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            send(input);
          }}
          className="border-t border-[var(--color-line)] p-3"
        >
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send(input);
                }
              }}
              rows={1}
              placeholder="Ask about customers, stock, or what to do today…"
              className="max-h-32 flex-1 resize-none rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3.5 py-2.5 text-[13px] outline-none transition-colors placeholder:text-[var(--color-ink-4)] focus:border-[var(--color-accent-line)]"
            />
            <Button
              type="submit"
              variant="primary"
              disabled={!input.trim() || busy}
              className="size-9 !p-0"
              aria-label="Send"
            >
              <ArrowUp className="size-4" />
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-[12px] rounded-br-[4px] bg-[var(--color-accent-soft)] px-3.5 py-2.5 text-[13px] text-[var(--color-ink)]">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up flex gap-3">
      <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-[9px] border border-[var(--color-line)] bg-[var(--color-surface-2)]">
        <Sparkles className="size-3.5 text-[var(--color-accent)]" />
      </div>
      <div className="min-w-0 flex-1">
        {message.toolCalls?.length ? (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {message.toolCalls.map((call, index) => (
              <Badge key={index} size="sm" tone="neutral">
                <Table2 className="size-2.5" />
                {TOOL_LABELS[call.tool] ?? call.tool}
              </Badge>
            ))}
          </div>
        ) : null}
        <Markdown text={message.content} />
        {message.notice ? (
          <p className="mt-2.5 text-[11px] text-[var(--color-ink-4)]">{message.notice}</p>
        ) : null}
      </div>
    </div>
  );
}

/** Minimal markdown: tables, bold, headings and lists — what the prompts emit. */
function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  const lines = text.split("\n");
  let index = 0;
  let key = 0;

  const inline = (value: string) =>
    value.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={i} className="font-semibold text-[var(--color-ink)]">
          {part.slice(2, -2)}
        </strong>
      ) : (
        <span key={i}>{part}</span>
      ),
    );

  while (index < lines.length) {
    const line = lines[index];

    if (line.trim().startsWith("|") && lines[index + 1]?.includes("---")) {
      const header = line.split("|").slice(1, -1).map((cell) => cell.trim());
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(lines[index].split("|").slice(1, -1).map((cell) => cell.trim()));
        index += 1;
      }
      blocks.push(
        <div key={key++} className="my-3 overflow-x-auto rounded-[10px] border border-[var(--color-line)]">
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="border-b border-[var(--color-line)] bg-[var(--color-surface-2)]">
                {header.map((cell, i) => (
                  <th key={i} className="whitespace-nowrap px-3 py-2 text-left font-semibold">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-[var(--color-line)] last:border-0">
                  {row.map((cell, j) => (
                    <td key={j} className="px-3 py-2 align-top text-[var(--color-ink-2)]">
                      {inline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (line.startsWith("## ")) {
      blocks.push(
        <h3 key={key++} className="mb-1.5 mt-4 text-[13px] font-semibold first:mt-0">
          {line.slice(3)}
        </h3>,
      );
      index += 1;
      continue;
    }

    if (line.trim().startsWith("- ")) {
      const items: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("- ")) {
        items.push(lines[index].trim().slice(2));
        index += 1;
      }
      blocks.push(
        <ul key={key++} className="my-2 space-y-1.5">
          {items.map((item, i) => (
            <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
              <span className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--color-ink-4)]" />
              <span>{inline(item)}</span>
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    if (line.trim()) {
      blocks.push(
        <p key={key++} className="my-2 text-[13px] leading-relaxed text-[var(--color-ink-2)] first:mt-0">
          {inline(line)}
        </p>,
      );
    }
    index += 1;
  }

  return <div>{blocks}</div>;
}

export default function AnalystPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <AnalystInner />
    </Suspense>
  );
}
