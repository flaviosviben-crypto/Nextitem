"""What to say, built from what RevenueOS already knows.

The advisor's real question after "who should I contact?" is "what do I say?".
This module answers it deterministically: every clause below is derived from a
field in the dataset, so a draft can be traced back to the record that produced
it. No discounts, no exclusivity, no events, no urgency the stock level does not
support — a boutique cannot retract a promise its software invented.

An LLM may rewrite the result for tone (see ``ai.analyst.polish_outreach``); it
is never required. Without a key the templates here are the product, not a
degraded mode, which is why they are written to be sent as they stand.

Two shapes come out of here:

    message   Something the advisor sends — WhatsApp, SMS, email.
    brief     Something the advisor reads before speaking — phone, in store.
              A scripted "message" for a phone call would be read aloud, and it
              would sound exactly like it was.
"""
from __future__ import annotations

from typing import Any

# Channels the advisor sends words through, as opposed to speaks them.
WRITTEN = {"whatsapp", "sms", "email"}
SPOKEN = {"phone", "in_store"}

# What a channel needs on file before RevenueOS may offer to open it. Absent the
# detail there is no action to offer — an "Open in WhatsApp" button that cannot
# work is worse than no button.
CONTACT_FIELD = {"whatsapp": "phone", "sms": "phone", "phone": "phone", "email": "email"}

# SMS is metered and read on a lock screen; keep it to the essential sentence.
SMS_MAX = 320


def first_name(full_name: str | None) -> str:
    """The name an advisor would actually use. Falls back to nothing, not to a
    placeholder — "Hi there" reads better than "Hi {first_name}"."""
    parts = (full_name or "").strip().split()
    return parts[0] if parts else ""


def _greeting(name: str) -> str:
    return f"Hi {name}" if name else "Hello"


def contact_detail(profile: dict[str, Any], channel: str) -> str | None:
    field = CONTACT_FIELD.get(channel)
    if not field:
        return None
    value = profile.get(field)
    return str(value).strip() or None if value else None


