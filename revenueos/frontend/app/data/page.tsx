"use client";

import { useRef, useState } from "react";
import { AlertTriangle, Check, FileUp, Info, Sparkles } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Meter,
  SectionTitle,
  Skeleton,
  Td,
  Th,
  inputClass,
} from "@/components/ui";
import { ColumnMapping, Quality, Summary, api, useApi } from "@/lib/api";
import { num, pct } from "@/lib/format";

type Kind = "customers" | "transactions" | "inventory";

type Staged = {
  ok: boolean;
  kind: Kind;
  filename: string;
  parse: {
    headers: string[];
    row_count: number;
    delimiter: string;
    encoding: string;
    had_header: boolean;
    issues: string[];
  };
  mappings: ColumnMapping[];
  ready: boolean;
  required: string[];
};

const FILES: { kind: Kind; title: string; blurb: string }[] = [
  {
    kind: "customers",
    title: "Customers",
    blurb: "Your standard CRM export: customer ID, name, contact details and consent. Optional if your sales export already carries a customer ID.",
  },
  {
    kind: "transactions",
    title: "Transactions",
    blurb: "Your standard sales export, one row per line item or per order. This is where spend, buying cycle and taste come from.",
  },
  {
    kind: "inventory",
    title: "Products & Inventory",
    blurb: "Your standard catalogue export: SKU, category, brand, price and stock on hand. Needed to recommend a specific piece.",
  },
];

