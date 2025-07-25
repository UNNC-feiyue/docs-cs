import argparse

from feiyue import db

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--source", choices=["cloud", "cache"], default="cache")
    args = parser.parse_args()

    print("[INFO] Step 1/1: Getting records from database...")
    db.get_records(args.api_key, args.source)

    print("\n[SUCCESS]")
