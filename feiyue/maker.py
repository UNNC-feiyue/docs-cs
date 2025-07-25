import argparse

import api

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", type=str, required=True)
    args = parser.parse_args()

    token, uuid = api.get_base_token_uuid(args.api_key)
    print("[INFO] Step 1/1: Fetching records from SeaTable database...")
    universities = api.get_all_rows("University", token, uuid)
    print(f"Got {len(universities)}\t university entries")
    programs = api.get_all_rows("Program", token, uuid)
    print(f"Got {len(programs)}\t program entries")
    students = api.get_all_rows("Student", token, uuid)
    print(f"Got {len(students)}\t student entries")
    applications = api.get_all_rows("Application", token, uuid)
    print(f"Got {len(applications)}\t application entries")

    print("\n[SUCCESS] All records downloaded")
