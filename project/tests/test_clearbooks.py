import json
import threading
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from clearbooks import agent
from clearbooks.__main__ import main
from clearbooks.extract import extract, money
from clearbooks.ledger import Ledger, SAMPLES
from clearbooks.web import create_server


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.sqlite3")


@pytest.mark.parametrize("filename,vendor,amount,category", [
    ("01-stationery.txt", "Silk Road Stationery", 24_000, "office"),
    ("03-coffee.txt", "西安晨光咖啡", 6_800, "meals"),
    ("05-print-invoice.pdf", "Loess Print Shop", 11_000, "office"),
])
def test_extract_text_and_pdf(filename, vendor, amount, category):
    row, text = extract(filename, (SAMPLES / filename).read_bytes())[0]
    assert (row.vendor, row.cents, row.currency, row.category) == (vendor, amount, "CNY", category)
    assert vendor in text


@pytest.mark.parametrize("total,code,wanted", [("($1,200.34)", "", (-120034, "USD")),
                                               ("￥100", "JPY", (10000, "JPY")),
                                               ("0.25", "人民币", (25, "CNY"))])
def test_money(total, code, wanted):
    assert money(total, code) == wanted


@pytest.mark.parametrize("total,code", [("10.234", "CNY"), ("€4", "CNY"), ("10", ""), ("12,34.12", "USD")])
def test_money_rejects_invalid_or_ambiguous(total, code):
    with pytest.raises(ValueError):
        money(total, code)


def test_csv_invalid_row_is_atomic(ledger):
    body = "vendor,date,amount,currency\nOK,2026-11-02,-5,CNY\nBad,2026-11-45,-47,CNY\n"
    with pytest.raises(ValueError, match="CSV line 3"):
        ledger.ingest("bank.csv", body.encode())
    assert ledger.rows() == []


def test_csv_uses_sign_unless_type_is_explicit(ledger):
    body = "vendor,date,amount,currency,type\nA,2026-11-02,-5,CNY,\nB,2026-11-02,47,CNY,\nC,2026-11-02,12,CNY,debit\n"
    ledger.ingest("bank.csv", body.encode())
    groups = ledger.summary("2026-11")["currencies"]["CNY"]
    assert (groups["income"], groups["expense"], groups["net"]) == (4700, 1700, 3000)


def test_demo_detects_duplicate_file_and_transaction(ledger):
    results = ledger.demo()
    assert sum(r["added"] for r in results) == 12
    assert sum(r["duplicates"] for r in results) == 1
    assert sum(r["evidence_only"] for r in results) == 1
    assert all(r["duplicate_file"] for r in ledger.demo())
    assert len(Ledger(ledger.path).rows()) == 13


def test_distinct_references_and_amounts(ledger):
    source = (SAMPLES / "01-stationery.txt").read_text()
    for ref in ("SR-114", "SR-115"):
        assert ledger.ingest(ref + ".txt", source.replace("SR-114", ref).encode())["added"] == 1
    assert ledger.summary("2026-11")["currencies"]["CNY"]["expense"] == 48000


def test_cash_budget_anomaly_and_currency_separation(ledger):
    ledger.demo()
    summary = ledger.summary("2026-11")
    assert summary["currencies"]["CNY"] == {"income": 980000, "expense": 404800, "net": 575200,
        "categories": {"office": 43000, "equipment": 320000, "meals": 6800, "travel": 9000, "software": 26000}}
    assert summary["currencies"]["USD"]["net"] == -1900
    assert [b["remaining"] for b in summary["budgets"]] == [-8000, -6000]
    assert [a["reason"] for a in summary["alerts"]] == ["large_and_unusual"]
    ledger.set_budget("2026-11", "office", "CNY", "500")
    assert ledger.summary("2026-11")["budgets"][0]["remaining"] == 7000


