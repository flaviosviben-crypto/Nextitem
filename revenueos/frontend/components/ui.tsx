"use client";

import { ReactNode, forwardRef } from "react";
import { AlertCircle, Info, Loader2 } from "lucide-react";
import { cx, UNKNOWN } from "@/lib/format";
import type { Tone } from "@/lib/theme";

/* ------------------------------------------------------------------ *
 * Surfaces
 * ------------------------------------------------------------------ */
export function Card({
  children,
  className,
  padded = true,
  interactive = false,
  ...rest
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  interactive?: boolean;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        "card",
        padded && "p-5",
        interactive &&
          "transition-colors hover:border-[var(--color-line-strong)] cursor-pointer",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function SectionHeader({
  title,
  subtitle,
  action,
  eyebrow,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow ? <div className="eyebrow mb-1.5">{eyebrow}</div> : null}
        <h2 className="text-[15px] font-semibold tracking-[-0.01em]">{title}</h2>
        {subtitle ? (
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-ink-3)]">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow ? <div className="eyebrow mb-2">{eyebrow}</div> : null}
        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.025em]">{title}</h1>
        {subtitle ? (
          <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-[var(--color-ink-3)]">
            {subtitle}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

/* ------------------------------------------------------------------ *
 * Badges & meters
 * ------------------------------------------------------------------ */
const TONE_CLASS: Record<Tone, string> = {
  accent: "text-[var(--color-accent)] bg-[var(--color-accent-soft)] border-[var(--color-accent-line)]",
  positive: "text-[var(--color-positive)] bg-[var(--color-positive-soft)] border-[color-mix(in_srgb,var(--color-positive)_28%,transparent)]",
  warning: "text-[var(--color-warning)] bg-[var(--color-warning-soft)] border-[color-mix(in_srgb,var(--color-warning)_28%,transparent)]",
  danger: "text-[var(--color-danger)] bg-[var(--color-danger-soft)] border-[color-mix(in_srgb,var(--color-danger)_28%,transparent)]",
  info: "text-[var(--color-info)] bg-[var(--color-info-soft)] border-[color-mix(in_srgb,var(--color-info)_28%,transparent)]",
  neutral: "text-[var(--color-ink-2)] bg-[var(--color-surface-2)] border-[var(--color-line)]",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  dot = false,
  size = "md",
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  dot?: boolean;
  size?: "sm" | "md";
  title?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-medium",
        size === "sm" ? "px-2 py-0.5 text-[10.5px]" : "px-2.5 py-1 text-[11.5px]",
        TONE_CLASS[tone],
        className,
      )}
      title={title}
    >
      {dot ? <span className="size-1.5 rounded-full bg-current" /> : null}
      {children}
    </span>
  );
}

export function ScoreRing({
  value,
  size = 44,
  tone = "accent",
  label,
}: {
  value: number | null | undefined;
  size?: number;
  tone?: Tone;
  label?: string;
}) {
  const known = typeof value === "number" && Number.isFinite(value);
  const pct = known ? Math.max(0, Math.min(100, value)) : 0;
  const stroke = 3.5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const colour = `var(--color-${tone === "neutral" ? "ink-3" : tone})`;

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      title={known ? `${Math.round(pct)}%` : UNKNOWN}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth={stroke}
        />
        {known ? (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={colour}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - pct / 100)}
            style={{ transition: "stroke-dashoffset .6s cubic-bezier(.22,1,.36,1)" }}
          />
        ) : null}
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span
          className="num text-[12px] font-semibold"
          style={{ color: known ? colour : "var(--color-ink-4)" }}
        >
          {known ? Math.round(pct) : "?"}
        </span>
      </div>
      {label ? (
        <div className="mt-1 text-center text-[10px] text-[var(--color-ink-4)]">{label}</div>
      ) : null}
    </div>
  );
}

