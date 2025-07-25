import argparse
import json

import requests

SERVER = "cloud.seatable.io"


def get_base_token_uuid(api_key: str) -> tuple[str, str]:
    response = requests.get(
        f"https://{SERVER}/api/v2.1/dtable/app-access-token/",
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
    )
    if response.status_code != 200:
        raise Exception(f"Failed to generate base token: {response.status_code} {response.text}")

    return response.json()["access_token"], response.json()["dtable_uuid"]


def get_metadata(base_token: str, base_uuid: str) -> dict:
    response = requests.get(
        f"https://{SERVER}/api-gateway/api/v2/dtables/{base_uuid}/metadata/",
        headers={"Accept": "application/json", "Authorization": f"Bearer {base_token}"}
    )
    if response.status_code != 200:
        raise Exception(f"Failed to get metadata: {response.status_code} {response.text}")

    return response.json()


def get_all_rows(table_name: str, base_token: str, base_uuid: str) -> dict:
    start = 0
    limit = 1000
    rows = {}
    while True:
        response = requests.get(
            f"https://{SERVER}/api-gateway/api/v2/dtables/{base_uuid}/rows/",
            headers={"Accept": "application/json", "Authorization": f"Bearer {base_token}"},
            params={
                "table_name": table_name,
                "start": start,
                "limit": limit,
                "convert_keys": True,
            }
        )
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


# Test api-key/base-token functionality and view db tables and attributes
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", type=str, required=True)
    args = parser.parse_args()
    token, uuid = get_base_token_uuid(args.api_key)

    metadata = get_metadata(token, uuid)
    result = {}
    for data in metadata['metadata']['tables']:
        table = data['name']
        column = {col['name']: col['type'] for col in data['columns']}
        result[table] = column

    print(json.dumps(result, indent=2))