@pytest.mark.parametrize("question,lang,intent,expected", [
    ("How much did I spend on office supplies in November?", "en", "expense_total", "CNY 430.00"),
    ("2026年11月办公用品花了多少？", "zh", "expense_total", "CNY 430.00"),
    ("Which vendor did I pay most?", "en", "top_vendor", "Northwest Digital"),
    ("哪家供应商付款最多？", None, "top_vendor", "Northwest Digital"),
    ("软件预算", "zh", "budget", "260.00"),
    ("大额支出", "zh", "review_expenses", "3,200.00"),
    ("Find document: Net 30", "en", "document_search", "Found 1"),
    ("查找文档：Net 30", None, "document_search", "找到 1"),
    ("Cash flow in November", "en", "monthly_summary", "5,752.00"),
    ("USD expenses", "en", "expense_total", "USD 19.00"),
])
def test_agent_routes_and_cites(ledger, question, lang, intent, expected):
    ledger.demo()
    result = agent.ask(ledger, question, "2026-11", lang)
    assert result["intent"] == intent
    assert expected in result["answer"]
    assert result["trace"][-1] == "cite_sources"
    assert all(r["source"] and r["excerpt"] for r in result["citations"])
    assert result["citations"]


def test_report_works_without_provider(ledger, monkeypatch):
    monkeypatch.delenv("CLEARBOOKS_LLM_ENDPOINT", raising=False)
    ledger.demo()
    result = agent.report(ledger, "2026-11", "zh")
    assert result["provider"] == "local"
    assert "办公用品超预算 CNY 80.00" in result["report"]
    assert "USD" in result["report"]


def test_provider_receives_aggregates_only(ledger, monkeypatch):
    ledger.demo()
    monkeypatch.setenv("CLEARBOOKS_LLM_ENDPOINT", "http://127.0.0.1:9999")
    monkeypatch.setenv("CLEARBOOKS_LLM_MODEL", "test")
    def fake(request, timeout):
        aggregates = json.loads(json.loads(request.data)["messages"][1]["content"])
        assert sorted(aggregates) == ["budgets", "currencies", "flag_count"]
        assert b"Northwest" not in request.data
        return BytesIO(b'{"choices":[{"message":{"content":"Review budget variance."}}]}')
    monkeypatch.setattr(agent, "urlopen", fake)
    assert agent.report(ledger, "2026-11")["note"] == "Review budget variance."


def test_cli_demo_budget_ask_report(ledger, capsys):
    base = ["--db", str(ledger.path)]
    assert main(base + ["demo"]) == 0
    assert json.loads(capsys.readouterr().out)[1]["duplicates"] == 1
    assert main(base + ["budget", "2026-11", "office", "CNY", "500"]) == 0
    assert "saved" in json.loads(capsys.readouterr().out)
    assert main(base + ["ask", "office supplies in November"]) == 0
    assert "CNY 430.00" in json.loads(capsys.readouterr().out)["answer"]
    assert main(base + ["report", "--lang", "zh"]) == 0
    assert "办公用品预算剩余 CNY 70.00" in capsys.readouterr().out


def test_web_upload_question_report_and_rejects_external_origin(ledger):
    with create_server(ledger, 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        root = f"http://127.0.0.1:{server.server_port}"
        def request(path, body=None, headers=None):
            req = Request(root + path, json.dumps(body).encode() if body is not None else None,
                          {"Content-Type": "application/json", **(headers or {})})
            with urlopen(req, timeout=3) as reply:
                return reply.read()
        try:
            assert b"Ask ClearBooks" in request("/")
            body = (SAMPLES / "01-stationery.txt").read_text()
            assert json.loads(request("/api/import", {"text": body}))["added"] == 1
            assert json.loads(request("/api/import", {"text": body}))["duplicate_file"]
            assert json.loads(request("/api/summary?month=2026-11"))["currencies"]["CNY"]["expense"] == 24000
            assert "CNY 240.00" in json.loads(request("/api/ask", {"question": "office expenses"}))["answer"]
            assert "240.00" in json.loads(request("/api/report", {}))["report"]
            with pytest.raises(HTTPError) as exc:
                request("/api/demo", {}, {"Origin": "https://unrelated.example"})
            assert exc.value.code == 403
        finally:
            server.shutdown()
            worker.join()
