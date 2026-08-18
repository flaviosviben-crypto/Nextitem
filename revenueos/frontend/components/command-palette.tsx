"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Boxes,
  Database,
  FlaskConical,
  LayoutGrid,
  Lightbulb,
  Megaphone,
  Search,
  Sparkles,
  Target,
  Upload,
  User,
  Users,
  Wand2,
} from "lucide-react";
import { api, query, refreshWorkspace, post } from "@/lib/api";
import { cx, money } from "@/lib/format";
import { Badge } from "@/components/ui";

type SearchResult = {
  customers: { customerId: string; name: string; segment: string; totalSpend: number | null }[];
  products: { productId: string; name: string; brand: string; price: number | null; status: string }[];
};

const COMMANDS = [
  { id: "overview", label: "Go to Overview", href: "/", icon: LayoutGrid },
  { id: "analyst", label: "Ask the AI Analyst", href: "/analyst", icon: Sparkles },
  { id: "customers", label: "Browse customers", href: "/customers", icon: Users },
  { id: "recommendations", label: "Open recommendations", href: "/recommendations", icon: Wand2 },
  { id: "inventory", label: "Open inventory", href: "/inventory", icon: Boxes },
  { id: "actions", label: "View today's actions", href: "/opportunities", icon: Target },
  { id: "campaign", label: "Create a campaign", href: "/campaigns", icon: Megaphone },
  { id: "scenario", label: "Run a scenario", href: "/scenarios", icon: FlaskConical },
  { id: "insights", label: "Read weekly insights", href: "/insights", icon: Lightbulb },
  { id: "upload", label: "Upload data", href: "/data", icon: Upload },
  { id: "demo", label: "Load the demo boutique", action: "demo", icon: Database },
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [results, setResults] = useState<SearchResult>({ customers: [], products: [] });
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) {
      setValue("");
      setResults({ customers: [], products: [] });
      setCursor(0);
    }
  }, [open]);

  useEffect(() => {
    if (!open || value.trim().length < 2) {
      setResults({ customers: [], products: [] });
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const data = await api<SearchResult>(`/search${query({ q: value, limit: 5 })}`);
        if (!cancelled) setResults(data);
      } catch {
        if (!cancelled) setResults({ customers: [], products: [] });
      }
    }, 160);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [value, open]);

  const filteredCommands = COMMANDS.filter((command) =>
    command.label.toLowerCase().includes(value.trim().toLowerCase()),
  );
  const askItem =
    value.trim().length > 3 && !value.trim().startsWith("/")
      ? [{ id: "ask", label: `Ask AI: "${value.trim()}"`, icon: Sparkles }]
      : [];

  const items: { key: string; run: () => void }[] = [
    ...askItem.map((item) => ({
      key: item.id,
      run: () => {
        router.push(`/analyst?q=${encodeURIComponent(value.trim())}`);
        onClose();
      },
    })),
    ...results.customers.map((customer) => ({
      key: `c-${customer.customerId}`,
      run: () => {
        router.push(`/customers/${customer.customerId}`);
        onClose();
      },
    })),
    ...results.products.map((product) => ({
      key: `p-${product.productId}`,
      run: () => {
        router.push(`/inventory/${product.productId}`);
        onClose();
      },
    })),
    ...filteredCommands.map((command) => ({
      key: command.id,
      run: async () => {
        if (command.action === "demo") {
          setBusy(true);
          await post("/data/demo").catch(() => null);
          await refreshWorkspace();
          setBusy(false);
          router.push("/");
        } else if (command.href) {
          router.push(command.href);
        }
        onClose();
      },
    })),
  ];

  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") return onClose();
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setCursor((c) => Math.min(c + 1, items.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        items[cursor]?.run();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, items, cursor, onClose]);

  if (!open) return null;

  let index = -1;
  const nextIndex = () => (index += 1);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/55 px-4 pt-[12vh] backdrop-blur-[3px]"
      onClick={onClose}
    >
      <div
        className="animate-fade-up w-full max-w-[560px] overflow-hidden rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-elevated)] shadow-[var(--shadow-pop)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-[var(--color-line)] px-4">
          <Search className="size-4 shrink-0 text-[var(--color-ink-4)]" />
          <input
            autoFocus
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setCursor(0);
            }}
            placeholder="Search or ask a question…"
            className="h-12 flex-1 bg-transparent text-[14px] outline-none placeholder:text-[var(--color-ink-4)]"
          />
          <kbd className="rounded-[5px] border border-[var(--color-line)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-ink-4)]">
            esc
          </kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-2">
          {askItem.length ? (
            <Row
              active={nextIndex() === cursor}
              onClick={() => items[0]?.run()}
              icon={<Sparkles className="size-[15px] text-[var(--color-accent)]" />}
              title={`Ask AI: "${value.trim()}"`}
              hint="Enter"
            />
          ) : null}

          {results.customers.length ? (
            <Group label="Customers">
              {results.customers.map((customer) => {
                const i = nextIndex();
                return (
                  <Row
                    key={customer.customerId}
                    active={i === cursor}
                    onClick={() => items[i]?.run()}
                    icon={<User className="size-[15px] text-[var(--color-ink-4)]" />}
                    title={customer.name}
                    meta={
                      <span className="flex items-center gap-2">
                        {customer.segment ? (
                          <Badge size="sm">{customer.segment}</Badge>
                        ) : null}
                        <span className="num text-[var(--color-ink-4)]">
                          {money(customer.totalSpend, { compact: true })}
                        </span>
                      </span>
                    }
                  />
                );
              })}
            </Group>
          ) : null}

          {results.products.length ? (
            <Group label="Products">
              {results.products.map((product) => {
                const i = nextIndex();
                return (
                  <Row
                    key={product.productId}
                    active={i === cursor}
                    onClick={() => items[i]?.run()}
                    icon={<Boxes className="size-[15px] text-[var(--color-ink-4)]" />}
                    title={product.name}
                    meta={
                      <span className="num text-[var(--color-ink-4)]">
                        {money(product.price)}
                      </span>
                    }
                  />
                );
              })}
            </Group>
          ) : null}

          {filteredCommands.length ? (
            <Group label="Commands">
              {filteredCommands.map(({ id, label, icon: Icon }) => {
                const i = nextIndex();
                return (
                  <Row
                    key={id}
                    active={i === cursor}
                    onClick={() => items[i]?.run()}
                    icon={<Icon className="size-[15px] text-[var(--color-ink-4)]" />}
                    title={busy && id === "demo" ? "Loading demo boutique…" : label}
                  />
                );
              })}
            </Group>
          ) : null}

          {!items.length ? (
            <div className="px-3 py-8 text-center text-[12.5px] text-[var(--color-ink-4)]">
              Nothing matched “{value}”.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-1">
      <div className="eyebrow px-3 pb-1 pt-2">{label}</div>
      {children}
    </div>
  );
}

function Row({
  active,
  onClick,
  icon,
  title,
  meta,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  meta?: React.ReactNode;
  hint?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cx(
        "flex w-full items-center gap-2.5 rounded-[9px] px-3 py-2 text-left text-[13px] transition-colors",
        active ? "bg-[var(--color-surface-2)]" : "hover:bg-[var(--color-surface-2)]",
      )}
    >
      {icon}
      <span className="min-w-0 flex-1 truncate">{title}</span>
      {meta}
      {hint ? (
        <kbd className="rounded-[5px] border border-[var(--color-line)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-ink-4)]">
          {hint}
        </kbd>
      ) : null}
    </button>
  );
}