export default function DataPage() {
  const summary = useApi<Summary>("/summary");
  // The API answers 404 for quality when nothing is imported, which is correct
  // but logs a console error on a perfectly normal empty workspace. Ask only
  // once there is something to report on.
  const quality = useApi<Quality>(summary.data?.loaded ? "/data/quality" : null,
                                  [summary.data?.loaded]);
  const imports = useApi<{
    source: string;
    imports: { kind: string; filename: string; rows: number; at: string; delimiter: string; encoding: string }[];
    counts: Record<string, number>;
  }>("/data/imports");

  const [staged, setStaged] = useState<Staged | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schema, setSchema] = useState<{ name: string; label: string }[]>([]);

  const refreshAll = () => {
    summary.refresh();
    quality.refresh();
    imports.refresh();
  };

  const upload = async (kind: Kind, file: File) => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("kind", kind);
      form.append("file", file);
      const result = await api.upload<Staged>("/data/upload", form);
      setStaged(result);
      const s = await api.get<{ fields: { name: string; label: string }[] }>(`/data/schema/${kind}`);
      setSchema(s.fields);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const remap = async (header: string, field: string) => {
    setBusy(true);
    try {
      const result = await api.post<Staged>("/data/mapping", {
        overrides: { [header]: field || null },
      });
      setStaged((prev) => (prev ? { ...prev, ...result } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the mapping");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/data/confirm");
      setStaged(null);
      refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const loadDemo = async () => {
    setBusy(true);
    try {
      await api.post("/data/demo", { seed: 7 });
      refreshAll();
    } finally {
      setBusy(false);
    }
  };

  const clearAll = async () => {
    if (!window.confirm("Delete all imported data from this workspace? This cannot be undone.")) return;
    setBusy(true);
    try {
      await api.del("/data");
      setStaged(null);
      refreshAll();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Data"
        title="Your data"
        subtitle="Three standard exports are all RevenueOS needs. Send them to us and we'll set the boutique up for you — or drop them in here and we'll map the columns, asking you only where we are unsure."
        asOf={summary.data?.as_of}
        actions={
          <>
            {/* Say the demo is loaded rather than offering to load it again:
                the button read as "nothing here yet" on a workspace that was
                already full. */}
            {summary.data?.source === "demo" ? (
              <span className="flex items-center gap-2.5 text-[13px] text-[var(--good)]">
                <span className="flex items-center gap-1.5">
                  <Check size={14} /> Demo boutique loaded
                </span>
                <button
                  onClick={loadDemo}
                  disabled={busy}
                  className="text-[12.5px] text-[var(--ink-3)] underline-offset-2 transition-colors hover:text-[var(--ink)] hover:underline disabled:opacity-50"
                >
                  Reset demo data
                </button>
              </span>
            ) : (
              <Button onClick={loadDemo} disabled={busy}>
                <Sparkles size={14} /> Load demo boutique
              </Button>
            )}
            {summary.data?.loaded && (
              /* Destructive and irreversible: available, never prominent. */
              <button
                onClick={clearAll}
                disabled={busy}
                className="text-[12.5px] text-[var(--muted)] underline-offset-2 transition-colors hover:text-[var(--critical)] hover:underline disabled:opacity-50"
              >
                Delete all data
              </button>
            )}
          </>
        }
      />

      {error && (
        <Card className="mb-4 border-[color-mix(in_srgb,var(--critical)_40%,transparent)]">
          <p className="text-[13px] text-[var(--critical)]">{error}</p>
        </Card>
      )}

      {staged ? (
        <MappingReview
          staged={staged}
          schema={schema}
          busy={busy}
          onRemap={remap}
          onConfirm={confirm}
          onCancel={() => setStaged(null)}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-3">
          {FILES.map((f) => (
            <UploadCard
              key={f.kind}
              {...f}
              busy={busy}
              rows={imports.data?.counts?.[f.kind === "inventory" ? "inventory" : f.kind]}
              onFile={(file) => upload(f.kind, file)}
            />
          ))}
        </div>
      )}

      {quality.data && (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1.3fr]">
          <Card>
            <SectionTitle title="Data health" hint={quality.data.summary} />
            <div className="flex items-baseline gap-3">
              <span className="num text-[36px] font-semibold leading-none">{quality.data.score}</span>
              <span className="text-[13px] text-[var(--ink-2)]">/ 100 · {quality.data.grade}</span>
            </div>
            <div className="mt-3">
              <Meter
                value={quality.data.score / 100}
                color={
                  quality.data.score >= 70
                    ? "var(--good)"
                    : quality.data.score >= 50
                      ? "var(--warning)"
                      : "var(--critical)"
                }
              />
            </div>

            <div className="mt-5">
              <div className="eyebrow mb-2.5">What your data supports</div>
              <ul className="space-y-2">
                {quality.data.capabilities.map((c) => (
                  <li key={c.name} className="flex gap-2.5 text-[12.5px]">
                    {c.available ? (
                      <Check size={14} className="mt-0.5 shrink-0 text-[var(--good)]" />
                    ) : (
                      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[var(--warning)]" />
                    )}
                    <span>
                      <span className={c.available ? "" : "text-[var(--ink-2)]"}>{c.name}</span>
                      {!c.available && (
                        <span className="mt-0.5 block text-[11.5px] leading-snug text-[var(--ink-3)]">
                          {c.unlock || c.reason}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Card>

          <Card>
            <SectionTitle title="Findings" hint="What we noticed while reading your files." />
            {quality.data.findings.length === 0 ? (
              <p className="py-6 text-center text-[13px] text-[var(--ink-3)]">
                No issues found in the imported data.
              </p>
            ) : (
              <ul className="space-y-2.5">
                {quality.data.findings.map((f, i) => (
                  <li key={i} className="flex gap-2.5 rounded-lg border border-[var(--line)] p-3">
                    <span className="mt-0.5 shrink-0">
                      {f.severity === "critical" ? (
                        <AlertTriangle size={14} className="text-[var(--critical)]" />
                      ) : f.severity === "warning" ? (
                        <AlertTriangle size={14} className="text-[var(--warning)]" />
                      ) : (
                        <Info size={14} className="text-[var(--ink-3)]" />
                      )}
                    </span>
                    <span>
                      <span className="block text-[13px] font-medium">{f.title}</span>
                      <span className="mt-0.5 block text-[12.5px] leading-relaxed text-[var(--ink-2)]">
                        {f.detail}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {imports.data?.imports && imports.data.imports.length > 0 && (
        <Card className="mt-5" padded={false}>
          <div className="p-5 pb-3">
            <SectionTitle title="Import history" />
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <Th>Type</Th>
                <Th>File</Th>
                <Th align="right">Rows</Th>
                <Th>Format</Th>
                <Th>When</Th>
              </tr>
            </thead>
            <tbody>
              {imports.data.imports.map((imp, i) => (
                <tr key={i}>
                  <Td><Badge>{imp.kind}</Badge></Td>
                  <Td>{imp.filename}</Td>
                  <Td align="right">{num(imp.rows)}</Td>
                  <Td>
                    <span className="text-[12px] text-[var(--ink-3)]">
                      {delimiterName(imp.delimiter)} · {imp.encoding}
                    </span>
                  </Td>
                  <Td>
                    <span className="text-[12px] text-[var(--ink-3)]">
                      {new Date(imp.at).toLocaleString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <p className="mt-6 text-[11.5px] leading-relaxed text-[var(--ink-3)]">
        Data stays in this workspace. Contact details are never sent to the AI model — the analyst
        sees internal IDs and computed metrics only. Use “Delete all data” to erase everything,
        in memory and on disk.
      </p>
    </Page>
  );
}

function delimiterName(d: string): string {
  if (d === "TAB") return "tab";
  return { ",": "comma", ";": "semicolon", "|": "pipe" }[d] || d;
}

function UploadCard({
  kind,
  title,
  blurb,
  busy,
  rows,
  onFile,
}: {
  kind: Kind;
  title: string;
  blurb: string;
  busy: boolean;
  rows?: number;
  onFile: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      className={`card flex flex-col p-5 transition-colors ${dragging ? "border-[var(--accent)]" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-[14px] font-semibold">{title}</h3>
        {rows ? <Badge color="var(--good)">{num(rows)} rows</Badge> : null}
      </div>
      <p className="mt-1.5 flex-1 text-[12.5px] leading-relaxed text-[var(--ink-2)]">{blurb}</p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.txt,.tsv,text/csv,text/plain"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
      <Button
        className="mt-4 w-full"
        variant="secondary"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        <FileUp size={14} /> Choose CSV
      </Button>
    </div>
  );
}

function MappingReview({
  staged,
  schema,
  busy,
  onRemap,
  onConfirm,
  onCancel,
}: {
  staged: Staged;
  schema: { name: string; label: string }[];
  busy: boolean;
  onRemap: (header: string, field: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const needsReview = staged.mappings.filter((m) => m.status === "review").length;

  return (
    <Card padded={false}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] p-4">
        <div>
          <h3 className="text-[14px] font-semibold">
            {staged.filename} — {staged.kind}
          </h3>
          <p className="mt-1 text-[12.5px] text-[var(--ink-2)]">
            {num(staged.parse.row_count)} rows · {staged.parse.headers.length} columns · separator{" "}
            <span className="font-mono">{staged.parse.delimiter}</span> · {staged.parse.encoding}
            {needsReview > 0 && ` · ${needsReview} to review`}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant="primary" onClick={onConfirm} disabled={busy || !staged.ready}>
            {staged.ready ? "Import data" : `Map ${staged.required.join(", ")} first`}
          </Button>
        </div>
      </div>

      {staged.parse.issues.length > 0 && (
        <div className="border-b border-[var(--line)] bg-[var(--raised)] px-4 py-2.5">
          {staged.parse.issues.map((issue, i) => (
            <p key={i} className="text-[12px] text-[var(--ink-2)]">{issue}</p>
          ))}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead>
            <tr>
              <Th>Your column</Th>
              <Th>Example</Th>
              <Th>Interpreted as</Th>
              <Th align="right">Confidence</Th>
            </tr>
          </thead>
          <tbody>
            {staged.mappings.map((m) => (
              <tr key={m.header}>
                <Td>
                  <span className="font-medium">{m.header}</span>
                </Td>
                <Td>
                  <span className="block max-w-[200px] truncate text-[12px] text-[var(--ink-3)]">
                    {String((m.profile as any)?.header ? "" : "")}
                    {m.reason}
                  </span>
                </Td>
                <Td>
                  <select
                    value={m.field || ""}
                    disabled={busy}
                    onChange={(e) => onRemap(m.header, e.target.value)}
                    className="w-full max-w-[240px] rounded-md border border-[var(--line)] bg-[var(--raised)] px-2 py-1.5 text-[12.5px] outline-none focus:border-[var(--accent)]"
                  >
                    <option value="">Ignore this column</option>
                    {schema.map((f) => (
                      <option key={f.name} value={f.name}>{f.label}</option>
                    ))}
                  </select>
                </Td>
                <Td align="right">
                  {m.field ? (
                    <span
                      className="num text-[12.5px]"
                      style={{
                        color:
                          m.status === "confident"
                            ? "var(--good)"
                            : m.status === "review"
                              ? "var(--warning)"
                              : "var(--ink-3)",
                      }}
                    >
                      {Math.round(m.confidence * 100)}%
                    </span>
                  ) : (
                    <span className="text-[12px] text-[var(--ink-3)]">—</span>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
