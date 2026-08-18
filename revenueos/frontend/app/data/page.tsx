"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileUp,
  Info,
  Trash2,
  X,
} from "lucide-react";
import { del, post, refreshWorkspace, upload, useApi } from "@/lib/api";
import { count, cx, isKnown, percent } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Note,
  PageHeader,
  SectionHeader,
  Select,
  Skeleton,
  Tabs,
} from "@/components/ui";

type ColumnMapping = {
  column: string;
  field: string | null;
  label: string | null;
  confidence: number;
  status: "auto" | "review" | "unmapped";
  rationale: string;
  samples: string[];
  fillRate: number;
  alternatives: { field: string; label: string; confidence: number; rationale: string }[];
};

type Analysis = {
  token: string;
  entity: string;
  entityLabel: string;
  entityConfidence: number;
  parse: {
    filename: string;
    encoding: string;
    delimiter: string;
    rows: number;
    columns: number;
    warnings: string[];
    droppedEmptyColumns: string[];
  };
  mapping: {
    overallConfidence: number;
    missingRequired: string[];
    columns: ColumnMapping[];
  };
  preview: { columns: string[]; rows: (string | null)[][]; totalRows: number };
  needsReview: string[];
};

type SchemaField = { name: string; label: string; required: boolean; description: string; unlocks: string[] };
type Schema = { entities: Record<string, { label: string; fields: SchemaField[] }> };

type Health = {
  hasData: boolean;
  score: number | null;
  grade: string;
  summary: string;
  scoreDrivers: { label: string; value: string; impact: number; max: number }[];
  capabilities: { key: string; label: string; why: string; status: string; strength: number; missing: string[] }[];
  issues: {
    code: string;
    severity: string;
    title: string;
    detail: string;
    entity: string;
    count: number | null;
    examples: string[];
    fix: string | null;
  }[];
  completeness: Record<string, { present: boolean; rows: number; score: number | null }>;
  imports: { entity: string; filename: string; rows: number; confidence: number }[];
};

const ENTITY_LABELS: Record<string, string> = {
  customers: "Customers",
  transactions: "Transactions",
  inventory: "Inventory",
};

