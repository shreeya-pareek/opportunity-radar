import argparse
from pathlib import Path

from .sources import (
    GreenhouseConfigError,
    GreenhouseSource,
    GreenhouseSourceError,
    JsonFileSource,
    load_greenhouse_employers,
)
from .store import OpportunityStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="radar", description="Collect and search opportunities")
    parser.add_argument("--db", type=Path, default=Path("data/opportunities.sqlite3"))
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="Import a publisher-approved JSON feed/export")
    collect.add_argument("json_file", type=Path)
    collect.add_argument("--source", help="Human-readable source name")
    collect_greenhouse = commands.add_parser(
        "collect-greenhouse", help="Collect internship listings from a Greenhouse job board"
    )
    collect_greenhouse.add_argument("board_token", help="Employer's public Greenhouse board token")
    collect_greenhouse_all = commands.add_parser(
        "collect-greenhouse-all",
        help="Collect internship listings from all configured Greenhouse employers",
    )
    collect_greenhouse_all.add_argument(
        "--config", type=Path, required=True, help="JSON file listing employer names and board tokens"
    )
    search = commands.add_parser("search", help="Search collected listings")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--category", default="")
    search.add_argument("--location", default="")
    args = parser.parse_args()

    employers = None
    if args.command == "collect-greenhouse-all":
        try:
            employers = load_greenhouse_employers(args.config)
        except GreenhouseConfigError as exc:
            parser.error(str(exc))

    store = OpportunityStore(args.db)
    try:
        if args.command == "collect-greenhouse-all":
            totals = {"inserted": 0, "updated": 0, "unchanged": 0}
            succeeded = 0
            failed = 0
            for employer in employers:
                display_name = employer["display_name"]
                print(f"Collecting {display_name}...")
                try:
                    items = GreenhouseSource(employer["board_token"]).fetch()
                except GreenhouseSourceError as exc:
                    failed += 1
                    print(f"Failed {display_name}: {exc}")
                    continue

                succeeded += 1
                counts = {"inserted": 0, "updated": 0, "unchanged": 0}
                for item in items:
                    result = store.upsert(item)
                    counts[result] += 1
                    totals[result] += 1
                print(
                    f"{display_name}: succeeded, {len(items)} internship listing(s); "
                    f"{counts['inserted']} inserted, {counts['updated']} updated, "
                    f"{counts['unchanged']} unchanged."
                )

            print(
                f"Greenhouse collection complete: {succeeded} employer(s) succeeded, "
                f"{failed} failed; {totals['inserted']} inserted, "
                f"{totals['updated']} updated, {totals['unchanged']} unchanged."
            )
            if failed:
                raise SystemExit(1)
        elif args.command in {"collect", "collect-greenhouse"}:
            if args.command == "collect":
                source = JsonFileSource(args.json_file, args.source)
                source_name = args.source or args.json_file.stem
            else:
                source = GreenhouseSource(args.board_token)
                source_name = f"Greenhouse board {args.board_token}"
            items = source.fetch()
            counts = {"inserted": 0, "updated": 0, "unchanged": 0}
            for item in items:
                counts[store.upsert(item)] += 1
            print(
                f"Collected {len(items)} listing(s) from {source_name}: "
                f"{counts['inserted']} inserted, {counts['updated']} updated, "
                f"{counts['unchanged']} unchanged."
            )
        else:
            rows = store.search(args.query, args.category, args.location)
            if not rows:
                print("No opportunities found.")
            for row in rows:
                deadline = row["deadline"] or "Not listed"
                print(f"{row['title']} — {row['organization'] or 'Organization not listed'}")
                print(f"  {row['category']} | {row['location']} | Deadline: {deadline}")
                print(f"  Source: {row['source_name']} | {row['application_url']}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
