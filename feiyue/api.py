import argparse
import json

import requests

SERVER = "cloud.seatable.io"


def parse_headers(token: str) -> dict:
    return {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }


def get_base_token_uuid(api_key: str) -> tuple[str, str]:
    url = f"https://{SERVER}/api/v2.1/dtable/app-access-token/"
    headers = parse_headers(api_key)
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to generate base token: {response.status_code} {response.text}")

    return response.json()["access_token"], response.json()["dtable_uuid"]


def get_metadata(base_token: str, base_uuid: str) -> dict:
    url = f"https://{SERVER}/api-gateway/api/v2/dtables/{base_uuid}/metadata/"
    headers = parse_headers(base_token)
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to get metadata: {response.status_code} {response.text}")

    return response.json()


def get_all_rows(table_name: str, base_token: str, base_uuid: str) -> dict:
    rows = {}
    start = 0
    limit = 1000

    url = f"https://{SERVER}/api-gateway/api/v2/dtables/{base_uuid}/rows/"
    headers = parse_headers(base_token)
    params = {
        "table_name": table_name,
        "start": start,
        "limit": limit,
        "convert_keys": True,
    }
    while True:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Failed to get rows: {response.status_code} {response.text}")

        for row in response.json()["rows"]:
            # Key "_id" is the unique identifier for each row in SeaTable
            rows[row["_id"]] = row

        if len(response.json()["rows"]) < limit:
            break

        start += limit
        continue

    return rows


def get_file_download_link(api_key: str, path: str) -> str:
    url = f"https://{SERVER}/api/v2.1/dtable/app-download-link/"
    headers = parse_headers(api_key)
    params = {'path': path}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        raise Exception(f"Failed to get file download link: {response.status_code} {response.text}")

    return response.json()["download_link"]


# Test api-key/base-token functionality and view db tables and attributes
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", type=str, required=True)
    args = parser.parse_args()

    metadata = get_metadata(get_base_token_uuid(args.api_key))
    result = {}
    for data in metadata['metadata']['tables']:
        table = data['name']
        column = {col['name']: col['type'] for col in data['columns']}
        result[table] = column

    print(json.dumps(result, indent=2))
