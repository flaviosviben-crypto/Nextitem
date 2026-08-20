"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  BarChart3,
  CheckSquare,
  Database,
  LayoutDashboard,
  Moon,
  Search,
  Sun,
  Target,
  Users,
} from "lucide-react";
import { api, apiIsSlow, subscribeApiSlow } from "@/lib/api";
import { Badge } from "./ui";

// Six destinations, in the order the work actually happens: see the day, work
// the list, track what you committed to, look someone up, check it paid off,
// keep the data flowing. Anything that does not serve that loop is not here.
const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/opportunities", label: "Opportunities", icon: Target },
  { href: "/actions", label: "Action Center", icon: CheckSquare },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/performance", label: "Performance", icon: BarChart3 },
  { href: "/data", label: "Data", icon: Database },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem("revenueos-theme") as "dark" | "light" | null;
    if (stored) {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    window.localStorage.setItem("revenueos-theme", next);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] flex-col border-r border-[var(--line)] bg-[var(--surface)] px-3 py-4 lg:flex">
        <Link href="/" className="mb-6 flex items-center gap-2.5 px-2">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[13px] font-bold text-white"
            style={{ background: "linear-gradient(135deg, var(--s1), var(--s7))" }}
          >
            R
          </span>
          <span>
            <span className="block text-[14px] font-semibold leading-tight tracking-[-0.01em]">
              RevenueOS
            </span>
            <span className="block text-[10px] uppercase tracking-[0.14em] text-[var(--ink-3)]">
              Revenue Intelligence
            </span>
          </span>
        </Link>

        <button
          onClick={() => setPaletteOpen(true)}
          className="mb-5 flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--raised)] px-2.5 py-2 text-[13px] text-[var(--ink-3)] transition-colors hover:border-[var(--line-strong)]"
        >
          <Search size={14} />
          <span className="flex-1 text-left">Search</span>
          <kbd className="rounded border border-[var(--line)] px-1.5 py-0.5 font-mono text-[10px]">
            ⌘K
          </kbd>
        </button>

        <nav className="flex-1 space-y-0.5">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors",
                  active
                    ? "bg-[var(--raised)] font-medium text-[var(--ink)]"
                    : "text-[var(--ink-2)] hover:bg-[var(--raised)] hover:text-[var(--ink)]",
                )}
              >
                <Icon size={15} className={active ? "text-[var(--accent)]" : undefined} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-4 border-t border-[var(--line)] pt-3">
          <button
            onClick={toggleTheme}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-[var(--ink-2)] transition-colors hover:bg-[var(--raised)] hover:text-[var(--ink)]"
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </aside>

      {/* Mobile nav */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-[var(--line)] bg-[var(--surface)] px-2 py-2 lg:hidden">
        {NAV.slice(0, 5).map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex flex-col items-center gap-1 px-2 py-1 text-[10px]",
                active ? "text-[var(--accent)]" : "text-[var(--ink-3)]",
              )}
            >
              <Icon size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* min-w-0 is load-bearing: a flex item defaults to min-width:auto and
          refuses to shrink below its content, so a wide table pushed the whole
          page sideways instead of scrolling inside its own container. */}
      <main className="min-w-0 flex-1 pb-20 lg:ml-[232px] lg:pb-0">{children}</main>

      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
    </div>
  );
}

type Hit = { kind: "customer" | "page"; id: string; title: string; subtitle: string };

