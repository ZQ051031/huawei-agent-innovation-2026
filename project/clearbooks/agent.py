import calendar
import json
import os
import re
from collections import defaultdict
from urllib.error import URLError
from urllib.request import Request, urlopen

from .extract import CURRENCIES, LABELS, category_for
from .ledger import display, month_key

HELP = {
    "en": 'Try “office supplies in November”, “which vendor did I pay most?”, “cash flow”, '
          '“budget status”, “large expenses”, or “find document: keyword”.',
    "zh": '试试“11月办公用品花了多少”“哪家供应商付款最多”“现金流”“预算”“大额支出”或“查找文档：关键词”。',
}


def monthly_report(summary, lang):
    zh = lang == "zh"
    month = summary["month"]
    lines = [f"{month} 月度财务报告" if zh else f"{month} monthly finance report"]
    for currency, group in sorted(summary["currencies"].items()):
        incoming, outgoing, net = (display(group[k]) for k in ("income", "expense", "net"))
        lines.append(f"{currency}：本月收入 {incoming}，支出 {outgoing}，净现金流 {net}。" if zh else
                     f"In {currency}, you received {incoming}, spent {outgoing}, and net cash flow was {net}.")
        if group["categories"]:
            name, cents = max(sorted(group["categories"].items()), key=lambda pair: pair[1])
            lines.append(f"最大支出类别为{LABELS[name]}（{currency} {display(cents)}）。" if zh else
                         f"Your biggest spending category was {name} ({currency} {display(cents)}).")
    if not summary["entries"]:
        lines.append("本月未录入交易。" if zh else "No transactions were recorded for this month.")
    for b in summary["budgets"]:
        label = LABELS[b["category"]] if zh else b["category"]
        remaining = f'{b["currency"]} {display(abs(b["remaining"]))}'
        if b["remaining"] < 0:
            lines.append(f"{label}超预算 {remaining}。" if zh else f"{label} is {remaining} over budget.")
        else:
            lines.append(f"{label}预算剩余 {remaining}。" if zh else f"{label} has {remaining} left in its budget.")
    alerts = len(summary["alerts"])
    lines.append(f"{alerts} 笔大额或异常支出建议人工复核；规则标记并非欺诈结论。" if zh else
                 f"Review {alerts} large or unusual expenses. Flags are not fraud determinations.")
    return "\n".join(lines)


def question_month(question, fallback):
    explicit = re.search(r"\b(\d{4})[-/](\d{1,2})(?!\d)|(?:(\d{4})年)?(\d{1,2})月", question)
    if explicit:
        y, m, cy, cm = explicit.groups()
        return month_key(f"{y or cy or fallback[:4]}-{int(m or cm):02d}")
    for n in range(1, 13):
        if re.search(r"\b(?:" + calendar.month_name[n] + "|" + calendar.month_abbr[n]
                     + r")\b", question, re.I):
            year = re.search(r"\b(20\d\d)\b", question)
            return f"{year[0] if year else fallback[:4]}-{n:02d}"
    return fallback


def evidence(rows, limit=8, keyword=None):
    citations = []
    for row in rows[:limit]:
        body = row["evidence"]
        start = 0
        if keyword:
            pos = body.casefold().find(keyword.casefold())
            if pos > 0:
                start = max(0, pos - 70)
        citations.append({"id": row["id"], "source": row["source"], "vendor": row["vendor"], "date": row["date"],
                          "excerpt": body[start:start + 240].strip()})
    return citations


