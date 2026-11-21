import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_BYTES = 5_000_000
MAX_ROWS = 5_000
CATEGORIES = {
    "office": ("office supplies", "stationery", "printer", "paper", "办公用品", "文具", "打印纸"),
    "software": ("software", "subscription", "hosting", "cloud", "软件", "订阅", "云服务"),
    "travel": ("travel", "taxi", "hotel", "train", "flight", "交通", "差旅", "酒店", "火车"),
    "meals": ("meal", "cafe", "restaurant", "coffee", "餐饮", "餐厅", "咖啡"),
    "equipment": ("equipment", "laptop", "computer", "monitor", "设备", "电脑", "显示器"),
    "utilities": ("utilities", "electric", "internet", "水电", "电费", "网络"),
    "other": ("other", "其他"),
}
LABELS = dict(zip(CATEGORIES, ("办公用品", "软件服务", "差旅", "餐饮", "设备", "公用事业", "其他")))
CURRENCIES = {"CNY", "USD", "EUR", "GBP", "HKD", "JPY", "CAD", "AUD", "SGD"}
MONEY = r"(?:[+-]?\s*[(]?\s*(?:[A-Z]{3}|[¥￥$€£])?\s*[+-]?\s*\d+(?:,\d{3})*(?:\.\d{1,2})?\s*(?:[A-Z]{3}|元)?\s*[)]?)"
DATE = r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?"


@dataclass(frozen=True)
class Entry:
    vendor: str
    date: str
    cents: int
    currency: str
    category: str
    direction: str
    reference: str = ""


def category_for(text):
    text = text.casefold()
    for category, words in CATEGORIES.items():
        for word in (category, *words):
            if (word in text if not word.isascii() else re.search(r"\b" + word + r"s?\b", text)):
                return category
    return "other"


def money(raw, currency=""):
    raw = str(raw).strip().upper()
    currency = currency.strip().upper()
    currency = {"RMB": "CNY", "人民币": "CNY"}.get(currency, currency)
    codes = {code for code in re.findall(r"[A-Z]{3}", raw)}
    symbols = {"CNY" if c in "¥￥元" else {"$": "USD", "€": "EUR", "£": "GBP"}[c]
               for c in set(raw) & set("¥￥元$€£")}
    if not currency:
        if len(codes or symbols) != 1:
            raise ValueError("Specify the currency (for example CNY or USD).")
        currency = next(iter(codes or symbols))
    if currency not in CURRENCIES or (codes and codes != {currency}):
        raise ValueError("Unsupported or conflicting currency.")
    if ("¥" in raw or "￥" in raw) and currency == "JPY":
        symbols.discard("CNY")
    if "$" in raw and currency in {"USD", "CAD", "AUD", "SGD", "HKD"}:
        symbols.discard("USD")
    if symbols and symbols != {currency}:
        raise ValueError("Conflicting currency symbol.")
    raw = re.sub(r"[A-Z]{3}|[¥￥元$€£\s]", "", raw)
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", raw):
        raise ValueError("Invalid total; expected up to two decimal places.")
    try:
        cents = int(Decimal(raw.replace(",", "")) * 100)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError("Invalid total.") from None
    if not 0 < abs(cents) <= 100_000_000_000:
        raise ValueError("Amount must be nonzero and at most 1 billion.")
    return cents, currency


def make_entry(vendor, dated, total, currency="", category="", direction="", reference="", detail="", bank=False):
    vendor, reference = vendor.strip(), reference.strip()
    if not vendor or len(vendor) > 150 or len(reference) > 150:
        raise ValueError("Vendor is required; vendor and reference must be at most 150 characters.")
    match = re.fullmatch(DATE, dated.strip())
    if not match:
        raise ValueError("Date is required (YYYY-MM-DD).")
    parts = [int(n) for n in re.findall(r"\d+", dated)]
    dated = date(*parts).isoformat()
    cents, currency = money(total, currency)
    direction = direction.strip().casefold()
    if direction in {"income", "credit", "收入", "入账"}:
        direction = "income"
    elif direction in {"expense", "debit", "支出", "付款"}:
        direction = "expense"
    elif direction:
        raise ValueError("Type must be income or expense.")
    else:
        direction = "income" if bank and cents > 0 else "expense"
    if category:
        bucket = category_for(category)
    else:
        bucket = category_for(detail + " " + vendor)
    return Entry(vendor, dated, abs(cents), currency, bucket, direction, reference)


