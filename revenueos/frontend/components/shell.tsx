"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import {
  Boxes,
  Database,
  FlaskConical,
  LayoutGrid,
  Lightbulb,
  Megaphone,
  Moon,
  Settings,
  Sparkles,
  Sun,
  Target,
  Users,
  Wand2,
  Zap,
} from "lucide-react";
import { useApi } from "@/lib/api";
import { cx } from "@/lib/format";
import { CommandPalette } from "@/components/command-palette";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutGrid },
  { href: "/analyst", label: "AI Analyst", icon: Sparkles },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/recommendations", label: "Recommendations", icon: Wand2 },
  { href: "/inventory", label: "Inventory", icon: Boxes },
  { href: "/opportunities", label: "Opportunities", icon: Target },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/scenarios", label: "Scenario Lab", icon: FlaskConical },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/data", label: "Data", icon: Database },
  { href: "/settings", label: "Settings", icon: Settings },
];

type Workspace = {
  name: string;
  source: string;
  hasData: boolean;
  counts: { customers: number; products: number; transactions: number; opportunities: number };
  dataHealth: number | null;
};

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { data: workspace } = useApi<Workspace>("/workspace", { refreshInterval: 0 });

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="relative z-10 flex min-h-screen">
      <Sidebar pathname={pathname} workspace={workspace} />
      <div className="flex min-w-0 flex-1 flex-col lg:pl-[232px]">
        <TopBar onOpenPalette={() => setPaletteOpen(true)} workspace={workspace} />
        <main className="mx-auto w-full max-w-[1320px] flex-1 px-5 pb-20 pt-6 lg:px-8">
          {children}
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

function Sidebar({ pathname, workspace }: { pathname: string; workspace?: Workspace }) {
  return (
    <aside
      className={cx(
        "fixed inset-y-0 left-0 z-30 hidden w-[232px] flex-col border-r border-[var(--color-line)] lg:flex",
        "bg-[color-mix(in_srgb,var(--color-surface)_82%,transparent)] backdrop-blur-xl",
      )}
    >
      <Link href="/" className="flex items-center gap-2.5 px-5 py-5">
        <div
          className="grid size-8 place-items-center rounded-[9px] text-[13px] font-bold text-white"
          style={{
            background: "linear-gradient(140deg,#7d7bfa,#5a4fe0)",
            boxShadow: "0 0 20px rgba(109,107,245,.25)",
          }}
        >
          R
        </div>
        <div className="min-w-0">
          <div className="text-[13.5px] font-semibold leading-tight tracking-[-0.01em]">
            RevenueOS
          </div>
          <div className="eyebrow mt-0.5">AI Revenue Intelligence</div>
        </div>
      </Link>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cx(
                "group flex items-center gap-2.5 rounded-[9px] px-3 py-[7px] text-[13px] transition-colors",
                active
                  ? "bg-[var(--color-surface-2)] font-medium text-[var(--color-ink)]"
                  : "text-[var(--color-ink-3)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-ink-2)]",
              )}
            >
              <Icon
                className={cx(
                  "size-[15px] shrink-0",
                  active ? "text-[var(--color-accent)]" : "text-[var(--color-ink-4)]",
                )}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-[var(--color-line)] p-3">
        <div className="rounded-[10px] bg-[var(--color-surface-2)] px-3 py-2.5">
          <div className="truncate text-[12px] font-medium">
            {workspace?.name ?? "No workspace"}
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-[11px] text-[var(--color-ink-4)]">
            {workspace?.hasData ? (
              <>
                <span className="num">{workspace.counts.customers.toLocaleString()}</span> clients
                <span className="text-[var(--color-line-strong)]">·</span>
                <span className="num">{workspace.counts.products.toLocaleString()}</span> SKUs
              </>
            ) : (
              "No data loaded"
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

function TopBar({
  onOpenPalette,
  workspace,
}: {
  onOpenPalette: () => void;
  workspace?: Workspace;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-[var(--color-line)] bg-[color-mix(in_srgb,var(--color-canvas)_82%,transparent)] backdrop-blur-xl">
      <div className="mx-auto flex h-14 w-full max-w-[1320px] items-center gap-3 px-5 lg:px-8">
        <Link href="/" className="flex items-center gap-2 lg:hidden">
          <div
            className="grid size-7 place-items-center rounded-[8px] text-[12px] font-bold text-white"
            style={{ background: "linear-gradient(140deg,#7d7bfa,#5a4fe0)" }}
          >
            R
          </div>
          <span className="text-[13px] font-semibold">RevenueOS</span>
        </Link>

        <button
          onClick={onOpenPalette}
          className={cx(
            "group ml-auto flex h-9 w-full max-w-[400px] items-center gap-2.5 rounded-[10px]",
            "border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3 text-left",
            "text-[12.5px] text-[var(--color-ink-4)] transition-colors",
            "hover:border-[var(--color-line-strong)] hover:text-[var(--color-ink-3)]",
          )}
        >
          <Zap className="size-3.5" />
          <span className="flex-1 truncate">Search customers, products, or ask AI…</span>
          <kbd className="hidden rounded-[5px] border border-[var(--color-line)] bg-[var(--color-canvas)] px-1.5 py-0.5 font-mono text-[10px] sm:block">
            ⌘K
          </kbd>
        </button>

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          {workspace?.dataHealth != null ? (
            <Link
              href="/data"
              className="hidden items-center gap-1.5 rounded-full border border-[var(--color-line)] bg-[var(--color-surface-2)] px-2.5 py-1 text-[11.5px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink-2)] sm:flex"
              title="Data health score"
            >
              <span
                className="size-1.5 rounded-full"
                style={{
                  background:
                    workspace.dataHealth >= 70
                      ? "var(--color-positive)"
                      : workspace.dataHealth >= 50
                        ? "var(--color-warning)"
                        : "var(--color-danger)",
                }}
              />
              Data <span className="num font-medium text-[var(--color-ink-2)]">{workspace.dataHealth}</span>
            </Link>
          ) : null}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = localStorage.getItem("revenueos-theme");
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    }
  }, []);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("revenueos-theme", next);
  };

  return (
    <button
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      className="grid size-9 place-items-center rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink)]"
    >
      {theme === "dark" ? <Sun className="size-[15px]" /> : <Moon className="size-[15px]" />}
    </button>
  );
}
