import argparse
import csv
import json
import sqlite3


def fetch_projects(db_file):
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM projects").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_csv(data, path):
    if not data:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)


def main():
    parser = argparse.ArgumentParser(description="Export project data from database")
    parser.add_argument("--db", default="portfolio_v2.db", help="Path to database file")
    parser.add_argument("--json", help="Path to JSON output file")
    parser.add_argument("--csv", help="Path to CSV output file")
    args = parser.parse_args()

    projects = fetch_projects(args.db)

    if args.json:
        export_json(projects, args.json)
        print(f"Saved JSON to {args.json}")
    if args.csv:
        export_csv(projects, args.csv)
        print(f"Saved CSV to {args.csv}")
    if not args.json and not args.csv:
        parser.error("Specify --json or --csv to export data")


if __name__ == "__main__":
    main()