function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [cursor, setCursor] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const search = useCallback(async (q: string) => {
    const pages: Hit[] = NAV.filter((n) => n.label.toLowerCase().includes(q.toLowerCase())).map(
      (n) => ({ kind: "page", id: n.href, title: n.label, subtitle: "Go to page" }),
    );
    if (q.trim().length < 2) {
      setHits(pages);
      return;
    }
    setLoading(true);
    try {
      const [customers] = await Promise.all([
        api.get<{ customers: { customer_id: string; name: string; segment: string | null }[] }>(
          `/customers?q=${encodeURIComponent(q)}&limit=8`,
        ),
      ]);
      setHits([
        ...customers.customers.map((c) => ({
          kind: "customer" as const,
          id: c.customer_id,
          title: c.name,
          subtitle: c.segment || "Customer",
        })),
        ...pages,
      ]);
    } catch {
      setHits(pages);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => search(query), 160);
    return () => clearTimeout(timer);
  }, [query, search]);

  const go = (hit: Hit) => {
    onClose();
    if (hit.kind === "customer") router.push(`/customers/${encodeURIComponent(hit.id)}`);
    else router.push(hit.id);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-lg overflow-hidden p-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-[var(--line)] px-4 py-3">
          <Search size={15} className="text-[var(--ink-3)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setCursor((c) => Math.min(c + 1, hits.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              } else if (e.key === "Enter" && hits[cursor]) {
                go(hits[cursor]);
              }
            }}
            placeholder="Search customers and pages…"
            className="flex-1 bg-transparent text-[14px] outline-none placeholder:text-[var(--ink-3)]"
          />
          {loading && <span className="text-[11px] text-[var(--ink-3)]">…</span>}
        </div>
        <div className="max-h-[340px] overflow-y-auto p-1.5">
          {hits.length === 0 ? (
            <p className="px-3 py-6 text-center text-[13px] text-[var(--ink-3)]">
              {query.length < 2 ? "Type to search" : "No matches"}
            </p>
          ) : (
            hits.map((hit, i) => (
              <button
                key={`${hit.kind}-${hit.id}`}
                onClick={() => go(hit)}
                onMouseEnter={() => setCursor(i)}
                className={clsx(
                  "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left",
                  i === cursor && "bg-[var(--raised)]",
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate text-[13px]">{hit.title}</span>
                  <span className="block truncate text-[11px] text-[var(--ink-3)]">
                    {hit.subtitle}
                  </span>
                </span>
                <Badge>{hit.kind}</Badge>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
        <h1 className="text-[24px] font-semibold tracking-[-0.02em]">{title}</h1>
        {subtitle && (
          <p className="mt-1.5 max-w-[68ch] text-[13px] leading-relaxed text-[var(--ink-2)]">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/**
 * Banner shown while any request is taking suspiciously long.
 *
 * Every screen renders skeletons while it waits, and a grid of grey blocks is
 * indistinguishable from an app that is simply broken — which is exactly how a
 * sleeping free-plan API presents itself for the first minute of the day.
 * Saying so is the difference between waiting and giving up.
 */
function SlowApiBanner() {
  const slow = useSyncExternalStore(subscribeApiSlow, apiIsSlow, () => false);
  if (!slow) return null;
  return (
    <div className="mb-5 flex items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--raised)] px-3.5 py-2.5 text-[13px] text-[var(--muted)]">
      <span className="inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-[var(--line)] border-t-[var(--accent)]" />
      <span>
        Waiting for the RevenueOS API. A free-plan service sleeps after 15 minutes of
        inactivity and can take up to a minute to wake.
      </span>
    </div>
  );
}

/**
 * The one place the desktop content width is decided.
 *
 * 1180px was chosen when every screen was a single stack of cards, and it
 * showed: on a 1440px monitor roughly a third of the usable width was doing
 * nothing while an operational table was squeezed into the middle. The answer
 * is not a wider column of the same stack — long prose at 1400px is unreadable
 * — it is a wider canvas that the pages spend on *columns*: Value beside
 * Lifecycle, revenue beside the funnel, an opportunity card that reads left to
 * right. Text that is genuinely prose is held back to PROSE below, so widening
 * the container never widens a paragraph.
 */
export const PROSE = "max-w-[68ch]";

export function Page({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-[1400px] px-5 py-7 lg:px-8 xl:px-10">
      <SlowApiBanner />
      {children}
    </div>
  );
}