def ask(ledger, question, month, lang=None):
    question = question.strip()
    if not question or len(question) > 500:
        raise ValueError("Enter a question of 1–500 characters.")
    zh = lang == "zh" or (lang is None and re.search(r"[\u3400-\u9fff]", question))
    lang = "zh" if zh else "en"
    q = question.casefold()
    month_key(month)
    search = re.search(r"(?:find document|search documents?|查找文档|搜索文档|查找|搜索)\s*[:：]?\s*(.+)", question, re.I)
    if search:
        keyword = search[1].strip(' "' + "'“”")
        rows = [r for r in ledger.rows() if keyword and keyword.casefold() in
                (r["source"] + "\n" + r["evidence"]).casefold()]
        return {"intent": "document_search", "trace": ["match_evidence", "cite_sources"], "month": None,
                "answer": f"找到 {len(rows)} 条来源，摘录如下。" if zh else f"Found {len(rows)} matching sources. See excerpts.",
                "citations": evidence(rows, keyword=keyword)}
    month = question_month(question, month)
    selected_currency = next((code for code in sorted(CURRENCIES) if re.search(rf"\b{code.lower()}\b", q)), None)
    category = category_for(q)
    s = ledger.summary(month)
    if selected_currency:
        s["currencies"] = {code: totals for code, totals in s["currencies"].items() if code == selected_currency}
        for name in ("entries", "alerts", "budgets"):
            s[name] = [row for row in s[name] if row["currency"] == selected_currency]
    rows = s["entries"]
    trace = ["resolve_period", "query_ledger"]
    if re.search(r"budget|预算", q):
        intent, trace = "budget", trace + ["compare_budget"]
        budgets = [b for b in s["budgets"] if category == "other" or b["category"] == category]
        rows = [r for r in rows if r["direction"] == "expense" and
                any((r["currency"], r["category"]) == (b["currency"], b["category"]) for b in budgets)]
        answer = "\n".join(
            f'{LABELS[b["category"]] if zh else b["category"]}: {b["currency"]} {display(b["spent"])} / '
            f'{display(b["cents"])} ({"剩余" if zh else "remaining"} {display(b["remaining"])})' for b in budgets
        ) or ("没有匹配的预算。" if zh else "No matching budgets.")
    elif re.search(r"large|unusual|outlier|anomal|大额|异常", q):
        intent, trace = "review_expenses", trace + ["apply_review_rules"]
        flags = {a["id"]: a for a in s["alerts"]}
        rows = [r for r in rows if r["id"] in flags and (category == "other" or r["category"] == category)]
        answer = "\n".join(f'{r["vendor"]}: {r["currency"]} {display(r["cents"])}' for r in rows[:12])
        answer = (f"{len(rows)} 笔待复核。" if zh else f"{len(rows)} expenses flagged for review.") + ("\n" + answer if answer else "")
    elif re.search(r"(vendor|supplier|merchant|供应商|商户|哪家)", q) and re.search(r"most|top|largest|最多|最高|最大", q):
        intent, trace = "top_vendor", trace + ["rank_vendors_by_currency"]
        rows = [r for r in rows if r["direction"] == "expense" and (category == "other" or r["category"] == category)]
        totals = defaultdict(lambda: defaultdict(int))
        names = {}
        for r in rows:
            key = " ".join(r["vendor"].casefold().split())
            totals[r["currency"]][key] += r["cents"]
            names.setdefault(key, r["vendor"])
        winners = {code: [key for key in sorted(items) if items[key] == max(items.values())] for code, items in totals.items()}
        answer = "\n".join(f'{", ".join(names[key] for key in keys)}: {code} {display(totals[code][keys[0]])}'
                           for code, keys in sorted(winners.items()))
        rows = [r for r in rows if " ".join(r["vendor"].casefold().split()) in winners[r["currency"]]]
    elif re.search(r"cash.flow|summary|report|现金流|报告|总结|收支", q):
        intent, trace = "monthly_summary", trace + ["summarize_cash_flow"]
        answer = monthly_report(s, lang)
    elif category != "other" or re.search(r"spend|spent|expense|income|revenue|paid|花|支出|收入|销售额", q):
        direction = "income" if re.search(r"income|revenue|收入|销售额", q) else "expense"
        intent, trace = direction + "_total", trace + ["sum_exact_minor_units"]
        rows = [r for r in rows if r["direction"] == direction and (category == "other" or r["category"] == category)]
        totals = defaultdict(int)
        for r in rows:
            totals[r["currency"]] += r["cents"]
        answer = " · ".join(f"{code} {display(cents)}" for code, cents in sorted(totals.items()))
    else:
        return {"intent": "help", "trace": ["match_supported_intent"], "month": month, "answer": HELP[lang], "citations": []}
    if not answer:
        answer = "无匹配交易。" if zh else "No matching transactions."
    return {"intent": intent, "trace": trace + ["cite_sources"], "month": month,
            "answer": f"{month} · {answer}" if intent != "monthly_summary" else answer, "citations": evidence(rows)}


def report(ledger, month, lang="en"):
    summary = ledger.summary(month)
    result = monthly_report(summary, lang)
    endpoint = os.getenv("CLEARBOOKS_LLM_ENDPOINT")
    model = os.getenv("CLEARBOOKS_LLM_MODEL")
    if not (endpoint and model):
        return {"report": result, "provider": "local"}
    # Only aggregate figures leave the machine when the report provider is enabled.
    aggregates = {k: summary[k] for k in ("currencies", "budgets")}
    aggregates["flag_count"] = len(summary["alerts"])
    payload = {"model": model, "messages": [
        {"role": "system", "content": "Write a short qualitative bookkeeping note in " + ("Chinese" if lang == "zh" else "English") +
         ". Do not invent facts or give tax advice. The deterministic report already shows numerical totals."},
        {"role": "user", "content": json.dumps(aggregates)},
    ]}
    headers = {"Content-Type": "application/json"}
    if token := os.getenv("CLEARBOOKS_LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + token
    try:
        request = Request(endpoint, json.dumps(payload).encode(), headers=headers)
        with urlopen(request, timeout=8) as response:
            note = json.loads(response.read(65_536))["choices"][0]["message"]["content"]
        if not isinstance(note, str) or not note.strip():
            raise ValueError("Empty note")
        return {"report": result, "provider": "local+optional_note", "note": note[:3000].strip()}
    except (URLError, OSError, ValueError, KeyError, IndexError, TypeError):
        return {"report": result, "provider": "local", "notice": "Optional provider unavailable; local report retained."}
