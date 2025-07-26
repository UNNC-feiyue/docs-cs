import argparse

import db
import docs

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--source", choices=["cloud", "cache"], default="cache")
    parser.add_argument("--template", type=str, default="templates")
    parser.add_argument("--resources", type=str, default="resources")
    parser.add_argument("--output", type=str, default="docs/output")
    args = parser.parse_args()

    print("[INFO] Step 1/1: Getting records from database...")
    records = db.get_records(args.api_key, args.source)

    print("\n[INFO] Step 2/2: Building mkdocs pages...")
    docs.build_pages(records, args.template, args.resources, args.output)

    print("\n[SUCCESS]")
