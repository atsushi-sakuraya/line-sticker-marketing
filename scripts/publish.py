"""Notion「投稿キュー」→ 画像生成 → Buffer 予約投稿 → Notion 更新。

GitHub Actions から定期実行する。必要な環境変数（リポジトリの Secrets / Variables）:
  NOTION_TOKEN        Notion インテグレーションのシークレット
  NOTION_DB_ID        投稿キューのデータベースID
  BUFFER_API_KEY      Buffer の API キー
  BUFFER_CHANNEL_X / BUFFER_CHANNEL_INSTAGRAM / BUFFER_CHANNEL_THREADS  各チャネルID
  GITHUB_REPOSITORY   自動で入る（owner/repo）
  DRY_RUN=1           Buffer に送らず画像生成とログだけ行う
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NOTION = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
BUFFER = "https://api.buffer.com"
CHANNELS = {
    "X": os.environ.get("BUFFER_CHANNEL_X"),
    "Instagram": os.environ.get("BUFFER_CHANNEL_INSTAGRAM"),
    "Threads": os.environ.get("BUFFER_CHANNEL_THREADS"),
}
LOOKAHEAD_H = int(os.environ.get("LOOKAHEAD_HOURS", "4"))  # Buffer無料は1チャネル10件までなので短めに
DRY = os.environ.get("DRY_RUN") == "1"


def _text(prop):
    if not prop:
        return ""
    arr = prop.get("rich_text") or prop.get("title") or []
    return "".join(t.get("plain_text", "") for t in arr)


def _sel(prop):
    s = (prop or {}).get("select")
    return s["name"] if s else ""


def query_approved():
    now = dt.datetime.now(dt.timezone.utc)
    body = {
        "filter": {
            "and": [
                {"property": "ステータス", "select": {"equals": "承認"}},
                {"property": "予定日時", "date": {"on_or_before": (now + dt.timedelta(hours=LOOKAHEAD_H)).isoformat()}},
            ]
        },
        "sorts": [{"property": "予定日時", "direction": "ascending"}],
    }
    r = requests.post(f"{NOTION}/databases/{os.environ['NOTION_DB_ID']}/query", headers=NOTION_HEADERS, json=body, timeout=30)
    r.raise_for_status()
    return r.json()["results"]


def update_page(page_id, props):
    r = requests.patch(f"{NOTION}/pages/{page_id}", headers=NOTION_HEADERS, json={"properties": props}, timeout=30)
    r.raise_for_status()


def rt(s):
    return {"rich_text": [{"text": {"content": s[:1900]}}]}


def git_push(paths):
    if DRY or not paths:
        return
    subprocess.run(["git", "config", "user.name", "sticker-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "sticker-bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", *paths], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
        subprocess.run(["git", "commit", "-m", "render post images"], check=True)
        subprocess.run(["git", "push"], check=True)


def buffer_create(channel_id, text, image_url, due_at):
    """image_url が None ならテキストのみ投稿。"""
    # 公式ドキュメントの例と同じくインライン引数で送る（文字列は JSON エスケープ）
    q = json.dumps
    assets = f"assets: [{{ image: {{ url: {q(image_url)} }} }}]" if image_url else ""
    mutation = f"""
    mutation CreatePost {{
      createPost(input: {{
        text: {q(text, ensure_ascii=False)}
        channelId: {q(channel_id)}
        schedulingType: automatic
        mode: customScheduled
        dueAt: {q(due_at)}
        {assets}
      }}) {{
        ... on PostActionSuccess {{ post {{ id dueAt }} }}
        ... on MutationError {{ message }}
      }}
    }}"""
    r = requests.post(
        BUFFER,
        headers={"Authorization": f"Bearer {os.environ['BUFFER_API_KEY']}", "Content-Type": "application/json"},
        json={"query": mutation},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))
    res = data["data"]["createPost"]
    if "post" not in res:
        raise RuntimeError(res.get("message", "unknown Buffer error"))
    return res["post"]["id"]


def mark_posted():
    """予定時刻を1時間以上過ぎた「予約済み」を「投稿済み」にする（Buffer側の失敗は Buffer の通知で確認）。"""
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
    body = {"filter": {"and": [
        {"property": "ステータス", "select": {"equals": "予約済み"}},
        {"property": "予定日時", "date": {"on_or_before": past}},
    ]}}
    r = requests.post(f"{NOTION}/databases/{os.environ['NOTION_DB_ID']}/query", headers=NOTION_HEADERS, json=body, timeout=30)
    r.raise_for_status()
    for row in r.json()["results"]:
        if not DRY:
            update_page(row["id"], {"ステータス": {"select": {"name": "投稿済み"}}})


def main():
    mark_posted()
    rows = query_approved()
    print(f"approved rows due within {LOOKAHEAD_H}h: {len(rows)}")
    rendered = []
    jobs = []
    for row in rows:
        p = row["properties"]
        pid = row["id"]
        try:
            channel = _sel(p.get("チャネル"))
            if not CHANNELS.get(channel):
                raise RuntimeError(f"channel not configured: {channel}")
            stickers = _text(p.get("スタンプ")).strip()
            fname = None
            if stickers:
                out = ROOT / "rendered" / f"{pid}.png"
                out.parent.mkdir(exist_ok=True)
                render(stickers, _sel(p.get("レイアウト")) or "single", _text(p.get("画像キャプション")), str(out))
                rendered.append(str(out.relative_to(ROOT)))
                fname = out.name
            elif channel == "Instagram":
                raise RuntimeError("Instagram は画像必須です（スタンプ列が空）")
            due = (p["予定日時"]["date"] or {}).get("start")
            due_utc = dt.datetime.fromisoformat(due).astimezone(dt.timezone.utc)
            if due_utc < dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
                due_utc = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
            jobs.append((pid, channel, _text(p.get("本文")), fname, due_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")))
        except Exception as e:  # noqa: BLE001
            print(f"[fail] {pid}: {e}")
            if not DRY:
                update_page(pid, {"ステータス": {"select": {"name": "失敗"}}, "メモ": rt(f"render: {e}")})

    git_push(rendered)
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    for pid, channel, text, fname, due in jobs:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/rendered/{fname}" if fname else None
        if DRY:
            print(f"[dry] {channel} {due} {url}\n{text}\n")
            continue
        try:
            bid = buffer_create(CHANNELS[channel], text, url, due)
            update_page(pid, {"ステータス": {"select": {"name": "予約済み"}}, "BufferID": rt(bid)})
            print(f"[ok] {pid} -> {channel} {due} ({bid})")
        except Exception as e:  # noqa: BLE001
            print(f"[fail] {pid}: {e}")
            update_page(pid, {"ステータス": {"select": {"name": "失敗"}}, "メモ": rt(f"buffer: {e}")})


if __name__ == "__main__":
    main()
