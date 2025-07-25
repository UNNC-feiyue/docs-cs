import argparse

import api

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", type=str, required=True)
    args = parser.parse_args()
    api_key = args.api_key
    api.generate_base_token(api_key)

    print("[INFO] Step 1/1: Fetching records from SeaTable database...")
    universities = api.get_all_rows("University")
    print(f"Got {len(universities)}\t university entries")
    programs = api.get_all_rows("Program")
    print(f"Got {len(programs)}\t program entries")
    students = api.get_all_rows("Student")
    print(f"Got {len(students)}\t student entries")
    applications = api.get_all_rows("Application")
    print(f"Got {len(applications)}\t application entries")

    print("\n[SUCCESS] All records downloaded")
