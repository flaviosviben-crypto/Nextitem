"""The canonical RevenueOS data model and its multilingual alias registry.

Every boutique exports its data differently. Rather than demanding a fixed
template, RevenueOS declares what it *understands* and maps whatever arrives
onto that model. Each field carries:

``aliases``   exact header names seen in the wild (EN/IT/FR/ES/DE)
``tokens``    individual words that hint at this field
``kind``      value archetype, used to score the actual cell contents
``required``  whether the entity is unusable without it
``unlocks``   the capabilities that become available when the field is present
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    ID = "id"
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    DATE = "date"
    NUMBER = "number"
    CURRENCY = "currency"
    INTEGER = "integer"
    CATEGORY = "category"
    LIST = "list"
    PERCENT = "percent"


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: Kind
    aliases: tuple[str, ...] = ()
    tokens: tuple[str, ...] = ()
    required: bool = False
    description: str = ""
    unlocks: tuple[str, ...] = ()

    @property
    def is_numeric(self) -> bool:
        return self.kind in {Kind.NUMBER, Kind.CURRENCY, Kind.INTEGER, Kind.PERCENT}


@dataclass(frozen=True)
class Entity:
    name: str
    label: str
    fields: tuple[Field, ...]
    description: str = ""
    # headers that strongly indicate this entity even before field mapping
    signature_tokens: tuple[str, ...] = ()

    def field_map(self) -> dict[str, Field]:
        return {f.name: f for f in self.fields}

    def required_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.required)


# --------------------------------------------------------------------------- #
# shared alias fragments
# --------------------------------------------------------------------------- #
_CUSTOMER_WORDS = ("customer", "client", "cliente", "clienti", "kunde", "cust",
                   "acquirente", "buyer", "contact", "contatto", "member", "socio")
_PRODUCT_WORDS = ("product", "prodotto", "article", "articolo", "item", "artikel",
                  "produit", "producto", "sku", "style", "modello", "model")

CUSTOMERS = Entity(
    name="customers",
    label="Customers",
    description="Your CRM: one row per customer.",
    signature_tokens=("customer", "cliente", "client", "crm", "anagrafica", "contatti"),
    fields=(
        Field("customer_id", "Customer ID", Kind.ID, required=True,
              aliases=("customer_id", "customerid", "cust_id", "id_cliente", "codice cliente",
                       "cliente_id", "client_id", "id cliente", "customer number", "customer code",
                       "codice_cliente", "cod cliente", "id", "crm id", "customer key",
                       "kundennummer", "n cliente", "numero cliente", "card number", "tessera"),
              tokens=_CUSTOMER_WORDS + ("id", "code", "codice", "number", "numero", "key"),
              description="Unique identifier used to join customers to transactions.",
              unlocks=("customer analytics", "transaction joins", "matching")),
        Field("first_name", "First Name", Kind.TEXT,
              aliases=("first_name", "firstname", "name", "nome", "prenom", "prénom",
                       "vorname", "nombre", "given name", "nome cliente", "first"),
              tokens=("first", "nome", "name", "given", "prenom", "vorname")),
        Field("last_name", "Last Name", Kind.TEXT,
              aliases=("last_name", "lastname", "surname", "cognome", "nom", "nachname",
                       "apellido", "family name", "second name", "last"),
              tokens=("last", "surname", "cognome", "family", "nachname", "apellido")),
        Field("full_name", "Full Name", Kind.TEXT,
              aliases=("full_name", "fullname", "customer name", "nome completo",
                       "nome e cognome", "nominativo", "ragione sociale", "name and surname",
                       "cliente", "client name", "nome cliente", "denominazione"),
              tokens=("full", "completo", "nominativo", "denominazione"),
              description="Used when first/last name are not stored separately."),
        Field("email", "Email", Kind.EMAIL,
              aliases=("email", "e-mail", "mail", "email address", "indirizzo email",
                       "posta elettronica", "correo", "courriel", "e_mail"),
              tokens=("email", "mail", "posta", "correo", "courriel"),
              unlocks=("email campaigns",)),
        Field("phone", "Phone", Kind.PHONE,
              aliases=("phone", "telefono", "tel", "mobile", "cellulare", "cell",
                       "phone number", "numero telefono", "whatsapp", "telephone", "handy"),
              tokens=("phone", "telefono", "mobile", "cellulare", "tel", "whatsapp"),
              unlocks=("WhatsApp / SMS outreach",)),
        Field("gender", "Gender", Kind.CATEGORY,
              aliases=("gender", "sesso", "sex", "genere", "geschlecht", "sexo"),
              tokens=("gender", "sesso", "genere", "sex"),
              unlocks=("gender-aware product matching",)),
        Field("birth_date", "Birth Date", Kind.DATE,
              aliases=("birth_date", "birthdate", "date of birth", "dob", "data di nascita",
                       "nascita", "geburtsdatum", "compleanno", "birthday"),
              tokens=("birth", "nascita", "dob", "geburt", "compleanno")),
        Field("age", "Age", Kind.INTEGER,
              aliases=("age", "eta", "età", "alter", "edad", "age range", "fascia eta"),
              tokens=("age", "eta", "alter", "edad")),
        Field("city", "City", Kind.CATEGORY,
              aliases=("city", "citta", "città", "comune", "ville", "stadt", "ciudad", "town"),
              tokens=("city", "citta", "comune", "ville", "stadt", "town")),
        Field("country", "Country", Kind.CATEGORY,
              aliases=("country", "paese", "nazione", "nation", "land", "pais", "país"),
              tokens=("country", "paese", "nazione", "land", "pais")),
        Field("store", "Preferred Store", Kind.CATEGORY,
              aliases=("store", "negozio", "boutique", "shop", "punto vendita", "pdv",
                       "preferred store", "negozio preferito", "filiale", "location", "branch"),
              tokens=("store", "negozio", "boutique", "shop", "pdv", "filiale", "branch")),
        Field("total_spend", "Lifetime Spend", Kind.CURRENCY,
              aliases=("total_spend", "totale", "total", "lifetime value", "ltv", "spesa totale",
                       "totale speso", "total spent", "revenue", "fatturato", "valore cliente",
                       "importo totale", "gesamtumsatz", "total purchases value", "spend"),
              tokens=("total", "totale", "spend", "spesa", "ltv", "lifetime", "fatturato",
                      "revenue", "importo", "umsatz"),
              description="Historical spend. Recomputed from transactions when available.",
              unlocks=("value segmentation", "RFM monetary axis")),
        Field("order_count", "Number of Purchases", Kind.INTEGER,
              aliases=("order_count", "orders", "num_orders", "n ordini", "numero acquisti",
                       "acquisti", "purchases", "number of purchases", "transactions",
                       "n_transazioni", "visite", "frequency", "frequenza", "anzahl bestellungen"),
              tokens=("order", "ordini", "purchase", "acquisti", "count", "numero",
                      "frequency", "frequenza", "transactions"),
              unlocks=("RFM frequency axis",)),
        Field("avg_order_value", "Average Order Value", Kind.CURRENCY,
              aliases=("avg_order_value", "aov", "scontrino medio", "valore medio",
                       "average order value", "average basket", "ticket medio",
                       "media acquisto", "durchschnittsbon"),
              tokens=("avg", "average", "medio", "media", "aov", "basket", "scontrino", "ticket")),
        Field("last_purchase_date", "Last Purchase Date", Kind.DATE,
              aliases=("last_purchase_date", "last purchase", "ultimo acquisto", "last order",
                       "ultima visita", "last visit", "data ultimo acquisto", "last_order_date",
                       "letzter kauf", "derniere visite", "ultima compra", "last transaction"),
              tokens=("last", "ultimo", "ultima", "letzter", "derniere", "recent", "recente"),
              unlocks=("RFM recency axis", "churn risk", "reactivation")),
        Field("first_purchase_date", "First Purchase Date", Kind.DATE,
              aliases=("first_purchase_date", "first purchase", "primo acquisto", "signup date",
                       "data registrazione", "customer since", "cliente dal", "created at",
                       "registration date", "data iscrizione", "erster kauf"),
              tokens=("first", "primo", "since", "signup", "registration", "created",
                      "iscrizione", "erster"),
              unlocks=("tenure", "loyalty tracking")),
        Field("preferred_categories", "Preferred Categories", Kind.LIST,
              aliases=("preferred_categories", "categorie preferite", "categories",
                       "categoria preferita", "favourite categories", "interests", "interessi"),
              tokens=("preferred", "preferite", "favourite", "categories", "categorie",
                      "interests")),
        Field("preferred_brands", "Preferred Brands", Kind.LIST,
              aliases=("preferred_brands", "brand preferiti", "brands", "marche preferite",
                       "favourite brands", "marchi", "designer"),
              tokens=("brand", "marca", "marche", "marchi", "designer", "label")),
        Field("sizes", "Sizes", Kind.LIST,
              aliases=("sizes", "size", "taglia", "taglie", "taille", "größe", "talla",
                       "clothing size", "dress size"),
              tokens=("size", "taglia", "taglie", "taille", "grosse", "talla"),
              unlocks=("size-aware recommendations",)),
        Field("colors", "Colors", Kind.LIST,
              aliases=("colors", "colours", "colore", "colori", "couleur", "farbe", "color"),
              tokens=("color", "colour", "colore", "colori", "couleur", "farbe")),
        Field("discount_sensitivity", "Discount Sensitivity", Kind.PERCENT,
              aliases=("discount_sensitivity", "sensibilita sconto", "discount affinity",
                       "promo sensitivity", "sconto medio", "avg discount"),
              tokens=("discount", "sconto", "promo", "sensitivity", "sensibilita")),
        Field("channel", "Channel", Kind.CATEGORY,
              aliases=("channel", "canale", "source", "provenienza", "acquisition channel",
                       "kanal", "origine")),
        Field("consent", "Marketing Consent", Kind.CATEGORY,
              aliases=("consent", "consenso", "marketing consent", "privacy", "gdpr",
                       "opt in", "optin", "newsletter", "marketing_opt_in"),
              tokens=("consent", "consenso", "optin", "gdpr", "privacy", "newsletter"),
              unlocks=("compliant outreach lists",)),
        Field("notes", "Notes", Kind.TEXT,
              aliases=("notes", "note", "commenti", "comments", "remarks", "osservazioni",
                       "bemerkungen")),
    ),
)

TRANSACTIONS = Entity(
    name="transactions",
    label="Transactions",
    description="One row per sold line item (or per order).",
    signature_tokens=("transaction", "order", "sale", "vendita", "scontrino", "ordine",
                      "receipt", "fattura", "invoice"),
    fields=(
        Field("transaction_id", "Transaction ID", Kind.ID,
              aliases=("transaction_id", "order_id", "id_ordine", "numero ordine", "receipt",
                       "scontrino", "id transazione", "invoice", "fattura", "documento",
                       "ticket", "sale_id", "bill", "order number"),
              tokens=("transaction", "order", "ordine", "receipt", "scontrino", "invoice",
                      "fattura", "sale", "ticket", "documento")),
        Field("customer_id", "Customer ID", Kind.ID, required=True,
              aliases=("customer_id", "cust_id", "id_cliente", "cliente", "client_id",
                       "codice cliente", "customer", "customer code", "card number", "tessera"),
              tokens=_CUSTOMER_WORDS + ("id", "codice", "code"),
              description="Links the sale back to a customer.",
              unlocks=("purchase history", "affinity profiles", "true RFM")),
        Field("date", "Transaction Date", Kind.DATE, required=True,
              aliases=("date", "data", "transaction_date", "order_date", "data ordine",
                       "data vendita", "purchase date", "datum", "fecha", "data acquisto",
                       "sale date", "timestamp", "created at"),
              tokens=("date", "data", "datum", "fecha", "timestamp", "when"),
              unlocks=("trends", "recency", "seasonality", "sell-through")),
        Field("product_id", "Product ID", Kind.ID,
              aliases=("product_id", "id_prodotto", "articolo", "item_id", "codice articolo",
                       "codice prodotto", "product code", "artikelnummer", "id articolo"),
              tokens=_PRODUCT_WORDS + ("id", "code", "codice"),
              unlocks=("product affinity", "product-level matching")),
        Field("sku", "SKU", Kind.ID,
              aliases=("sku", "barcode", "ean", "codice a barre", "upc", "reference", "ref",
                       "codice sku", "style code"),
              tokens=("sku", "barcode", "ean", "upc", "reference", "ref")),
        Field("product_name", "Product Name", Kind.TEXT,
              aliases=("product_name", "descrizione", "description", "product", "articolo",
                       "nome prodotto", "item name", "descrizione articolo", "bezeichnung"),
              tokens=("product", "prodotto", "descrizione", "description", "name", "articolo")),
        Field("quantity", "Quantity", Kind.INTEGER,
              aliases=("quantity", "qty", "quantita", "quantità", "pezzi", "pcs", "units",
                       "menge", "cantidad", "qta", "q.ta", "n pezzi"),
              tokens=("quantity", "qty", "quantita", "pezzi", "units", "menge", "pcs")),
        Field("unit_price", "Unit Price", Kind.CURRENCY,
              aliases=("unit_price", "price", "prezzo", "prezzo unitario", "listino",
                       "prix", "preis", "precio", "prezzo di listino", "gross price"),
              tokens=("price", "prezzo", "prix", "preis", "precio", "unit", "listino")),
        Field("discount", "Discount", Kind.NUMBER,
              aliases=("discount", "sconto", "rabatt", "descuento", "remise", "discount_pct",
                       "percentuale sconto", "discount amount", "sconto %", "promo"),
              tokens=("discount", "sconto", "rabatt", "remise", "descuento", "promo"),
              unlocks=("discount sensitivity", "margin analysis")),
        Field("net_amount", "Line Total", Kind.CURRENCY, required=True,
              aliases=("net_amount", "final price", "total", "totale", "importo", "amount",
                       "totale riga", "net", "netto", "revenue", "line total", "valore",
                       "prezzo finale", "totale netto", "gesamt", "importo netto", "paid"),
              tokens=("total", "totale", "amount", "importo", "net", "netto", "final",
                      "finale", "revenue", "paid", "valore"),
              description="Actual money taken for this line.",
              unlocks=("revenue analytics", "monetary value", "sell-through")),
        Field("category", "Category", Kind.CATEGORY,
              aliases=("category", "categoria", "kategorie", "categorie", "product category",
                       "famiglia", "family", "reparto", "department", "linea"),
              tokens=("category", "categoria", "family", "famiglia", "department", "reparto"),
              unlocks=("category affinity", "category performance")),
        Field("brand", "Brand", Kind.CATEGORY,
              aliases=("brand", "marca", "marchio", "designer", "label", "fornitore brand",
                       "maison", "griffe"),
              tokens=("brand", "marca", "marchio", "designer", "label", "maison"),
              unlocks=("brand affinity",)),
        Field("color", "Color", Kind.CATEGORY,
              aliases=("color", "colour", "colore", "couleur", "farbe", "colore articolo"),
              tokens=("color", "colour", "colore", "couleur", "farbe")),
        Field("size", "Size", Kind.CATEGORY,
              aliases=("size", "taglia", "taille", "größe", "talla", "misura"),
              tokens=("size", "taglia", "taille", "grosse", "talla", "misura")),
        Field("store", "Store", Kind.CATEGORY,
              aliases=("store", "negozio", "boutique", "punto vendita", "pdv", "shop",
                       "filiale", "location")),
        Field("channel", "Channel", Kind.CATEGORY,
              aliases=("channel", "canale", "sales channel", "online offline", "kanal")),
    ),
)

INVENTORY = Entity(
    name="inventory",
    label="Inventory",
    description="Your product catalogue and current stock.",
    signature_tokens=("inventory", "stock", "product", "catalog", "catalogo", "giacenza",
                      "magazzino", "articoli", "listino"),
    fields=(
        Field("product_id", "Product ID", Kind.ID, required=True,
              aliases=("product_id", "id_prodotto", "codice articolo", "item_id", "id",
                       "codice prodotto", "product code", "artikelnummer", "id articolo",
                       "modello", "style"),
              tokens=_PRODUCT_WORDS + ("id", "code", "codice"),
              unlocks=("catalogue joins", "product recommendations")),
        Field("sku", "SKU", Kind.ID,
              aliases=("sku", "barcode", "ean", "upc", "reference", "ref", "codice a barre",
                       "style code", "variant"),
              tokens=("sku", "barcode", "ean", "upc", "reference")),
        Field("product_name", "Product Name", Kind.TEXT, required=True,
              aliases=("product_name", "name", "nome", "descrizione", "description",
                       "articolo", "nome prodotto", "item name", "bezeichnung", "titolo",
                       "product", "denominazione"),
              tokens=("name", "nome", "product", "prodotto", "descrizione", "description",
                      "articolo", "titolo")),
        Field("description", "Description", Kind.TEXT,
              aliases=("description", "descrizione lunga", "long description", "details",
                       "dettagli", "note prodotto", "composizione")),
        Field("category", "Category", Kind.CATEGORY,
              aliases=("category", "categoria", "kategorie", "famiglia", "family", "reparto",
                       "department", "product category", "linea", "macro categoria"),
              tokens=("category", "categoria", "family", "famiglia", "department", "reparto"),
              unlocks=("category affinity matching", "category mix")),
        Field("subcategory", "Subcategory", Kind.CATEGORY,
              aliases=("subcategory", "sottocategoria", "sub category", "type", "tipologia",
                       "micro categoria", "sub-family")),
        Field("brand", "Brand", Kind.CATEGORY,
              aliases=("brand", "marca", "marchio", "designer", "label", "maison", "griffe",
                       "vendor brand"),
              tokens=("brand", "marca", "marchio", "designer", "label"),
              unlocks=("brand affinity matching",)),
        Field("gender", "Gender", Kind.CATEGORY,
              aliases=("gender", "sesso", "genere", "target", "sex", "linea uomo donna",
                       "geschlecht", "for")),
        Field("price", "Retail Price", Kind.CURRENCY, required=True,
              aliases=("price", "prezzo", "retail price", "prezzo vendita", "selling price",
                       "listino", "prezzo listino", "preis", "precio", "prix", "rrp",
                       "prezzo attuale", "current price"),
              tokens=("price", "prezzo", "retail", "listino", "preis", "prix", "precio"),
              unlocks=("price affinity matching", "inventory value")),
        Field("original_price", "Original Price", Kind.CURRENCY,
              aliases=("original_price", "prezzo originale", "full price", "was price",
                       "prezzo pieno", "list price", "prezzo intero", "msrp"),
              tokens=("original", "originale", "full", "pieno", "msrp", "was")),
        Field("cost", "Cost", Kind.CURRENCY,
              aliases=("cost", "costo", "cost price", "prezzo acquisto", "wholesale",
                       "einkaufspreis", "purchase price", "costo acquisto", "cogs"),
              tokens=("cost", "costo", "wholesale", "cogs", "acquisto"),
              unlocks=("margin analysis", "margin-aware prioritisation")),
        Field("stock", "Stock on Hand", Kind.INTEGER, required=True,
              aliases=("stock", "giacenza", "quantita", "quantità", "qty", "available",
                       "disponibilita", "disponibilità", "on hand", "inventory", "bestand",
                       "stock quantity", "pezzi disponibili", "units"),
              tokens=("stock", "giacenza", "available", "disponibil", "hand", "bestand",
                      "inventory", "qty", "quantita"),
              unlocks=("dead stock detection", "availability filtering")),
        Field("size", "Size", Kind.CATEGORY,
              aliases=("size", "taglia", "taille", "größe", "talla", "misura"),
              tokens=("size", "taglia", "taille", "misura"),
              unlocks=("size compatibility",)),
        Field("color", "Color", Kind.CATEGORY,
              aliases=("color", "colour", "colore", "couleur", "farbe", "colore principale"),
              tokens=("color", "colour", "colore", "couleur", "farbe"),
              unlocks=("colour affinity",)),
        Field("season", "Season", Kind.CATEGORY,
              aliases=("season", "stagione", "saison", "temporada", "collection season",
                       "fw", "ss")),
        Field("collection", "Collection", Kind.CATEGORY,
              aliases=("collection", "collezione", "kollektion", "line", "capsule",
                       "drop", "coleccion")),
        Field("arrival_date", "Arrival Date", Kind.DATE,
              aliases=("arrival_date", "data arrivo", "received", "data carico", "intake date",
                       "date received", "in stock since", "wareneingang", "data ingresso",
                       "created at", "first received"),
              tokens=("arrival", "arrivo", "received", "carico", "intake", "ingresso"),
              unlocks=("stock ageing", "dead stock risk")),
        Field("supplier", "Supplier", Kind.CATEGORY,
              aliases=("supplier", "fornitore", "vendor", "lieferant", "proveedor")),
        Field("margin", "Margin", Kind.PERCENT,
              aliases=("margin", "margine", "markup", "marge", "gross margin",
                       "margine lordo", "margin %")),
    ),
)

ENTITIES: dict[str, Entity] = {
    CUSTOMERS.name: CUSTOMERS,
    TRANSACTIONS.name: TRANSACTIONS,
    INVENTORY.name: INVENTORY,
}


def entity(name: str) -> Entity:
    try:
        return ENTITIES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown entity '{name}'. Expected one of {list(ENTITIES)}.") from exc


def schema_catalogue() -> dict:
    """Serialisable description of the model, used by the mapping UI."""
    return {
        name: {
            "label": ent.label,
            "description": ent.description,
            "fields": [
                {
                    "name": f.name,
                    "label": f.label,
                    "kind": f.kind.value,
                    "required": f.required,
                    "description": f.description,
                    "unlocks": list(f.unlocks),
                }
                for f in ent.fields
            ],
        }
        for name, ent in ENTITIES.items()
    }
