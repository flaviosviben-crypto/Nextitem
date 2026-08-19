"""Canonical RevenueOS schema: the fields we understand, in any language.

Aliases cover English, Italian, French, Spanish and German header conventions
plus the abbreviations POS exports habitually use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["customers", "transactions", "inventory"]
ValueType = Literal["id", "text", "email", "phone", "date", "number", "money", "bool", "category"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    value_type: ValueType
    aliases: tuple[str, ...] = ()
    # Fields that unlock major capability; used by the data-health explainer.
    importance: Literal["critical", "high", "medium", "low"] = "medium"
    unlocks: str = ""
    tags: tuple[str, ...] = field(default=())


def _f(*args, **kwargs) -> FieldSpec:
    return FieldSpec(*args, **kwargs)


CUSTOMER_FIELDS: tuple[FieldSpec, ...] = (
    _f("customer_id", "Customer ID", "id",
       ("customer id", "customerid", "cust id", "custid", "client id", "clientid", "id cliente",
        "cliente id", "idcliente", "codice cliente", "cod cliente", "customer code", "customer no",
        "customer number", "id", "kundennummer", "id client", "numero cliente"),
       "critical", "Links customers to their purchase history."),
    _f("name", "Customer Name", "text",
       ("name", "customer name", "client name", "full name", "fullname", "nome cliente",
        "nome completo", "nominativo", "ragione sociale", "cliente", "customer", "client",
        "nom client", "nombre cliente", "kunde"), "high", "Human-readable customer identity."),
    _f("first_name", "First Name", "text",
       ("first name", "firstname", "given name", "nome", "prenom", "prénom", "nombre", "vorname")),
    _f("last_name", "Last Name", "text",
       ("last name", "lastname", "surname", "family name", "cognome", "nom", "apellido", "nachname")),
    _f("email", "Email", "email",
       ("email", "e mail", "mail", "email address", "indirizzo email", "posta elettronica",
        "correo", "courriel"), "medium", "Enables outreach and duplicate detection."),
    _f("phone", "Phone", "phone",
       ("phone", "telephone", "tel", "mobile", "cell", "telefono", "cellulare", "numero telefono",
        "handy", "movil")),
    _f("gender", "Gender", "category",
       ("gender", "sex", "sesso", "genere", "genre", "sexo", "geschlecht"),
       "medium", "Filters product recommendations by gender fit."),
    _f("age", "Age", "number", ("age", "eta", "età", "edad", "alter")),
    _f("birth_date", "Birth Date", "date",
       ("birth date", "birthdate", "date of birth", "dob", "data di nascita", "data nascita",
        "nascita", "fecha nacimiento", "geburtsdatum")),
    _f("city", "City", "category",
       ("city", "town", "citta", "città", "comune", "localita", "località", "ville", "ciudad", "stadt")),
    _f("country", "Country", "category",
       ("country", "nation", "market", "paese", "nazione", "pays", "pais", "país", "land")),
    _f("store", "Preferred Store", "category",
       ("store", "shop", "boutique", "negozio", "punto vendita", "puntovendita", "preferred store",
        "store preferito", "magasin", "tienda", "filiale", "location", "sede"),
       "medium", "Enables store-level stock and staffing insight."),
    _f("total_spend", "Lifetime Spend", "money",
       ("total spend", "totalspend", "lifetime spend", "lifetime value", "ltv", "total revenue",
        "revenue", "totale speso", "spesa totale", "totale acquisti", "fatturato", "totale",
        "importo totale", "gesamtumsatz", "total gastado", "chiffre affaires"),
       "critical", "Drives value segmentation when transactions are absent."),
    _f("num_purchases", "Purchase Count", "number",
       ("num purchases", "number of purchases", "purchases", "orders", "order count", "n ordini",
        "numero ordini", "numero acquisti", "n acquisti", "acquisti", "frequency", "frequenza",
        "transactions count", "anzahl bestellungen", "pedidos"),
       "high", "Needed for frequency and repurchase-cadence analysis."),
    _f("avg_order_value", "Average Order Value", "money",
       ("avg order value", "average order value", "aov", "average basket", "scontrino medio",
        "ticket medio", "valore medio ordine", "panier moyen", "ticket promedio")),
    _f("last_purchase_date", "Last Purchase Date", "date",
       ("last purchase date", "last purchase", "last order date", "last order", "ultimo acquisto",
        "data ultimo acquisto", "ultima vendita", "derniere achat", "dernier achat",
        "ultima compra", "letzter kauf"),
       "critical", "Powers recency, churn risk and 'who is overdue' logic."),
    _f("first_purchase_date", "First Purchase Date", "date",
       ("first purchase date", "first purchase", "first order", "customer since", "primo acquisto",
        "data primo acquisto", "cliente dal", "data iscrizione", "signup date", "created at",
        "registration date", "data registrazione", "premier achat")),
    _f("preferred_category", "Preferred Category", "category",
       ("preferred category", "favorite category", "favourite category", "category", "categoria",
        "categoria preferita", "reparto", "famiglia", "categorie", "categoria favorita"),
       "high", "Primary signal for product matching."),
    _f("preferred_brand", "Preferred Brand", "category",
       ("preferred brand", "favorite brand", "brand", "marca", "marchio", "brand preferito",
        "marque", "hersteller"), "high", "Strong signal for product matching."),
    _f("size", "Size", "category",
       ("size", "taglia", "taille", "talla", "grosse", "größe", "clothing size", "size worn")),
    _f("color", "Preferred Color", "category",
       ("color", "colour", "colore", "couleur", "farbe", "preferred color", "colore preferito")),
    _f("discount_sensitivity", "Discount Sensitivity", "number",
       ("discount sensitivity", "discount rate", "sconto medio", "sensibilita sconto",
        "sensibilità sconto", "percentuale sconto", "avg discount")),
    _f("channel", "Channel", "category",
       ("channel", "canale", "source", "origine", "acquisition channel", "canal")),
    _f("segment", "Existing Segment", "category",
       ("segment", "segmento", "tier", "fascia", "customer segment", "segmento cliente",
        "cluster", "categoria cliente", "kundensegment")),
    _f("marketing_consent", "Marketing Consent", "bool",
       ("marketing consent", "consent", "opt in", "optin", "newsletter", "privacy",
        "consenso marketing", "consenso", "gdpr", "email consent", "accetta marketing"),
       "high", "Required before any outreach action is allowed."),
    _f("notes", "Notes", "text", ("notes", "note", "comment", "comments", "remarks", "osservazioni")),
)

TRANSACTION_FIELDS: tuple[FieldSpec, ...] = (
    _f("transaction_id", "Transaction ID", "id",
       ("transaction id", "transactionid", "order id", "orderid", "receipt", "receipt id",
        "invoice", "invoice id", "id transazione", "id ordine", "numero ordine", "scontrino",
        "documento", "ticket", "bon"), "high", "Groups lines into baskets for true AOV."),
    _f("customer_id", "Customer ID", "id",
       ("customer id", "customerid", "cust id", "client id", "clientid", "id cliente",
        "cliente id", "idcliente", "codice cliente", "customer", "cliente", "email",
        "customer email", "customer code"),
       "critical", "Without it, purchases cannot be attributed to people."),
    _f("date", "Transaction Date", "date",
       ("date", "transaction date", "order date", "purchase date", "sale date", "data",
        "data acquisto", "data ordine", "data vendita", "datum", "fecha"),
       "critical", "Drives recency, cadence, trend and seasonality."),
    _f("product_id", "Product ID", "id",
       ("product id", "productid", "item id", "id prodotto", "codice prodotto", "articolo id")),
    _f("sku", "SKU", "id",
       ("sku", "product sku", "item sku", "codice articolo", "cod articolo", "barcode", "ean",
        "reference", "ref", "articolo", "artikelnummer"),
       "high", "Links sales to catalogue items for SKU-level matching."),
    _f("product", "Product Name", "text",
       ("product", "product name", "item", "item name", "description", "descrizione",
        "prodotto", "nome prodotto", "articolo descrizione", "designation", "producto")),
    _f("category", "Category", "category",
       ("category", "product category", "categoria", "reparto", "department", "famiglia",
        "merceologia", "categorie", "kategorie"),
       "critical", "The strongest driver of product affinity."),
    _f("brand", "Brand", "category",
       ("brand", "marca", "marchio", "marque", "hersteller", "vendor", "fornitore brand"),
       "high", "Enables brand-loyalty recommendations."),
    _f("color", "Color", "category", ("color", "colour", "colore", "couleur", "farbe")),
    _f("size", "Size", "category", ("size", "taglia", "taille", "talla", "größe")),
    _f("quantity", "Quantity", "number",
       ("quantity", "qty", "qta", "q ta", "quantita", "quantità", "pezzi", "units", "cantidad",
        "menge", "nr pezzi")),
    _f("unit_price", "Unit Price", "money",
       ("unit price", "price", "prezzo", "prezzo unitario", "prix", "precio", "preis",
        "listino", "prezzo listino")),
    _f("discount", "Discount", "money",
       ("discount", "sconto", "rabatt", "descuento", "remise", "discount amount",
        "discount pct", "sconto percentuale", "percentuale sconto")),
    _f("line_total", "Line Total", "money",
       ("line total", "total", "amount", "net amount", "revenue", "final price", "totale",
        "importo", "totale riga", "netto", "ricavo", "imponibile", "total amount", "montant",
        "importe", "gesamt", "incasso", "venduto"),
       "critical", "The revenue figure every money metric is built on."),
    _f("store", "Store", "category",
       ("store", "shop", "boutique", "negozio", "punto vendita", "magasin", "tienda", "filiale")),
    _f("advisor", "Sales Advisor", "category",
       ("advisor", "sales advisor", "seller", "salesperson", "venditore", "commesso",
        "consulente", "vendeur", "operatore")),
)

INVENTORY_FIELDS: tuple[FieldSpec, ...] = (
    _f("product_id", "Product ID", "id",
       ("product id", "productid", "item id", "id prodotto", "id articolo", "codice")),
    _f("sku", "SKU", "id",
       ("sku", "product sku", "item sku", "codice articolo", "cod articolo", "barcode", "ean",
        "reference", "ref", "modello", "artikelnummer"),
       "critical", "The catalogue key everything else hangs off."),
    _f("product_name", "Product Name", "text",
       ("product name", "productname", "name", "item name", "product", "descrizione",
        "descrizione articolo", "nome prodotto", "prodotto", "articolo", "designation",
        "producto", "bezeichnung"),
       "critical", "Needed to present a recommendation a human understands."),
    _f("description", "Description", "text",
       ("description", "long description", "descrizione estesa", "dettaglio", "note prodotto")),
    _f("category", "Category", "category",
       ("category", "product category", "categoria", "reparto", "department", "famiglia",
        "merceologia", "linea", "kategorie", "categorie"),
       "critical", "Matching is category-first; without it matches get weak."),
    _f("subcategory", "Subcategory", "category",
       ("subcategory", "sub category", "sottocategoria", "sotto categoria", "tipologia",
        "product type", "type", "modello tipo")),
    _f("brand", "Brand", "category",
       ("brand", "marca", "marchio", "marque", "hersteller", "designer", "griffe"),
       "high", "Enables brand-affinity matching."),
    _f("gender", "Gender", "category",
       ("gender", "sex", "sesso", "genere", "target", "linea uomo donna", "genre", "sexo")),
    _f("price", "Retail Price", "money",
       ("price", "retail price", "selling price", "unit price", "prezzo", "prezzo vendita",
        "prezzo listino", "listino", "pvp", "prix", "precio", "preis", "rrp", "msrp"),
       "critical", "Price-band fit and inventory value both need it."),
    _f("original_price", "Original Price", "money",
       ("original price", "full price", "was price", "prezzo pieno", "prezzo originale",
        "prezzo intero", "list price", "prix initial")),
    _f("cost", "Cost", "money",
       ("cost", "cost price", "wholesale", "costo", "costo acquisto", "prezzo acquisto",
        "coste", "einkaufspreis")),
    _f("stock", "Stock On Hand", "number",
       ("stock", "quantity", "qty", "qta", "quantita", "quantità", "giacenza", "disponibilita",
        "disponibilità", "units", "on hand", "onhand", "inventory", "existencias", "bestand",
        "pezzi", "rimanenze"),
       "critical", "Availability gates every recommendation."),
    _f("size", "Size", "category", ("size", "taglia", "taille", "talla", "größe")),
    _f("color", "Color", "category", ("color", "colour", "colore", "couleur", "farbe", "tinta")),
    _f("season", "Season", "category",
       ("season", "stagione", "saison", "temporada", "saison collection")),
    _f("collection", "Collection", "category",
       ("collection", "collezione", "linea", "coleccion", "kollektion", "capsule")),
    _f("arrival_date", "Arrival Date", "date",
       ("arrival date", "arrival", "received", "date received", "data arrivo", "data carico",
        "data ingresso", "launch date", "data lancio", "in stock since", "eingang")),
    _f("supplier", "Supplier", "category",
       ("supplier", "vendor", "fornitore", "fournisseur", "proveedor", "lieferant")),
    _f("margin", "Margin", "number",
       ("margin", "margine", "markup", "ricarico", "marge", "margen", "profit")),
    _f("store", "Store", "category",
       ("store", "shop", "boutique", "negozio", "punto vendita", "magasin", "tienda", "filiale")),
)

SCHEMAS: dict[Kind, tuple[FieldSpec, ...]] = {
    "customers": CUSTOMER_FIELDS,
    "transactions": TRANSACTION_FIELDS,
    "inventory": INVENTORY_FIELDS,
}


def field_spec(kind: Kind, name: str) -> FieldSpec | None:
    for spec in SCHEMAS[kind]:
        if spec.name == name:
            return spec
    return None


def schema_payload(kind: Kind) -> list[dict[str, str]]:
    return [
        {
            "name": s.name,
            "label": s.label,
            "value_type": s.value_type,
            "importance": s.importance,
            "unlocks": s.unlocks,
        }
        for s in SCHEMAS[kind]
    ]
