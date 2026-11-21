import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from statistics import median

from .extract import CATEGORIES, MAX_BYTES, extract, money

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
LARGE = {"CNY": 250000, "JPY": 5000000, "HKD": 250000}
FIELDS = ("vendor", "date", "cents", "currency", "category", "direction", "reference")


def month_key(month):
    if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month):
        raise ValueError("Month must be YYYY-MM.")
    return month


def display(cents):
    return f"{'-' if cents < 0 else ''}{abs(cents) // 100:,}.{abs(cents) % 100:02d}"


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY, hash TEXT UNIQUE NOT NULL, name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
                    evidence TEXT NOT NULL, vendor TEXT, date TEXT, cents INTEGER,
                    currency TEXT, category TEXT, direction TEXT, reference TEXT,
                    fingerprint TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS budgets (
                    month TEXT, category TEXT, currency TEXT, cents INTEGER NOT NULL,
                    PRIMARY KEY(month, category, currency)
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, name, data):
        if not name or len(name) > 200:
            raise ValueError("File name must be 1–200 characters.")
        name = Path(name.replace("\\", "/")).name
        if not name:
            raise ValueError("Use a file name ending in .txt, .csv or .pdf.")
        digest = hashlib.sha256(data).hexdigest()
        result = {"source": name, "added": 0, "duplicates": 0, "evidence_only": 0, "duplicate_file": False}
        with self.connect() as db:
            if db.execute("SELECT id FROM documents WHERE hash = ?", (digest,)).fetchone():
                result["duplicate_file"] = True
                return result
        candidates = extract(name, data)
        with self.connect() as db:
            doc = db.execute("INSERT INTO documents(hash, name) VALUES (?, ?) ON CONFLICT(hash) DO NOTHING",
                             (digest, name))
            if not doc.rowcount:
                result["duplicate_file"] = True
                return result
            for entry, evidence in candidates:
                fields = asdict(entry) if entry else dict.fromkeys(FIELDS)
                fingerprint = None
                if entry:
                    normalized = " ".join(entry.vendor.casefold().split())
                    fingerprint = json.dumps((normalized, entry.date, entry.cents, entry.currency, entry.direction,
                                              entry.reference.strip().casefold()), ensure_ascii=False)
                row = db.execute("""
                    INSERT INTO entries(document_id, evidence, vendor, date, cents, currency, category, direction,
                                        reference, fingerprint)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(fingerprint) DO NOTHING
                """, (doc.lastrowid, evidence[:50_000], *(fields[k] for k in FIELDS), fingerprint))
                result["added" if entry and row.rowcount else "evidence_only" if row.rowcount else "duplicates"] += 1
        return result

    def import_file(self, path):
        path = Path(path)
        with path.open("rb") as file:
            return self.ingest(path.name, file.read(MAX_BYTES + 1))

    def demo(self):
        imports = [self.import_file(path) for path in sorted(SAMPLES.iterdir()) if path.suffix in {".txt", ".csv", ".pdf"}]
        with self.connect() as db:
            db.executemany("INSERT INTO budgets VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                           (("2026-11", "office", "CNY", 35000), ("2026-11", "software", "CNY", 20000)))
        return imports

    def set_budget(self, month, category, currency, amount):
        month_key(month)
        if category not in CATEGORIES:
            raise ValueError("Select a recognized budget category.")
        cents, currency = money(amount, currency)
        if cents < 0:
            raise ValueError("Budget must be positive.")
        with self.connect() as db:
            db.execute("""
                INSERT INTO budgets VALUES (?, ?, ?, ?)
                ON CONFLICT(month, category, currency) DO UPDATE SET cents = excluded.cents
            """, (month, category, currency, cents))

    def rows(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT e.id, vendor, date, cents, currency, category, direction, reference, evidence, d.name AS source
                FROM entries e JOIN documents d ON d.id = e.document_id
                ORDER BY e.date DESC, e.id DESC
            """)]

    def months(self):
        with self.connect() as db:
            return [row[0] for row in db.execute("""
                SELECT substr(date, 1, 7) AS month FROM entries WHERE date IS NOT NULL
                UNION SELECT month FROM budgets ORDER BY month DESC
            """)]

    def summary(self, month):
        month_key(month)
        all_rows = self.rows()
        records = [row for row in all_rows if row["date"] and row["date"][:7] == month]
        groups = defaultdict(lambda: {"income": 0, "expense": 0, "net": 0, "categories": {}})
        alerts = []
        for row in records:
            group = groups[row["currency"]]
            group[row["direction"]] += row["cents"]
            if row["direction"] == "expense":
                category = row["category"]
                group["categories"][category] = group["categories"].get(category, 0) + row["cents"]
                peers = [peer["cents"] for peer in all_rows if peer["date"] and peer["date"] < row["date"]
                         and peer["currency"] == row["currency"] and peer["category"] == category
                         and peer["direction"] == "expense"]
                large = row["cents"] >= LARGE.get(row["currency"], 50000)
                unusual = len(peers) >= 3 and row["cents"] >= 3 * median(peers)
                if large or unusual:
                    alerts.append({"id": row["id"], "vendor": row["vendor"], "cents": row["cents"],
                                   "currency": row["currency"], "source": row["source"],
                                   "reason": "large_and_unusual" if large and unusual else "large" if large else "unusual"})
        for group in groups.values():
            group["net"] = group["income"] - group["expense"]
        with self.connect() as db:
            budgets = [dict(row) for row in db.execute(
                "SELECT category, currency, cents FROM budgets WHERE month = ? ORDER BY currency, category", (month,))]
        for item in budgets:
            item["spent"] = groups[item["currency"]]["categories"].get(item["category"], 0)
            item["remaining"] = item["cents"] - item["spent"]
        return {"month": month, "currencies": dict(groups), "entries": records, "alerts": alerts, "budgets": budgets,
                "evidence_only": sum(row["date"] is None for row in all_rows)}