def _digits(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


def deep_link(channel: str, detail: str | None, subject: str | None, body: str) -> str | None:
    """A link the advisor's own device can open, with the draft already in it.

    This hands the conversation to the tool the advisor already uses; RevenueOS
    does not send anything itself, and nothing here records a contact.
    """
    if not detail:
        return None
    from urllib.parse import quote

    if channel == "whatsapp":
        number = _digits(detail)
        return f"https://wa.me/{number}?text={quote(body)}" if number else None
    if channel == "sms":
        return f"sms:{_digits(detail)}?&body={quote(body)}"
    if channel == "email":
        query = f"subject={quote(subject or '')}&body={quote(body)}"
        return f"mailto:{detail}?{query}"
    if channel == "phone":
        return f"tel:{_digits(detail)}"
    return None


# ----------------------------------------------------------------- clauses ---

def _product_clause(opp: dict[str, Any], trigger: str) -> str:
    product = opp.get("product") or {}
    name, brand = product.get("name"), product.get("brand")
    piece = f"the {name} from {brand}" if brand else f"the {name}"
    if trigger == "new_arrival":
        return f"{piece} has just come in and I thought of you"
    return f"{piece} came in and made me think of you"


def _affinity_clause(opp: dict[str, Any], profile: dict[str, Any]) -> str | None:
    """Why this piece, in the customer's own buying record.

    Uses the same signals the match was built from, so the sentence the customer
    reads and the evidence the advisor sees are the same fact.
    """
    product = opp.get("product") or {}
    category = product.get("category")
    share = (profile.get("category_affinity") or {}).get(category)
    if category and share and share >= 0.4:
        return f"it sits with the {category.lower()} you usually shop with us"
    brand = product.get("brand")
    if brand and (profile.get("brand_affinity") or {}).get(brand, 0) >= 0.15:
        return f"you have bought {brand} with us before"
    return None


def _size_clause(opp: dict[str, Any], profile: dict[str, Any]) -> str | None:
    """Only when the size is unambiguous for that family — a guessed size in a
    boutique message is the kind of error a client remembers."""
    product = opp.get("product") or {}
    family = (profile.get("size_affinity_by_family") or {}).get(product.get("category")) or {}
    if not family:
        return None
    size, share = max(family.items(), key=lambda kv: kv[1])
    if share < 0.6 or str(size).lower() in {"one size", "os", "unisize"}:
        return None
    return f"we have it in your usual {size}"


def _stock_clause(opp: dict[str, Any]) -> str | None:
    stock = (opp.get("product") or {}).get("stock")
    if stock is None:
        return None
    if stock <= 0:
        return None
    if stock == 1:
        return "there is one left in the boutique"
    # Not "we have it in": the size clause already opens that way, and the two
    # together read as a stock report rather than a note from a person.
    return "it is in the boutique now"


def _closing(channel: str) -> str:
    if channel == "email":
        return "If you would like to see it, I can put one aside for you."
    return "Happy to put one aside if you would like to see it."


# ------------------------------------------------------------------ shapes ---

def _sentences(opp: dict[str, Any], profile: dict[str, Any], channel: str) -> list[str]:
    trigger = opp.get("trigger") or ""
    name = first_name(opp.get("customer_name") or profile.get("name"))

    if not (opp.get("product") or {}).get("name"):
        # No product cleared the bar, or matching is unavailable for this
        # dataset. A genuine check-in reads better than a sentence built
        # around a piece that does not exist.
        return [
            f"{_greeting(name)} — I wanted to check in and see how you're doing.",
            "We have some new arrivals in store and I'd be happy to show you "
            "anything that might suit you.",
        ]

    size, stock = _size_clause(opp, profile), _stock_clause(opp)
    # "We have it in your usual L" already says it is here. Keep the stock line
    # only when it adds something — that the last one is on the floor.
    if size and stock and "one left" not in stock:
        stock = None
    supporting = [c for c in (_affinity_clause(opp, profile), size, stock) if c]
    lines = [f"{_greeting(name)} — {_product_clause(opp, trigger)}."]
    if supporting:
        # Two supporting facts is a personal note; four is a product listing.
        joined = ", and ".join([", ".join(supporting[:-1]), supporting[-1]]) \
            if len(supporting) > 2 else " and ".join(supporting)
        lines.append(f"{joined[0].upper()}{joined[1:]}.")
    lines.append(_closing(channel))
    return lines


def _subject(opp: dict[str, Any]) -> str:
    product = opp.get("product") or {}
    name, brand = product.get("name"), product.get("brand")
    if not name:
        return "Checking in"
    return f"{name} — {brand}" if brand else str(name)


def _call_brief(opp: dict[str, Any], profile: dict[str, Any]) -> str:
    """A natural opening for the advisor to have in mind — not a script to
    read aloud, and never the internal reasoning the card is built from.

    ``why_now``/``evidence`` explain the recommendation to the advisor on the
    card itself; none of that vocabulary (recency, cycle, segment, score)
    belongs in what they say or think about saying to the customer. This is
    advice about the conversation, phrased the way a manager would say it to
    the advisor in passing — "check in with Anna and mention X" — built from
    the same clean, customer-safe facts the written channels use.
    """
    name = first_name(opp.get("customer_name") or profile.get("name")) or "the customer"
    product = opp.get("product") or {}
    if not product.get("name"):
        return (f"Check in with {name} personally. Mention the new arrivals and offer "
                f"to show them a few pieces that may suit them.")

    piece = f"the {product['name']} from {product['brand']}" if product.get("brand") \
        else f"the {product['name']}"
    lead = f"Check in with {name} and mention {piece} — it just came in."

    supporting = [c for c in (_affinity_clause(opp, profile), _size_clause(opp, profile),
                              _stock_clause(opp)) if c]
    if supporting:
        fact = supporting[0]
        lead += f" {fact[0].upper()}{fact[1:]}."
    lead += " Offer to put one aside if they would like to see it."
    return lead


def _talking_points(opp: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    """Practical facts to have on hand — product, price, size, stock. Never
    the internal reason the card exists (see ``_call_brief`` for that)."""
    product = opp.get("product") or {}
    points: list[str] = []
    if product.get("name"):
        parts = [product["name"]]
        for extra in (product.get("brand"),
                      f"€{product['price']:,.0f}" if product.get("price") else None,
                      product.get("availability")):
            if extra:
                parts.append(str(extra))
        points.append(" · ".join(parts))
    for reason in (product.get("why") or [])[:2]:
        points.append(reason)
    size = _size_clause(opp, profile)
    if size:
        points.append(size[0].upper() + size[1:])
    for caveat in (product.get("caveats") or [])[:1]:
        points.append(f"Worth knowing: {caveat}")
    return points[:5]


def build(opp: dict[str, Any], profile: dict[str, Any], channel: str) -> dict[str, Any]:
    """A draft for one recommendation on one channel.

    Always returns something usable, including when the channel is not permitted
    — the advisor still needs to know why not, and the eligibility check that
    decides it lives in ``compliance``, not here.
    """
    profile = profile or {}
    detail = contact_detail(profile, channel)
    permitted = {c["key"] for c in (opp.get("eligibility") or {}).get("channels", [])}

    if channel in SPOKEN:
        body = ""
        draft: dict[str, Any] = {
            "kind": "brief",
            "subject": None,
            "body": None,
            # The natural opening — labelled "Suggested call brief" in the UI,
            # and what "Copy" copies. talking_points stays as reference facts
            # only; it is never what gets copied.
            "brief": _call_brief(opp, profile),
            "talking_points": _talking_points(opp, profile),
        }
    else:
        lines = _sentences(opp, profile, channel)
        body = "\n\n".join(lines) if channel == "email" else " ".join(lines)
        if channel == "sms" and len(body) > SMS_MAX:
            body = " ".join(lines[:1] + lines[-1:])
        if channel == "email":
            store = profile.get("store")
            body += "\n\n" + (f"— {store}" if store else "—")
        draft = {
            "kind": "message",
            "subject": _subject(opp) if channel == "email" else None,
            "body": body,
            "brief": None,
            "talking_points": [],
        }

    return {
        **draft,
        "channel": channel,
        "opportunity_id": opp.get("id"),
        "customer_id": opp.get("customer_id"),
        "customer_name": opp.get("customer_name"),
        "engine": "template",
        # Presence of the detail is reported, the detail itself is not: the
        # browser never needs a customer's phone number to show a draft, and
        # the deep link carries it only when the advisor asked to open one.
        "contact_available": bool(detail),
        "channel_permitted": channel in permitted,
        "deep_link": deep_link(channel, detail, draft.get("subject"), body),
        "facts_used": [c for c in (_affinity_clause(opp, profile),
                                   _size_clause(opp, profile),
                                   _stock_clause(opp)) if c],
    }
