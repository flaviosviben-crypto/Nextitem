"use client";

import clsx from "clsx";
import Link from "next/link";
import { ReactNode } from "react";
import { EMPTY } from "@/lib/format";

export function Card({
  children,
  className,
  padded = true,
  id,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  id?: string;
}) {
  return (
    <div id={id} className={clsx("card", padded && "p-5", className)}>
      {children}
    </div>
  );
}

export function SectionTitle({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-[15px] font-semibold tracking-[-0.01em]">{title}</h2>
        {hint && <p className="mt-1 text-[13px] text-[var(--ink-2)]">{hint}</p>}
      </div>
      {action}
    </div>
  );
}

/**
 * A KPI tile. `value` already formatted; `hint` explains what the number means —
 * a number without its basis is a vanity metric.
 */
export function Stat({
  label,
  value,
  hint,
  tone,
  href,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "warning" | "critical";
  href?: string;
}) {
  const color =
    tone === "good"
      ? "var(--good)"
      : tone === "warning"
        ? "var(--warning)"
        : tone === "critical"
          ? "var(--critical)"
          : "var(--ink)";
  const body = (
    <>
      <div className="eyebrow">{label}</div>
      <div className="num mt-2 text-[26px] font-semibold leading-none" style={{ color }}>
        {value}
      </div>
      {hint && <div className="mt-2 text-[12px] leading-snug text-[var(--ink-3)]">{hint}</div>}
    </>
  );
  if (href) {
    return (
      <Link href={href} className="card block p-4 transition-colors hover:border-[var(--line-strong)]">
        {body}
      </Link>
    );
  }
  return <div className="card p-4">{body}</div>;
}

export function Badge({
  children,
  color,
  subtle = true,
}: {
  children: ReactNode;
  color?: string;
  subtle?: boolean;
}) {
  const c = color || "var(--ink-3)";
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{
        color: subtle ? c : "#fff",
        background: subtle ? `color-mix(in srgb, ${c} 14%, transparent)` : c,
        border: `1px solid color-mix(in srgb, ${c} 30%, transparent)`,
      }}
    >
      {children}
    </span>
  );
}

/** A status dot + label: identity is never carried by colour alone. */
export function StatusPill({ label, color }: { label: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[12px] text-[var(--ink-2)]">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  size = "md",
  disabled,
  type = "button",
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        size === "sm" ? "px-2.5 py-1.5 text-[12px]" : "px-3.5 py-2 text-[13px]",
        variant === "primary" && "bg-[var(--accent)] text-white hover:opacity-90",
        variant === "secondary" &&
          "border border-[var(--line)] bg-[var(--raised)] text-[var(--ink)] hover:border-[var(--line-strong)]",
        variant === "ghost" && "text-[var(--ink-2)] hover:bg-[var(--raised)] hover:text-[var(--ink)]",
        variant === "danger" && "border border-[var(--critical)] text-[var(--critical)] hover:bg-[color-mix(in_srgb,var(--critical)_12%,transparent)]",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="eyebrow">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "rounded-lg border border-[var(--line)] bg-[var(--raised)] px-3 py-2 text-[13px] text-[var(--ink)] placeholder:text-[var(--ink-3)] outline-none focus:border-[var(--accent)]";

/** A pill filter. Shared so the Opportunities and Action Center chips match. */
export function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={
        active
          ? "rounded-full border border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] px-3 py-1 text-[12px] font-medium text-[var(--ink)]"
          : "rounded-full border border-[var(--line)] px-3 py-1 text-[12px] text-[var(--ink-2)] transition-colors hover:border-[var(--line-strong)]"
      }
    >
      {children}
    </button>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} />;
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={clsx("h-5", c === 0 ? "w-[24%]" : "flex-1")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-3 text-[var(--ink-3)]">{icon}</div>}
      <h3 className="text-[14px] font-semibold">{title}</h3>
      {body && <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-[var(--ink-2)]">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <EmptyState
      title="Something went wrong"
      body={message}
      action={onRetry && <Button onClick={onRetry}>Try again</Button>}
    />
  );
}

/** Renders a possibly-null value, with the honest em dash for unknowns. */
export function Value({
  children,
  hint,
}: {
  children: string | number | null | undefined;
  hint?: string;
}) {
  const empty = children === null || children === undefined || children === EMPTY;
  return (
    <span
      className={empty ? "text-[var(--ink-3)]" : undefined}
      title={empty ? hint || "Not enough information in the imported data" : undefined}
    >
      {empty ? EMPTY : children}
    </span>
  );
}

export function Meter({
  value,
  color,
  height = 6,
}: {
  value: number;
  color?: string;
  height?: number;
}) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <div
      className="w-full overflow-hidden rounded-full"
      style={{ height, background: "var(--grid)" }}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500"
        style={{ width: `${clamped * 100}%`, background: color || "var(--accent)" }}
      />
    </div>
  );
}

export function Th({
  children,
  align = "left",
  className,
}: {
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      className={clsx(
        "sticky top-0 z-10 whitespace-nowrap border-b border-[var(--line)] bg-[var(--surface)] px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--ink-3)]",
        align === "right" && "text-right",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className,
}: {
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <td
      className={clsx(
        "whitespace-nowrap border-b border-[var(--line)] px-4 py-2.5 text-[13px]",
        align === "right" && "num text-right",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function ConfidenceTag({ level }: { level: string | null | undefined }) {
  if (!level) return null;
  const color =
    level === "High" ? "var(--good)" : level === "Medium" ? "var(--warning)" : "var(--ink-3)";
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-[var(--ink-3)]" title="How much data this is based on">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {level} confidence
    </span>
  );
}

export function EstimateNote({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 text-[11px] leading-relaxed text-[var(--ink-3)]">
      <span className="font-medium">Estimate.</span> {children}
    </p>
  );
}
