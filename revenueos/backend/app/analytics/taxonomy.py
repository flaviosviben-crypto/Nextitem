"""Fashion taxonomy: group free-text categories into comparable families.

Boutique exports write the same thing a dozen ways ("Borse", "Bags", "Pelletteria",
"Leather Goods"). Grouping them means a customer who buys handbags is matched to
a catalogue that files them under a different word.
"""
from __future__ import annotations

import re
import unicodedata

FAMILIES: dict[str, tuple[str, ...]] = {
    "Leather Goods": ("leather goods", "leathergoods", "pelletteria", "borse", "borsa", "bags",
                      "bag", "handbag", "handbags", "tote", "crossbody", "clutch", "shoulder bag",
                      "wallet", "wallets", "portafogli", "portafoglio", "maroquinerie", "bolsos",
                      "backpack", "zaino", "zaini", "pochette", "marsupio"),
    "Shoes": ("shoes", "shoe", "footwear", "calzature", "scarpe", "scarpa", "loafer", "loafers",
              "sneakers", "sneaker", "boots", "boot", "stivali", "stivaletti", "sandals", "sandali",
              "heels", "decollete", "pumps", "mocassini", "ballerine", "chaussures", "zapatos"),
    "Ready-to-Wear": ("ready to wear", "readytowear", "rtw", "abbigliamento", "clothing", "apparel",
                      "maglieria", "knitwear", "knit", "denim", "jeans", "tailoring", "sartoria",
                      "abiti", "abito", "dress", "dresses", "vestiti", "suits", "giacche", "jacket",
                      "jackets", "capispalla", "outerwear", "coat", "coats", "cappotti", "trench",
                      "shirts", "camicie", "camicia", "blouse", "bluse", "trousers", "pantaloni",
                      "skirts", "gonne", "gonna", "top", "tops", "felpe", "sweater", "maglioni",
                      "cardigan", "blazer", "pret a porter", "vetements", "ropa", "t shirt",
                      "tshirt", "polo", "gilet", "piumini", "puffer"),
    "Accessories": ("accessories", "accessory", "accessori", "accessorio", "belts", "belt",
                    "cinture", "cintura", "scarves", "scarf", "sciarpe", "foulard", "hats", "hat",
                    "cappelli", "gloves", "guanti", "jewelry", "jewellery", "gioielli", "bijoux",
                    "sunglasses", "occhiali", "eyewear", "ties", "cravatte", "socks", "calze",
                    "hair accessories", "complementos"),
    "Travel": ("travel", "viaggio", "luggage", "bagagli", "suitcase", "valigie", "valigia",
               "trolley", "weekender", "duffle", "garment bag"),
    "Beauty": ("beauty", "cosmetics", "cosmetica", "profumi", "profumo", "fragrance", "fragrances",
               "parfum", "perfume", "skincare", "make up", "makeup", "trucco"),
    "Home": ("home", "casa", "lifestyle", "candles", "candele", "textiles", "arredo", "deco"),
}

_TOKEN_INDEX: dict[str, str] = {}
for _family, _terms in FAMILIES.items():
    for _t in _terms:
        _TOKEN_INDEX[_t.replace(" ", "")] = _family
    _TOKEN_INDEX[_family.lower().replace(" ", "").replace("-", "")] = _family


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def family_of(value: object) -> str | None:
    """Map a free-text category to a known fashion family, or ``None``."""
    key = _norm(value)
    if not key or key in {"uncategorized", "na", "none", "altro", "other", "varie"}:
        return None
    if key in _TOKEN_INDEX:
        return _TOKEN_INDEX[key]
    # Longest known term contained in the label wins ("borse donna" -> Leather Goods).
    best: tuple[int, str] | None = None
    for term, family in _TOKEN_INDEX.items():
        if len(term) >= 4 and term in key:
            if best is None or len(term) > best[0]:
                best = (len(term), family)
    return best[1] if best else None


def compatibility(a: object, b: object) -> float:
    """How interchangeable are two category labels? 0 (unrelated) to 1 (same)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    fa, fb = family_of(a), family_of(b)
    if fa and fb and fa == fb:
        return 0.9
    if na in nb or nb in na:
        return 0.75
    if fa and fb and fa != fb:
        return _cross_family(fa, fb)
    return 0.0


# Categories a customer plausibly buys together — used for cross-sell, never as
# a substitute for a genuine category match.
_ADJACENT = {
    frozenset({"Leather Goods", "Accessories"}): 0.45,
    frozenset({"Leather Goods", "Travel"}): 0.5,
    frozenset({"Ready-to-Wear", "Accessories"}): 0.4,
    frozenset({"Ready-to-Wear", "Shoes"}): 0.38,
    frozenset({"Shoes", "Accessories"}): 0.35,
    frozenset({"Shoes", "Leather Goods"}): 0.35,
    frozenset({"Accessories", "Beauty"}): 0.25,
}


def _cross_family(a: str, b: str) -> float:
    return _ADJACENT.get(frozenset({a, b}), 0.0)


def describe(value: object) -> str:
    """Human label for a category, falling back to the raw text."""
    fam = family_of(value)
    raw = str(value or "").strip()
    if fam and _norm(fam) != _norm(raw):
        return f"{raw or fam} ({fam})"
    return raw or (fam or "Uncategorised")
