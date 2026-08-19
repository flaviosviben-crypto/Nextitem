"""Contact eligibility: who may be approached, on which channel, how often.

Compliance is invisible in the product and absolute underneath it. RevenueOS
must never tell an advisor to "WhatsApp this customer today" when that customer
has not agreed to WhatsApp — so eligibility is resolved *before* an opportunity
is written, not checked afterwards in the UI.

The output is deliberately binary for the advisor:

    Actionable   — an outreach channel is open, act now
    Suppressed   — do not reach out, with a plain reason (and whatever remains
                   possible, such as a conversation if they visit the boutique)

Everything here fails closed. Unknown consent is not consent; a missing phone
number is not a usable phone number; a customer contacted yesterday is not
contacted again today just because a new opportunity appeared.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Channels in the order an advisor should reach for them: the most personal
# outreach first, with the shop floor as the fallback that always remains open.
# Each names the consent flag that unlocks it and the contact detail it needs.
CHANNELS: tuple[dict[str, Any], ...] = (
    {"key": "phone", "label": "Phone", "consent_field": "phone_consent", "requires": "phone",
     "verb": "Call"},
    {"key": "whatsapp", "label": "WhatsApp", "consent_field": "whatsapp_consent",
     "requires": "phone", "verb": "Message on WhatsApp"},
    {"key": "email", "label": "Email", "consent_field": "email_consent", "requires": "email",
     "verb": "Email"},
    {"key": "sms", "label": "SMS", "consent_field": "sms_consent", "requires": "phone",
     "verb": "Text"},
    {"key": "in_store", "label": "In store", "consent_field": None, "requires": None,
     "verb": "Speak to them on their next visit"},
)

# How often the same customer may be approached. Frequency caps protect the
# relationship, which in premium retail is worth more than any single sale.
FREQUENCY_CAP_DAYS = 21

# In-store conversation is not outreach: an advisor greeting a client who walks
# in needs no marketing consent and is not rationed by the outreach cap.
_UNRESTRICTED = {"in_store"}


def _consent(profile: dict[str, Any], field: str | None) -> bool | None:
    """Channel consent, falling back to the general marketing flag.

    A specific "no" always wins over a general "yes": a customer who opted out of
    WhatsApp stays out of WhatsApp even with a newsletter consent on file.
    """
    if field is None:
        return True
    specific = profile.get(field)
    if specific is not None:
        return bool(specific)
    return profile.get("marketing_consent")


def _has_detail(profile: dict[str, Any], requires: str | None) -> bool:
    if requires is None:
        return True
    return bool(profile.get(requires))


def _days_since_contact(profile: dict[str, Any], as_of: date) -> int | None:
    last = profile.get("last_contacted_date") or profile.get("last_contacted_at")
    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last).date()
        except ValueError:
            return None
    if isinstance(last, datetime):
        last = last.date()
    if not isinstance(last, date):
        return None
    return (as_of - last).days


def evaluate(profile: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    """Resolve which channels are open for this customer, and why.

    Returns the eligibility record the opportunity engine attaches to every
    recommendation, so the action text can only ever name a permitted channel.
    """
    as_of = as_of or date.today()

    if profile.get("do_not_contact"):
        # A withdrawal of consent is absolute — not even the shop floor is offered
        # as a workaround.
        return _suppressed("This customer has asked not to be contacted.", "do_not_contact")

    channels: list[dict[str, Any]] = []
    blocked: list[str] = []
    for spec in CHANNELS:
        consent = _consent(profile, spec["consent_field"])
        if consent is False:
            blocked.append(f"No consent for {spec['label'].lower()}")
            continue
        if consent is None:
            blocked.append(f"Consent for {spec['label'].lower()} is not recorded")
            continue
        if not _has_detail(profile, spec["requires"]):
            blocked.append(f"No {spec['requires']} on file for {spec['label'].lower()}")
            continue
        channels.append({"key": spec["key"], "label": spec["label"], "verb": spec["verb"]})

    # Only outreach makes a customer *Actionable*. The shop floor is always open,
    # but "speak to them if they happen to walk in" is not something an advisor
    # can act on today, so it never counts as permission to reach out.
    outreach = [c for c in channels if c["key"] not in _UNRESTRICTED]
    in_store = [c for c in channels if c["key"] in _UNRESTRICTED]
    since = _days_since_contact(profile, as_of)

    if outreach and since is not None and since < FREQUENCY_CAP_DAYS:
        remaining = FREQUENCY_CAP_DAYS - since
        return _suppressed(
            f"Contacted {since} days ago — outreach paused for another {remaining} days "
            "to respect the frequency cap.",
            "frequency_cap", blocked, in_store, since)

    if not outreach:
        return _suppressed(
            blocked[0] if blocked else "No permitted outreach channel on file.",
            "no_channel", blocked, in_store, since)

    return {
        "status": "Actionable",
        "reason": None,
        "reason_code": None,
        "channels": outreach + in_store,
        "preferred_channel": outreach[0],
        "blocked": blocked,
        "days_since_contact": since,
    }


def _suppressed(reason: str, code: str, blocked: list[str] | None = None,
                fallback: list[dict[str, Any]] | None = None,
                since: int | None = None) -> dict[str, Any]:
    """Suppressed for outreach — with whatever remains possible stated plainly."""
    fallback = fallback or []
    if fallback:
        reason = f"{reason} You can still speak to them in the boutique."
    return {
        "status": "Suppressed",
        "reason": reason,
        "reason_code": code,
        "channels": fallback,
        "preferred_channel": None,
        "blocked": blocked or [],
        "days_since_contact": since,
    }


def apply(profiles: list[dict[str, Any]], as_of: date | None = None) -> list[dict[str, Any]]:
    """Attach an eligibility record to every profile."""
    for p in profiles:
        elig = evaluate(p, as_of)
        p["eligibility"] = elig
        p["contactable"] = elig["status"] == "Actionable"
        p["contact_channels"] = [c["label"] for c in elig["channels"]]
        p["suppression_reason"] = elig["reason"] if elig["status"] == "Suppressed" else None
    return profiles


def summarize(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts for the compliance panel — reassurance, not a dashboard."""
    actionable = sum(1 for p in profiles if p.get("contactable"))
    by_reason: dict[str, int] = {}
    for p in profiles:
        elig = p.get("eligibility") or {}
        if elig.get("status") == "Suppressed":
            code = elig.get("reason_code") or "unknown"
            by_reason[code] = by_reason.get(code, 0) + 1
    return {
        "actionable": actionable,
        "suppressed": len(profiles) - actionable,
        "suppressed_by_reason": by_reason,
        "frequency_cap_days": FREQUENCY_CAP_DAYS,
    }
