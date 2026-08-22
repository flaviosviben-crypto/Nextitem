"use client";

/**
 * What to say, once the advisor has decided to say it.
 *
 * Approving used to change a status and leave the advisor to compose the
 * message themselves — the part of the job that actually earns the money. This
 * panel replaces the card in place: the recommendation has left the decision
 * inbox, and what stands where it was is the draft.
 *
 * Two shapes, because two kinds of channel:
 *   message  written, editable, copyable, openable in the advisor's own client
 *   brief    spoken — a call reads badly from a script, so phone and in-store
 *            get the facts to have in mind instead of words to recite
 *
 * Nothing here sends anything, and nothing here records a contact. Copying
 * text and opening WhatsApp are both things an advisor does *before* the
 * conversation; only "Mark as contacted" says one happened.
 */

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Sparkles } from "lucide-react";
import { api, type OutreachDraft } from "@/lib/api";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { money } from "@/lib/format";

const OPEN_LABEL: Record<string, string> = {
  whatsapp: "Open in WhatsApp",
  sms: "Open in Messages",
  email: "Open in email",
  phone: "Call",
};

export function OutreachPanel({
  opportunityId,
  customerName,
  onDone,
  onDismiss,
}: {
  opportunityId: string;
  customerName: string;
  /** Contact recorded — the caller takes the recommendation out of the list. */
  onDone: () => void;
  /** Advisor is done looking; the decision stands either way. */
  onDismiss: () => void;
}) {
  const [draft, setDraft] = useState<OutreachDraft | null>(null);
  const [channel, setChannel] = useState<string>("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (want: string) => {
      setLoading(true);
      setError(null);
      try {
        const next = await api.get<OutreachDraft>(
          `/outreach/${encodeURIComponent(opportunityId)}${want ? `?channel=${want}` : ""}`,
        );
        setDraft(next);
        setChannel(next.channel);
        setSubject(next.subject ?? "");
        setBody(next.body ?? "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not build a draft.");
      } finally {
        setLoading(false);
      }
    },
    [opportunityId],
  );

  useEffect(() => {
    load("");
  }, [load]);

  const copy = async () => {
    // The brief is the only thing "Copy" ever copies for a call — never the
    // internal facts list, and never the reasoning behind the recommendation.
    const text = draft?.kind === "brief"
      ? draft.brief || ""
      : [subject, body].filter(Boolean).join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Could not reach the clipboard — select the text and copy it.");
    }
  };

  /** The only thing that records a contact, and only a person can press it. */
  const markContacted = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await api.post(`/outreach/${encodeURIComponent(opportunityId)}/contacted`, {
        channel,
        // The wording actually used, not the wording suggested.
        message: draft?.kind === "message" ? [subject, body].filter(Boolean).join("\n\n") : null,
      });
      onDone();
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message} Nothing was recorded.`
          : "Could not record that contact. Nothing was recorded.",
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading && !draft) {
    return (
      <Card>
        <Skeleton className="h-32 w-full rounded-lg" />
      </Card>
    );
  }

  if (!draft) {
    return (
      <Card>
        <p className="text-[13px] text-[var(--critical)]">{error}</p>
        <Button size="sm" className="mt-3" onClick={() => load("")}>
          Try again
        </Button>
      </Card>
    );
  }

  const canOpen = draft.contact_available && !!draft.deep_link;

  return (
    <Card className="border-[color-mix(in_srgb,var(--accent)_35%,var(--line))]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-semibold">{customerName}</span>
            <Badge color="var(--good)">Ready to contact</Badge>
            {draft.engine === "claude" && (
              <span
                className="flex items-center gap-1 text-[11px] text-[var(--ink-3)]"
                title="Wording refined by Claude from the facts below. The facts themselves are computed."
              >
                <Sparkles size={11} /> tone refined
              </span>
            )}
          </div>
        </div>
        {draft.influenced_value !== null && (
          <div className="num shrink-0 text-[14px] font-semibold">
            {money(draft.influenced_value)}
          </div>
        )}
      </div>

      {/* Only channels this customer has consented to. An advisor cannot pick
          their way around the compliance check from here. */}
      {draft.channels.length > 1 && (
        <div className="mt-3.5 flex flex-wrap gap-1.5">
          {draft.channels.map((c) => (
            <button
              key={c.key}
              onClick={() => load(c.key)}
              className={
                c.key === channel
                  ? "rounded-full border border-[var(--accent)] px-2.5 py-1 text-[12px] text-[var(--ink)]"
                  : "rounded-full border border-[var(--line)] px-2.5 py-1 text-[12px] text-[var(--ink-2)] transition-colors hover:border-[var(--line-strong)]"
              }
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {draft.kind === "message" ? (
        <div className="mt-3.5 space-y-2">
          {draft.subject !== null && (
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Subject"
              className="w-full rounded-lg border border-[var(--line)] bg-[var(--raised)] px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]"
            />
          )}
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={draft.channel === "email" ? 7 : 4}
            className="w-full resize-y rounded-lg border border-[var(--line)] bg-[var(--raised)] px-3 py-2.5 text-[13.5px] leading-relaxed outline-none focus:border-[var(--accent)]"
          />
        </div>
      ) : (
        <div className="mt-3.5 rounded-lg bg-[var(--raised)] p-4">
          <div className="eyebrow mb-2">Suggested call brief</div>
          {/* What "Copy" copies — a natural opening, never the reasoning the
              recommendation is built from. */}
          <p className="text-[13.5px] leading-relaxed text-[var(--ink-2)]">{draft.brief}</p>
          {draft.talking_points.length > 0 && (
            <ul className="mt-3 space-y-1.5 border-t border-[var(--line)] pt-3">
              {draft.talking_points.map((point) => (
                <li key={point} className="text-[12px] leading-snug text-[var(--ink-3)]">
                  · {point}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!draft.contact_available && draft.kind === "message" && (
        <p className="mt-2 text-[12px] text-[var(--warning)]">
          No {draft.channel === "email" ? "email address" : "phone number"} on file — copy
          the text and send it from wherever you have their details.
        </p>
      )}

      {error && <p className="mt-2 text-[12px] text-[var(--critical)]">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-4">
        <Button size="sm" onClick={copy}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </Button>
        {/* Offered only when the detail needed to open it is actually on file. */}
        {canOpen && (
          <a href={draft.deep_link!} target="_blank" rel="noreferrer">
            <Button size="sm">
              <ExternalLink size={13} /> {OPEN_LABEL[draft.channel] ?? "Open"}
            </Button>
          </a>
        )}
        <Button variant="primary" size="sm" disabled={saving} onClick={markContacted}>
          {saving ? "Recording…" : "Mark as contacted"}
        </Button>
        <button
          onClick={onDismiss}
          className="text-[12.5px] text-[var(--ink-3)] transition-colors hover:text-[var(--ink)]"
        >
          Later
        </button>
      </div>

      <p className="mt-2.5 text-[11px] text-[var(--muted)]">
        RevenueOS does not send this for you. Copying or opening it changes nothing —
        only &ldquo;Mark as contacted&rdquo; records the outreach.
      </p>
    </Card>
  );
}

/**
 * A read-only look at what the advisor would say, before they have decided to
 * act on the card at all — "what do I say" answered at the moment it is
 * asked, not only after "Ready to contact" is clicked.
 *
 * Deliberately smaller than the full panel: no channel switcher, no editing,
 * no "Mark as contacted". Those stay behind the decision they follow, so this
 * preview cannot create a state the rest of the product does not expect.
 */
export function OutreachPreview({ opportunityId }: { opportunityId: string }) {
  const [draft, setDraft] = useState<OutreachDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<OutreachDraft>(`/outreach/${encodeURIComponent(opportunityId)}`)
      .then((next) => {
        if (!cancelled) setDraft(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not build a draft.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [opportunityId]);

  const copy = async () => {
    if (!draft) return;
    // The brief, never the internal facts list — same rule as the full panel.
    const text =
      draft.kind === "brief"
        ? draft.brief || ""
        : [draft.subject, draft.body].filter(Boolean).join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Could not reach the clipboard — select the text and copy it.");
    }
  };

  if (loading) {
    return <Skeleton className="h-20 w-full rounded-lg" />;
  }

  if (error || !draft) {
    return <p className="text-[12px] text-[var(--critical)]">{error || "Could not load a suggested message."}</p>;
  }

  return (
    <div className="rounded-lg bg-[var(--raised)] p-3.5">
      {draft.kind === "message" ? (
        <p className="whitespace-pre-line text-[13px] leading-relaxed text-[var(--ink-2)]">
          {[draft.subject, draft.body].filter(Boolean).join("\n\n")}
        </p>
      ) : (
        <p className="text-[13px] leading-relaxed text-[var(--ink-2)]">{draft.brief}</p>
      )}
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={copy}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </Button>
        {!draft.contact_available && draft.kind === "message" && (
          <span className="text-[11px] text-[var(--warning)]">
            No {draft.channel === "email" ? "email address" : "phone number"} on file
          </span>
        )}
      </div>
      {error && <p className="mt-2 text-[11px] text-[var(--critical)]">{error}</p>}
      <p className="mt-2 text-[10.5px] leading-snug text-[var(--muted)]">
        A preview on the {draft.channel === "in_store" ? "in-store" : draft.channel} channel.
        Nothing is recorded until the recommendation is marked as contacted.
      </p>
    </div>
  );
}
