import json
import re
import shutil
from pathlib import Path

import api

CACHE_DIR = Path.cwd() / ".cache"


def load_from_cache(filename: str) -> dict:
    with open(CACHE_DIR / filename) as f:
        return json.load(f)


def save_to_cache(filename: str, data: dict) -> None:
    with open(CACHE_DIR / filename, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def match_update_images(content: str) -> tuple[list[tuple[str, str]], str]:
    # Match image URL pattern in <img src="...">
    _pattern = re.compile(
        r'img\s+src="https://cloud\.seatable\.io/workspace/\d+/asset/[a-f0-9\-]+/(images/\d{4}-\d{2}/([^"]+))"'
    )
    images = []

    def _replace(m):
        path = m.group(1)  # e.g. images/2025-07/image-xxx.png
        filename = m.group(2)  # e.g. image-xxx.png
        images.append((path, filename))
        return f'img src="../../images/{filename}"'  # Replace URL with relative path to images_dir

    updated_content = _pattern.sub(_replace, content)
    return images, updated_content


def get_records(api_key: str, source: str) -> tuple[list[dict], dict]:
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
                try:
                    image_links = load_from_cache("Image.json")
                    for image in image_links.values():
                        image["download_link"] = api.get_file_download_link(api_key, image["path"])
                except (FileNotFoundError, json.JSONDecodeError):
                    print(f"Loaded all records from cache\nNO CACHED IMAGE FOUND, USE --source cloud IF NEEDED")
                    return [universities, programs, students, applications], {}
                else:
                    print(f"Loaded all records from cache, including {len(image_links)} image links")
                    return [universities, programs, students, applications], image_links
        else:
            print("Cache directory does not exist, try to fetch from cloud")

    # Fetch records from cloud
    if not api_key:
        raise Exception("Failed to access cloud database, an API key is required")

    token, uuid = api.get_base_token_uuid(api_key)

    universities = api.get_all_rows("University", token, uuid)
    print(f"Fetched {len(universities)} university entries from cloud")

    programs = api.get_all_rows("Program", token, uuid)
    print(f"Fetched {len(programs)} program entries from cloud")

    students = api.get_all_rows("Student", token, uuid)
    image_links = {}
    for student in students.values():
        for column in ["experience", "sharing"]:
            content = student[column]
            if not content:
                continue
            images, updated_content = match_update_images(content)
            if images:
                student[column] = updated_content
                for path, filename in images:
                    if filename not in image_links:
                        image_links[filename] = {
                            "path": path,
                            "download_link": api.get_file_download_link(api_key, path)
                        }

    if image_links:
        print(f"Fetched {len(students)} student entries from cloud, including {len(image_links)} image links")
    else:
        print(f"Fetched {len(students)} student entries from cloud")

    applications = api.get_all_rows("Application", token, uuid)
    print(f"Fetched {len(applications)} application entries from cloud")

    # Save records to cache
    CACHE_DIR.mkdir(exist_ok=True)
    save_to_cache("University.json", universities)
    save_to_cache("Program.json", programs)
    save_to_cache("Student.json", students)
    save_to_cache("Application.json", applications)
    save_to_cache("Image.json", {
        filename: {
            "path": data["path"]
        } for filename, data in image_links.items()
    })
    print(f"Saved all records to cache")

    return [universities, programs, students, applications], image_links