export function Meter({
  value,
  tone = "accent",
  className,
}: {
  value: number | null | undefined;
  tone?: Tone;
  className?: string;
}) {
  const known = typeof value === "number" && Number.isFinite(value);
  const pct = known ? Math.max(0, Math.min(100, value * 100)) : 0;
  return (
    <div className={cx("h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]", className)}>
      <div
        className="h-full rounded-full transition-[width] duration-500"
        style={{
          width: `${pct}%`,
          background: `var(--color-${tone === "neutral" ? "ink-4" : tone})`,
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Controls
 * ------------------------------------------------------------------ */
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, children, className, disabled, ...rest },
  ref,
) {
  const variants = {
    primary:
      "bg-[var(--color-accent)] text-white hover:brightness-110 border-transparent shadow-[0_1px_2px_rgba(0,0,0,.3)]",
    secondary:
      "bg-[var(--color-surface-2)] text-[var(--color-ink)] hover:bg-[var(--color-elevated)] border-[var(--color-line)]",
    ghost:
      "bg-transparent text-[var(--color-ink-2)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-ink)] border-transparent",
    danger:
      "bg-[var(--color-danger-soft)] text-[var(--color-danger)] hover:brightness-110 border-[color-mix(in_srgb,var(--color-danger)_30%,transparent)]",
  };
  const sizes = {
    sm: "h-8 px-3 text-[12.5px] gap-1.5 rounded-[8px]",
    md: "h-9 px-3.5 text-[13px] gap-2 rounded-[10px]",
    lg: "h-11 px-5 text-[14px] gap-2 rounded-[11px]",
  };
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center border font-medium transition-all",
        "focus-visible:focus-ring disabled:cursor-not-allowed disabled:opacity-45",
        "active:scale-[.98]",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export function Input({
  className,
  icon,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }) {
  return (
    <div className="relative flex-1">
      {icon ? (
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ink-4)]">
          {icon}
        </span>
      ) : null}
      <input
        className={cx(
          "h-9 w-full rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)]",
          "px-3 text-[13px] text-[var(--color-ink)] placeholder:text-[var(--color-ink-4)]",
          "transition-colors focus:border-[var(--color-accent-line)] focus:outline-none",
          icon && "pl-9",
          className,
        )}
        {...rest}
      />
    </div>
  );
}

export function Select({
  className,
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cx(
        "h-9 rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)]",
        "px-2.5 pr-7 text-[13px] text-[var(--color-ink)] transition-colors",
        "focus:border-[var(--color-accent-line)] focus:outline-none",
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: { key: string; label: string; count?: number }[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "inline-flex items-center gap-1 rounded-[11px] border border-[var(--color-line)] bg-[var(--color-surface-2)] p-1",
        className,
      )}
    >
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={cx(
            "rounded-[8px] px-3 py-1.5 text-[12.5px] font-medium transition-colors",
            active === tab.key
              ? "bg-[var(--color-elevated)] text-[var(--color-ink)] shadow-[0_1px_2px_rgba(0,0,0,.25)]"
              : "text-[var(--color-ink-3)] hover:text-[var(--color-ink-2)]",
          )}
        >
          {tab.label}
          {typeof tab.count === "number" ? (
            <span className="num ml-1.5 text-[var(--color-ink-4)]">{tab.count}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * States
 * ------------------------------------------------------------------ */
export function Skeleton({
  className,
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <div className={cx("skeleton", className)} style={style} />;
}

export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <Card>
      <Skeleton className="mb-4 h-3 w-28" />
      <div className="space-y-2.5">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" style={{ opacity: 1 - i * 0.12 }} />
        ))}
      </div>
    </Card>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={cx(
        "flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed",
        "border-[var(--color-line-strong)] text-center",
        compact ? "px-5 py-8" : "px-6 py-14",
      )}
    >
      {icon ? (
        <div className="mb-3.5 grid size-10 place-items-center rounded-[11px] border border-[var(--color-line)] bg-[var(--color-surface-2)] text-[var(--color-ink-3)]">
          {icon}
        </div>
      ) : null}
      <h3 className="text-[14px] font-medium">{title}</h3>
      {description ? (
        <p className="mt-1.5 max-w-md text-[12.5px] leading-relaxed text-[var(--color-ink-3)]">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: { message: string }; retry?: () => void }) {
  return (
    <EmptyState
      icon={<AlertCircle className="size-5 text-[var(--color-danger)]" />}
      title="That did not load"
      description={error.message}
      action={retry ? <Button onClick={retry}>Try again</Button> : undefined}
    />
  );
}

export function Note({
  children,
  tone = "info",
  icon,
}: {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}) {
  return (
    <div
      className={cx(
        "flex items-start gap-2.5 rounded-[11px] border px-3.5 py-2.5 text-[12.5px] leading-relaxed",
        TONE_CLASS[tone],
      )}
    >
      <span className="mt-0.5 shrink-0">{icon ?? <Info className="size-3.5" />}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** Renders a value, or an explicit "not known" — never a fabricated zero. */
export function Value({
  children,
  known,
  className,
  fallback = UNKNOWN,
}: {
  children: ReactNode;
  known: boolean;
  className?: string;
  fallback?: string;
}) {
  if (known) return <span className={className}>{children}</span>;
  return (
    <span
      className={cx("text-[12px] font-normal italic text-[var(--color-ink-4)]", className)}
      title="This metric cannot be computed from the data you have provided."
    >
      {fallback}
    </span>
  );
}

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        className={cx(
          "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden -translate-x-1/2",
          "whitespace-nowrap rounded-[8px] border border-[var(--color-line)] bg-[var(--color-elevated)]",
          "px-2.5 py-1.5 text-[11.5px] text-[var(--color-ink-2)] shadow-[var(--shadow-pop)]",
          "group-hover:block",
        )}
      >
        {label}
      </span>
    </span>
  );
}
