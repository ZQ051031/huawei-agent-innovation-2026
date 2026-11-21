import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import agent
from .extract import CATEGORIES, CURRENCIES, MAX_BYTES
from .ledger import Ledger, display
from .web import create_server


def main(argv=None):
    parser = argparse.ArgumentParser(prog="clearbooks", description="Local document and finance agent")
    parser.add_argument("--db", default=os.getenv("CLEARBOOKS_DB") or str(Path.home() / ".clearbooks" / "ledger.sqlite3"))
    subs = parser.add_subparsers(dest="command", required=True)
    serve = subs.add_parser("serve", help="Start the local web interface")
    serve.add_argument("--port", type=int, default=8765)
    subs.add_parser("demo", help="Load bundled samples and budget")
    ingest = subs.add_parser("import", help="Import TXT, CSV or PDF; use - for pasted text on stdin")
    ingest.add_argument("source", nargs="+")
    budget = subs.add_parser("budget", help="Set a monthly category budget")
    budget.add_argument("month")
    budget.add_argument("category", choices=CATEGORIES)
    budget.add_argument("currency", choices=sorted(CURRENCIES))
    budget.add_argument("amount")
    for command in ("summary", "ask", "report"):
        sub = subs.add_parser(command)
        sub.add_argument("--month", help="Default period YYYY-MM (latest period or current month)")
        if command != "summary":
            sub.add_argument("--lang", choices=("zh", "en"))
        if command == "ask":
            sub.add_argument("question")
    args = parser.parse_args(argv)
    try:
        db = Ledger(args.db)
        if args.command == "serve":
            with create_server(db, args.port) as server:
                print(f"ClearBooks is listening at http://127.0.0.1:{server.server_port}", flush=True)
                server.serve_forever()
            return 0
        if args.command == "demo":
            result = db.demo()
        elif args.command == "import":
            result = [db.ingest("pasted.txt", sys.stdin.buffer.read(MAX_BYTES + 1)) if f == "-" else db.import_file(f)
                      for f in args.source]
        elif args.command == "budget":
            db.set_budget(args.month, args.category, args.currency, args.amount)
            result = {"saved": f"{args.month} {args.category} {args.currency} {args.amount}"}
        else:
            months = db.months()
            month = args.month or (months[0] if months else date.today().isoformat()[:7])
            if args.command == "ask":
                result = agent.ask(db, args.question, month, args.lang)
            elif args.command == "report":
                result = agent.report(db, month, args.lang or "en")
                print(result["report"])
                if "note" in result:
                    print("\nOptional AI note:\n" + result["note"])
                if "notice" in result:
                    print(result["notice"], file=sys.stderr)
                return 0
            else:
                result = db.summary(month)
                for item in result["entries"]:
                    item.pop("evidence")
                    item["amount"] = display(item["cents"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ClearBooks: {exc}\n")
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
