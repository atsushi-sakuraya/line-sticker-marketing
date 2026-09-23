# line-sticker-marketing

chabi の LINE スタンプ（つな＆くれあ／まりん）を SNS で宣伝する自律運用ループの「投稿実行側」。

```
Claude 定期タスク（企画・執筆・分析）
   │  Notion「投稿キュー」に投稿案を書く（ステータス: 下書き or 承認）
   ▼
GitHub Actions（このリポジトリ、毎時）
   │  4時間以内の承認済み行を取得 → スタンプ付きなら画像合成 → rendered/ に commit
   ▼
Buffer 無料プラン（API） → X / Instagram / Threads に予約投稿
```

費用: すべて無料枠（Buffer Free: 3チャネル・各10件まで予約、API 月3,000リクエスト／GitHub Actions 公開リポジトリは無料／Notion Free）。

## セットアップ（最初の1回だけ・約40分）

1. **このリポジトリを GitHub に public で作成**（画像を raw URL で Buffer に渡すため public 必須）
2. **スタンプ画像を配置**: `assets/stickers/tsuna_kurea/01.png` 〜 `40.png`、`assets/stickers/marin/01.png` 〜 `40.png`
   （LINE Creators Market に提出した PNG をそのまま、番号は提出順）
3. **SNS アカウント作成**: X、Instagram（プロアカウント=クリエイター）、Threads
4. **Buffer**（buffer.com）無料登録 → 3チャネル接続 → Settings > API で API キー発行
5. `BUFFER_API_KEY=xxx python scripts/list_channels.py` でチャネルIDを確認
6. **Notion インテグレーション**を作成（notion.so/my-integrations）→「LINEスタンプ マーケ運用ハブ（chabi）」ページの「接続」に追加
7. GitHub リポジトリの Settings > Secrets and variables > Actions:
   - Secrets: `NOTION_TOKEN`, `BUFFER_API_KEY`
   - Variables: `NOTION_DB_ID`（= `c161ba0cb9b84972b12024b775b30505`）, `BUFFER_CHANNEL_X`, `BUFFER_CHANNEL_INSTAGRAM`, `BUFFER_CHANNEL_THREADS`
8. Actions タブ → publish-queue → Run workflow（dry_run=1）でログ確認 → 問題なければ dry_run=0

## 運用

- 運用モードは **自動**（Claude の投稿案は「承認」で入り、そのまま投稿される）。出したくない行は「却下」に。
- X は1日2〜10件の短文。LINEスタンプ画像は「くすっ」とするオチのときだけ付ける（スタンプ列が空ならテキストのみ投稿）。Instagram は画像必須。
- 止めたいときは Notion ハブの「一時停止: はい」。
- 失敗した行はステータス「失敗」、理由は「メモ」列。

## ローカルで画像だけ試す

```
python scripts/render.py "tsuna_kurea/05,tsuna_kurea/12" dialog "月曜の朝のぼくたち" out.png
```