export default function DataPage() {
  const router = useRouter();
  const [tab, setTab] = useState("import");
  const { data: health, mutate: refreshHealth } = useApi<Health>("/data/health");
  const { data: schema } = useApi<Schema>("/data/schema");

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Data foundation"
        title="Data"
        subtitle="Bring your own exports. RevenueOS reads whatever column names you use, tells you what it understood, and asks when it is not sure."
      />

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "import", label: "Import" },
          { key: "health", label: "Data health" },
          { key: "privacy", label: "Privacy" },
        ]}
      />

      {tab === "import" ? (
        <ImportTab schema={schema} onImported={() => { refreshHealth(); refreshWorkspace(); }} health={health} />
      ) : tab === "health" ? (
        <HealthTab health={health} />
      ) : (
        <PrivacyTab
          onDeleted={() => {
            refreshHealth();
            refreshWorkspace();
            router.push("/");
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Import
 * ------------------------------------------------------------------ */
function ImportTab({
  schema,
  onImported,
  health,
}: {
  schema?: Schema;
  onImported: () => void;
  health?: Health;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [entity, setEntity] = useState<string>("");
  const [fieldMap, setFieldMap] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ entity: string; rowsLoaded: number; clean: { notes: string[] } } | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  const handleFile = async (file: File) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await upload<Analysis>("/data/analyse", form);
      setAnalysis(data);
      setEntity(data.entity);
      const initial: Record<string, string> = {};
      for (const column of data.mapping.columns) {
        if (column.field) initial[column.field] = column.column;
      }
      setFieldMap(initial);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read that file.");
      setAnalysis(null);
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!analysis) return;
    setBusy(true);
    setError(null);
    try {
      const data = await post<{ entity: string; rowsLoaded: number; clean: { notes: string[] } }>(
        "/data/commit",
        { token: analysis.token, entity, fieldMap },
      );
      setResult(data);
      setAnalysis(null);
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not import that file.");
    } finally {
      setBusy(false);
    }
  };

  const loadDemo = async () => {
    setDemoBusy(true);
    try {
      await post("/data/demo");
      onImported();
    } finally {
      setDemoBusy(false);
    }
  };

  const fields = schema?.entities[entity]?.fields ?? [];
  const mappedColumns = new Set(Object.values(fieldMap));

  return (
    <div className="space-y-4">
      {/* -------- loaded tables -------- */}
      <div className="grid gap-3 sm:grid-cols-3">
        {(["customers", "transactions", "inventory"] as const).map((key) => {
          const entry = health?.completeness?.[key];
          const imported = health?.imports?.find((i) => i.entity === key);
          return (
            <Card key={key}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-[13px] font-medium">{ENTITY_LABELS[key]}</div>
                  <div className="mt-1 text-[11.5px] text-[var(--color-ink-4)]">
                    {entry?.present ? `${count(entry.rows)} rows loaded` : "Not loaded"}
                  </div>
                </div>
                {entry?.present ? (
                  <CheckCircle2 className="size-4 text-[var(--color-positive)]" />
                ) : null}
              </div>
              {entry?.present && isKnown(entry.score) ? (
                <div className="mt-3">
                  <div className="mb-1 flex items-center justify-between text-[11px] text-[var(--color-ink-4)]">
                    <span>Field completeness</span>
                    <span className="num">{entry.score.toFixed(0)}%</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                    <div
                      className="h-full rounded-full bg-[var(--color-accent)]"
                      style={{ width: `${entry.score}%` }}
                    />
                  </div>
                  {imported ? (
                    <div className="mt-2 truncate text-[10.5px] text-[var(--color-ink-4)]">
                      {imported.filename} · mapped at {percent(imported.confidence)} confidence
                    </div>
                  ) : null}
                </div>
              ) : null}
            </Card>
          );
        })}
      </div>

      {/* -------- dropzone -------- */}
      {!analysis ? (
        <Card>
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              const file = event.dataTransfer.files?.[0];
              if (file) handleFile(file);
            }}
            className={cx(
              "flex flex-col items-center justify-center rounded-[12px] border border-dashed px-6 py-12 text-center transition-colors",
              dragging
                ? "border-[var(--color-accent-line)] bg-[var(--color-accent-soft)]"
                : "border-[var(--color-line-strong)]",
            )}
          >
            <div className="mb-3.5 grid size-11 place-items-center rounded-[12px] border border-[var(--color-line)] bg-[var(--color-surface-2)]">
              <FileUp className="size-5 text-[var(--color-ink-3)]" />
            </div>
            <h3 className="text-[14px] font-medium">Drop a CSV or Excel export here</h3>
            <p className="mt-1.5 max-w-md text-[12.5px] leading-relaxed text-[var(--color-ink-3)]">
              Customers, transactions or inventory — RevenueOS works out which is which, and
              handles semicolons, European decimals and unfamiliar column names on its own.
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.tsv,.txt,.xlsx,.xls"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) handleFile(file);
                event.target.value = "";
              }}
            />
            <div className="mt-5 flex flex-wrap justify-center gap-2.5">
              <Button variant="primary" loading={busy} onClick={() => fileRef.current?.click()}>
                Choose a file
              </Button>
              <Button loading={demoBusy} onClick={loadDemo} icon={<Database className="size-3.5" />}>
                Load demo boutique
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      {error ? <Note tone="danger">{error}</Note> : null}

      {result ? (
        <Note tone="positive" icon={<CheckCircle2 className="size-3.5" />}>
          <span className="font-medium">
            Imported {count(result.rowsLoaded)} {ENTITY_LABELS[result.entity].toLowerCase()} rows.
          </span>
          {result.clean.notes?.length ? (
            <ul className="mt-1.5 space-y-0.5">
              {result.clean.notes.map((note, index) => (
                <li key={index}>· {note}</li>
              ))}
            </ul>
          ) : null}
        </Note>
      ) : null}

      {/* -------- mapping review -------- */}
      {analysis ? (
        <div className="animate-fade-up space-y-4">
          <Card>
            <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="eyebrow mb-1.5">Step 2 · Confirm the mapping</div>
                <h2 className="text-[17px] font-semibold">{analysis.parse.filename}</h2>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[var(--color-ink-4)]">
                  <span>{count(analysis.parse.rows)} rows</span>
                  <span>· {analysis.parse.columns} columns</span>
                  <span>· {analysis.parse.encoding}</span>
                  <span>· “{analysis.parse.delimiter}” separated</span>
                </div>
              </div>
              <div className="flex items-center gap-2.5">
                <div>
                  <label className="eyebrow mb-1.5 block">Detected as</label>
                  <Select
                    value={entity}
                    onChange={(event) => {
                      setEntity(event.target.value);
                      setFieldMap({});
                    }}
                  >
                    {Object.entries(ENTITY_LABELS).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </div>
                <Badge tone={analysis.entityConfidence >= 0.7 ? "positive" : "warning"}>
                  {percent(analysis.entityConfidence)} sure
                </Badge>
              </div>
            </div>

            {analysis.parse.warnings?.length ? (
              <div className="mb-4">
                <Note tone="info">{analysis.parse.warnings.join(" ")}</Note>
              </div>
            ) : null}

            {analysis.mapping.missingRequired.length ? (
              <div className="mb-4">
                <Note tone="warning" icon={<AlertTriangle className="size-3.5" />}>
                  Required field{analysis.mapping.missingRequired.length > 1 ? "s" : ""} not
                  found: <span className="font-medium">
                    {analysis.mapping.missingRequired.join(", ")}
                  </span>
                  . Map {analysis.mapping.missingRequired.length > 1 ? "them" : "it"} below, or
                  RevenueOS will generate keys where it safely can.
                </Note>
              </div>
            ) : null}

            <div className="mb-3 flex items-center justify-between">
              <div className="text-[12.5px] text-[var(--color-ink-3)]">
                Detected column → interpreted meaning → confidence
              </div>
              <div className="flex gap-3 text-[11.5px]">
                <span className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-[var(--color-positive)]" /> auto
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-[var(--color-warning)]" /> review
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-[var(--color-ink-4)]" /> unmapped
                </span>
              </div>
            </div>

            <div className="space-y-1.5">
              {analysis.mapping.columns.map((column) => {
                const currentField =
                  Object.entries(fieldMap).find(([, source]) => source === column.column)?.[0] ?? "";
                return (
                  <div
                    key={column.column}
                    className="grid items-center gap-3 rounded-[10px] border border-[var(--color-line)] px-3 py-2.5 md:grid-cols-[1.1fr_auto_1.3fr_88px]"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-[12.5px] font-medium">{column.column}</div>
                      <div className="truncate text-[11px] text-[var(--color-ink-4)]">
                        {column.samples.slice(0, 3).join(" · ") || "empty"}
                      </div>
                    </div>
                    <span className="hidden text-[var(--color-ink-4)] md:block">→</span>
                    <Select
                      value={currentField}
                      onChange={(event) => {
                        const next = { ...fieldMap };
                        for (const [field, source] of Object.entries(next)) {
                          if (source === column.column) delete next[field];
                        }
                        if (event.target.value) next[event.target.value] = column.column;
                        setFieldMap(next);
                      }}
                      className="w-full"
                    >
                      <option value="">— ignore this column —</option>
                      {fields.map((field) => (
                        <option
                          key={field.name}
                          value={field.name}
                          disabled={
                            fieldMap[field.name] !== undefined &&
                            fieldMap[field.name] !== column.column
                          }
                        >
                          {field.label}
                          {field.required ? " *" : ""}
                        </option>
                      ))}
                    </Select>
                    <div className="text-right">
                      {currentField ? (
                        <Badge
                          size="sm"
                          tone={
                            column.status === "auto"
                              ? "positive"
                              : column.status === "review"
                                ? "warning"
                                : "neutral"
                          }
                          title={column.rationale}
                        >
                          {percent(column.confidence)}
                        </Badge>
                      ) : (
                        <span className="text-[11px] text-[var(--color-ink-4)]">ignored</span>
                      )}
                    </div>
                    <div className="col-span-full -mt-1 text-[11px] leading-relaxed text-[var(--color-ink-4)]">
                      {column.rationale}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-line)] pt-4">
              <div className="text-[12.5px] text-[var(--color-ink-3)]">
                {mappedColumns.size} of {analysis.parse.columns} columns mapped · overall
                confidence {percent(analysis.mapping.overallConfidence)}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  icon={<X className="size-3.5" />}
                  onClick={() => setAnalysis(null)}
                >
                  Cancel
                </Button>
                <Button variant="primary" loading={busy} onClick={commit}>
                  Import {count(analysis.parse.rows)} rows
                </Button>
              </div>
            </div>
          </Card>

          <Card>
            <SectionHeader title="File preview" subtitle="The first rows exactly as they were read." />
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[11.5px]">
                <thead>
                  <tr className="border-b border-[var(--color-line)]">
                    {analysis.preview.columns.map((column) => (
                      <th
                        key={column}
                        className="eyebrow whitespace-nowrap px-2.5 py-2 text-left font-semibold"
                      >
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analysis.preview.rows.map((row, index) => (
                    <tr key={index} className="border-b border-[var(--color-line)] last:border-0">
                      {row.map((cell, cellIndex) => (
                        <td
                          key={cellIndex}
                          className="max-w-[180px] truncate px-2.5 py-1.5 text-[var(--color-ink-3)]"
                        >
                          {cell ?? <span className="italic text-[var(--color-ink-4)]">empty</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Health
 * ------------------------------------------------------------------ */
function HealthTab({ health }: { health?: Health }) {
  if (!health) return <Skeleton className="h-96 w-full" />;
  if (!health.hasData) {
    return <EmptyState icon={<Database className="size-5" />} title="No data loaded yet" />;
  }

  const score = health.score ?? 0;
  const tone = score >= 85 ? "positive" : score >= 70 ? "info" : score >= 50 ? "warning" : "danger";

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-8">
          <div className="text-center">
            <div
              className="num text-[46px] font-semibold leading-none"
              style={{ color: `var(--color-${tone})` }}
            >
              {score}
            </div>
            <div className="mt-1.5 text-[11.5px] text-[var(--color-ink-4)]">out of 100</div>
            <Badge tone={tone} className="mt-2">
              {health.grade}
            </Badge>
          </div>
          <div className="min-w-[280px] flex-1">
            <div className="eyebrow mb-2">Data health score</div>
            <p className="text-[13px] leading-relaxed text-[var(--color-ink-2)]">
              {health.summary}
            </p>
            <div className="mt-4 space-y-1.5">
              {health.scoreDrivers.map((driver) => (
                <div key={driver.label} className="flex items-center gap-3">
                  <span className="w-[200px] shrink-0 text-[11.5px] text-[var(--color-ink-3)]">
                    {driver.label}
                  </span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                    <div
                      className="h-full rounded-full bg-[var(--color-accent)]"
                      style={{ width: `${Math.max(0, (driver.impact / driver.max) * 100)}%` }}
                    />
                  </div>
                  <span className="num w-16 shrink-0 text-right text-[11px] text-[var(--color-ink-4)]">
                    {driver.impact.toFixed(0)}/{driver.max}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="What your data powers"
          subtitle="Each capability is switched on only when the fields it needs actually exist."
        />
        <div className="grid gap-2.5 md:grid-cols-2">
          {health.capabilities.map((capability) => {
            const tone =
              capability.status === "full"
                ? "positive"
                : capability.status === "partial"
                  ? "info"
                  : capability.status === "limited"
                    ? "warning"
                    : "danger";
            return (
              <div
                key={capability.key}
                className="rounded-[10px] border border-[var(--color-line)] px-3.5 py-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12.5px] font-medium">{capability.label}</span>
                  <Badge size="sm" tone={tone}>
                    {capability.status}
                  </Badge>
                </div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--color-ink-3)]">
                  {capability.why}
                </p>
                {capability.missing.length ? (
                  <p className="mt-1.5 text-[11px] text-[var(--color-ink-4)]">
                    Would improve with: {capability.missing.join(", ").replace(/[._]/g, " ")}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      </Card>

      <Card>
        <SectionHeader
          title={`${health.issues.length} issue${health.issues.length === 1 ? "" : "s"} found`}
          subtitle="Ordered by severity. None of these stop RevenueOS working — they tell you where it is guessing."
        />
        {health.issues.length ? (
          <div className="space-y-2">
            {health.issues.map((issue) => (
              <div
                key={issue.code}
                className="rounded-[10px] border border-[var(--color-line)] px-3.5 py-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    size="sm"
                    tone={
                      issue.severity === "critical"
                        ? "danger"
                        : issue.severity === "warning"
                          ? "warning"
                          : "neutral"
                    }
                  >
                    {issue.severity}
                  </Badge>
                  <span className="text-[12.5px] font-medium">{issue.title}</span>
                  <span className="text-[11px] text-[var(--color-ink-4)]">{issue.entity}</span>
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--color-ink-3)]">
                  {issue.detail}
                </p>
                {issue.examples?.length ? (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {issue.examples.map((example, index) => (
                      <span
                        key={index}
                        className="rounded-[5px] bg-[var(--color-surface-2)] px-1.5 py-0.5 font-mono text-[10.5px] text-[var(--color-ink-4)]"
                      >
                        {example}
                      </span>
                    ))}
                  </div>
                ) : null}
                {issue.fix ? (
                  <p className="mt-2 text-[11.5px] text-[var(--color-ink-4)]">
                    <span className="font-medium">Fix: </span>
                    {issue.fix}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState compact title="No issues found" description="Your data is clean." />
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Privacy
 * ------------------------------------------------------------------ */
function PrivacyTab({ onDeleted }: { onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const wipe = async () => {
    setBusy(true);
    try {
      await del("/data/all");
      onDeleted();
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <SectionHeader
          eyebrow="GDPR"
          title="How your data is handled"
          subtitle="RevenueOS is built for European retail, so data minimisation is a default, not a setting."
        />
        <ul className="space-y-3">
          {[
            ["Everything stays local", "Your files are parsed and stored by the RevenueOS backend you run. Nothing is uploaded to a third-party analytics service."],
            ["The AI sees the minimum", "When a question is sent to Claude, email addresses, phone numbers and free-text notes are stripped. Customers are identified by internal ID and display name only — enough for you to know who to call, and nothing more."],
            ["No key in the browser", "The Anthropic API key is read from the server environment. It is never sent to the client and never appears in a network request you could inspect."],
            ["Analytics are computed, not generated", "Every number comes from a deterministic calculation over your tables. The model narrates results; it cannot invent a customer or a figure."],
            ["Deletion is immediate", "Erasing your data removes every table and every derived artefact from disk and memory at once."],
          ].map(([title, body]) => (
            <li key={title} className="flex gap-3">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--color-positive)]" />
              <div>
                <div className="text-[12.5px] font-medium">{title}</div>
                <p className="mt-0.5 text-[12px] leading-relaxed text-[var(--color-ink-3)]">{body}</p>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <SectionHeader
          title="Erase all data"
          subtitle="Removes every customer, transaction and product from this workspace, along with all computed analytics. This cannot be undone."
        />
        {confirming ? (
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-[12.5px] text-[var(--color-ink-2)]">
              This permanently deletes everything in this workspace. Continue?
            </span>
            <Button variant="danger" loading={busy} onClick={wipe} icon={<Trash2 className="size-3.5" />}>
              Yes, erase everything
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button variant="danger" onClick={() => setConfirming(true)} icon={<Trash2 className="size-3.5" />}>
            Erase all data
          </Button>
        )}
      </Card>
    </div>
  );
}
