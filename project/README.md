# ClearBooks Agent demo

From the package root, run `bash readme/install.sh`. Then from `project/`:

```bash
../.venv/bin/python -m clearbooks serve
# Open http://127.0.0.1:8765/ and click Load demo data.
```

CLI (run within `project/`; use a fresh database path for reproducible demo totals):

```bash
export CLEARBOOKS_DB="$HOME/.clearbooks/demo.sqlite3"
../.venv/bin/python -m clearbooks demo
../.venv/bin/python -m clearbooks import samples/05-print-invoice.pdf
../.venv/bin/python -m clearbooks summary --month 2026-11
../.venv/bin/python -m clearbooks ask --month 2026-11 'How much did I spend on office supplies in November?'
../.venv/bin/python -m clearbooks ask --month 2026-11 '查找文档：Net 30'
../.venv/bin/python -m clearbooks report --month 2026-11 --lang zh
../.venv/bin/python -m clearbooks budget 2026-11 office CNY 500
```

## Import and review

- **TXT / paste**: one invoice or receipt per file; labeled fields such as `Vendor:`, `Date:`, `Grand total: CNY 240.00`, optional `Category:`, `Invoice No:` and `Type:`. Chinese labels such as 商户、日期、实付金额、票号 are supported. Unrecognized/incomplete invoices and ordinary documents are retained as **evidence only** and never included in totals; re-import corrected text if needed.
- **PDF**: one invoice/receipt per text document; up to 25 pages. No OCR; paste extracted text for scans. Up to 5 MB for any input.
- **CSV**: UTF-8 with `date,vendor,amount,currency`, optional `category,type,reference,description` and supported Chinese header aliases. Positive amounts default to income, negative to expense; explicit `type` overrides sign. Currency code or an unambiguous supported symbol is required. Use a currency code when a symbol could mean multiple currencies. Monetary values have at most two fractional digits; currencies are never converted or added together.
- Identical file bytes are skipped. Transaction dedup matches normalized vendor, date, total, currency, direction and reference (including empty reference); it is not fuzzy matching. Use unique references for legitimate similar payments.
- Review flags are rules, not fraud conclusions: CNY/HKD ≥ 2,500; JPY ≥ 50,000; other supported currencies ≥ 500; or amount ≥ 3× the historical median of at least three earlier expenses in that currency and category.
- Supported questions use an intent router and display sources: expense/income totals, top vendors, budgets, cash flow, large/abnormal transactions and keyword document search. A named month with no year takes the selected year. Totals use all matches; source excerpts are capped at eight. Vendor rankings are per currency. Use explicit currency or supported category terms to narrow results.
- This is a local bookkeeping aid, not double-entry accounting, OCR, tax or fraud software. Validate imported figures against originals.

## Optional model — not needed

With no environment variables the app does not contact an LLM. To append a narrative note to a report only, set `CLEARBOOKS_LLM_ENDPOINT` to the full OpenAI-compatible chat completions URL and `CLEARBOOKS_LLM_MODEL` to the provider's model name. Set `CLEARBOOKS_LLM_API_KEY` only if required; keep it out of Git and screenshots. A self-hosted compatible endpoint is also supported. Check the provider's privacy and pricing before enabling; use HTTPS for a remote endpoint. Only currency aggregates, budgets and flag count are sent, never vendor names, document text or questions. The deterministic report remains unchanged if the provider fails. An external provider was not called in testing.
