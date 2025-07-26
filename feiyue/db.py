import json
import shutil
from pathlib import Path

import api

CACHE_DIR = Path.cwd() / ".cache"


def load_from_cache(filename: str) -> dict:
    with open(CACHE_DIR / filename) as f:
        return json.load(f)


def save_to_cache(filename: str, data: dict) -> None:
    with open(CACHE_DIR / filename, "w") as f:
        json.dump(data, f, ensure_ascii=False)


def get_records(api_key: str, source: str) -> list[dict]:
    # Load records from cache
    if source == "cache":
        if CACHE_DIR.exists():
            try:
                universities = load_from_cache("University.json")
                programs = load_from_cache("Program.json")
                students = load_from_cache("Student.json")
                applications = load_from_cache("Application.json")
            except (FileNotFoundError, json.JSONDecodeError):
                shutil.rmtree(CACHE_DIR)
                print("Cache is corrupted or incomplete, try to get from cloud")
            else:
                print("Loaded all records from cache")
                return [universities, programs, students, applications]
        else:
            print("Cache directory does not exist, try to get from cloud")

    # Fetch records from cloud
    if not api_key:
        raise Exception("Failed to access cloud database, an API key is required")

    token, uuid = api.get_base_token_uuid(api_key)

    universities = api.get_all_rows("University", token, uuid)
    print(f"Fetched {len(universities)}\t university entries from cloud")
    programs = api.get_all_rows("Program", token, uuid)
    print(f"Fetched {len(programs)}\t program entries from cloud")
    students = api.get_all_rows("Student", token, uuid)
    print(f"Fetched {len(students)}\t student entries from cloud")
    applications = api.get_all_rows("Application", token, uuid)
    print(f"Fetched {len(applications)}\t application entries from cloud")

    # Save records to cache
    CACHE_DIR.mkdir(exist_ok=True)
    save_to_cache("University.json", universities)
    save_to_cache("Program.json", programs)
    save_to_cache("Student.json", students)
    save_to_cache("Application.json", applications)
    print(f"Saved all records to cache")

    return [universities, programs, students, applications]