def field(text, labels):
    match = re.search(r"^\s*(?:" + labels + r")[ \t]*[:：][ \t]*([^\r\n]+)", text, re.I | re.M)
    return match[1].strip() if match else ""


def from_text(text):
    vendor = field(text, r"vendor|merchant|supplier|payee|seller|商户|供应商|销售方|收款方")
    if not vendor:
        vendor = next((line.strip() for line in text.splitlines()
                       if line.strip() and not re.match(r"^(invoice|receipt|发票|收据)(\b|$)", line.strip(), re.I)
                       and not re.search(r"[:：]", line)), "")
    dated = field(text, r"(?:invoice |receipt )?date|日期|开票日期|交易日期")
    if not dated:
        matched = re.search(DATE, text)
        dated = matched[0] if matched else ""
    total = ""
    for label in (
        r"grand total|amount (?:paid|due)|total paid|价税合计|实付金额|应付金额",
        r"total(?: amount)?|合计金额|合计|总金额|总计|金额",
    ):
        result = re.search(r"^[ \t]*(?:" + label + r")[ \t]*[:：]?[ \t]*(" + MONEY +
                           r")[ \t]*$", text, re.I | re.M)
        if result:
            total = result[1]
            break
    return make_entry(vendor, dated, total, field(text, r"currency|币种"),
                      field(text, r"category|类别"), field(text, r"type|direction|收支类型"),
                      field(text, r"(?:invoice|receipt|reference)(?:[ \t]*(?:no\.?|number|#))?|票号|发票号码|流水号"), text)


CSV_FIELDS = {
    "vendor": ("vendor", "merchant", "payee", "商户", "供应商"),
    "date": ("date", "transaction date", "日期", "交易日期"),
    "amount": ("amount", "total", "金额"),
    "currency": ("currency", "币种"),
    "category": ("category", "类别"),
    "type": ("type", "direction", "收支类型"),
    "reference": ("reference", "reference id", "id", "票号", "流水号"),
    "detail": ("description", "note", "memo", "说明", "备注"),
}


def from_csv(text):
    rows = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    headers = {key.strip().casefold(): key for key in rows.fieldnames or ()}
    keys = {name: next((headers[k] for k in synonyms if k in headers), None)
            for name, synonyms in CSV_FIELDS.items()}
    if not all(keys[k] for k in ("vendor", "date", "amount")):
        raise ValueError("CSV needs vendor, date and amount columns (plus currency if amount has no currency).")
    results = []
    try:
        for i, row in enumerate(rows, start=2):
            if i > MAX_ROWS + 1:
                raise ValueError(f"CSV may contain at most {MAX_ROWS} records.")
            def col(name):
                return row.get(keys[name]) or ""
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Column count does not match the header.")
                entry = make_entry(col("vendor"), col("date"), col("amount"), col("currency"), col("category"),
                                   col("type"), col("reference"), col("detail"), bank=True)
                evidence = "; ".join(f"{key.strip()}: {value}" for key, value in row.items() if value)
                results.append((entry, evidence))
            except ValueError as exc:
                raise ValueError(f"CSV line {i}: {exc}") from exc
    except csv.Error as exc:
        raise ValueError(f"Invalid CSV: {exc}") from exc
    if not results:
        raise ValueError("CSV has no transactions.")
    return results


def extract(name, data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Document is empty or exceeds 5 MB.")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        try:
            pdf = PdfReader(io.BytesIO(data))
            if pdf.is_encrypted or len(pdf.pages) > 25:
                raise ValueError("Use an unencrypted PDF of at most 25 pages.")
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except (PdfReadError, OSError) as exc:
            raise ValueError("Could not read PDF.") from exc
        if not text.strip():
            raise ValueError("This PDF has no extractable text; OCR it or paste its text.")
    elif suffix in {".txt", ".csv"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Save your text or CSV as UTF-8.") from exc
    else:
        raise ValueError("Use a .txt, .csv or .pdf file.")
    if suffix == ".csv":
        return from_csv(text)
    try:
        return [(from_text(text), text)]
    except ValueError:
        # Keep a searchable evidence-only document rather than invent transaction fields.
        if not text.strip():
            raise ValueError("Document has no text.") from None
        return [(None, text)]
