"use client";

/**
 * The one question worth asking when an advisor says no.
 *
 * A rejection is the only decision carrying information the engine cannot
 * derive for itself: it is the boutique telling RevenueOS where it is wrong.
 * Discarding it was the cheapest data loss in the product.
 *
 * The cost of asking is one click on a five-item popover — a modal here would
 * be worse than not asking. Nothing is saved until a reason is chosen, and a
 * failed save leaves the popover open with the choice intact, so the advisor
 * never has to work out what they had already answered.
 */

import { useEffect, useRef, useState } from "react";
import { DECLINE_REASONS } from "@/lib/api";
import { Button } from "@/components/ui";

export type Decline = { reason: string; note?: string };

export function DeclineMenu({
  onDecline,
  onClose,
  align = "right",
}: {
  onDecline: (decline: Decline) => Promise<void>;
  onClose: () => void;
  align?: "left" | "right";
}) {
  const [reason, setReason] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) onClose();
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  const save = async (code: string, text?: string) => {
    if (saving) return;
    setSaving(true);
    try {
      await onDecline({ reason: code, note: text });
      onClose();
    } catch {
      /* the page shows the error; the choice stays on screen */
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      ref={box}
      className={`absolute z-20 mt-1.5 w-[230px] rounded-lg border border-[var(--line)] bg-[var(--surface)] p-1.5 shadow-lg ${
        align === "right" ? "right-0" : "left-0"
      }`}
    >
      <div className="px-2 py-1.5 text-[11.5px] text-[var(--ink-3)]">
        Why not this recommendation?
      </div>
      {DECLINE_REASONS.map((r) => (
        <button
          key={r.code}
          disabled={saving}
          onClick={() => (r.code === "other" ? setReason("other") : save(r.code))}
          className={
            (reason === r.code ? "bg-[var(--raised)] text-[var(--ink)] " : "text-[var(--ink-2)] ") +
            "block w-full rounded-md px-2 py-1.5 text-left text-[13px] transition-colors hover:bg-[var(--raised)] hover:text-[var(--ink)] disabled:opacity-50"
          }
        >
          {r.label}
        </button>
      ))}

      {/* Free text belongs to "Other" and nowhere else — a note box under every
          option invites an essay where a click would do. */}
      {reason === "other" && (
        <div className="mt-1 border-t border-[var(--line)] p-1.5 pt-2">
          <input
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && save("other", note.trim() || undefined)}
            placeholder="Optional — a few words"
            maxLength={140}
            className="w-full rounded-md border border-[var(--line)] bg-[var(--raised)] px-2 py-1.5 text-[12.5px] outline-none focus:border-[var(--accent)]"
          />
          <Button
            size="sm"
            variant="primary"
            disabled={saving}
            className="mt-1.5 w-full"
            onClick={() => save("other", note.trim() || undefined)}
          >
            {saving ? "Saving…" : "Set aside"}
          </Button>
        </div>
      )}
    </div>
  );
}

/** "Not now", with the reason picker attached. */
export function NotNowButton({
  disabled,
  onDecline,
}: {
  disabled?: boolean;
  onDecline: (decline: Decline) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <Button size="sm" disabled={disabled} onClick={() => setOpen((v) => !v)}>
        Not now
      </Button>
      {open && <DeclineMenu onDecline={onDecline} onClose={() => setOpen(false)} />}
    </div>
  );
}
