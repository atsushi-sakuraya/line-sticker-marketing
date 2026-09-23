"""Buffer の組織IDとチャネルIDを表示する（初回セットアップ用）。
  BUFFER_API_KEY=xxx python scripts/list_channels.py
"""
import os

import requests

H = {"Authorization": f"Bearer {os.environ['BUFFER_API_KEY']}", "Content-Type": "application/json"}


def gql(q):
    r = requests.post("https://api.buffer.com", headers=H, json={"query": q}, timeout=30)
    r.raise_for_status()
    return r.json()["data"]


orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
for o in orgs:
    print(f"org: {o['name']} ({o['id']})")
    chans = gql(f'query {{ channels(input: {{ organizationId: "{o["id"]}" }}) {{ id name service }} }}')["channels"]
    for c in chans:
        print(f"  {c['service']:10s} {c['name']:30s} {c['id']}")
