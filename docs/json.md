---
layout: page
title: JSON形式
---

`chatlog.py` が蓄積するデータ構造のリファレンスです。通常は直接編集する必要はありません。

## 単一形式

1 チャンネル 1 ファイル。

```json
{
  "channel": "general",
  "service": "discord",
  "retrievedAt": "2024-02-02T05:10:00+00:00",
  "users": { "1002": "bob" },
  "messages": [
    { "id": "…", "ts": "…", "time": "…", "name": "alice",
      "text": "こんにちは <@1002>", "files": ["plan.pdf"] }
  ]
}
```

| キー | 説明 |
| --- | --- |
| `channel` | チャンネル名 |
| `service` | 取得元（`"slack"` / `"discord"`）。ビューアが描画方式の切替に使う（無い場合は `slack` 扱い） |
| `retrievedAt` | 取得した時刻（UTC の ISO 8601）。実行のたびに更新される |
| `users` | ユーザー ID → 名前のマップ（メンション解決用） |
| `messages` | メッセージの配列（`ts` の昇順） |
| `messages[].id` | **Discord のみ**。メッセージ ID（一意。Discord の重複判定のキー） |
| `messages[].ts` | タイムスタンプ（エポック秒。ビューアが日付・時刻表示に使う。Slack の重複判定のキー） |
| `messages[].time` | `ts` を整形した日時（**UTC**, `YYYY-MM-DD HH:MM:SS`）。人が読むための補助項目で、ビューアは使わない（ビューアは `ts` から JST を計算して表示する） |
| `messages[].name` | 発言者名 |
| `messages[].text` | 本文（Slack は実体参照済み・`<@ID>`／`<url\|text>`、Discord は生テキスト・`<@ID>`／`<@!ID>`） |
| `messages[].files` | 添付ファイルの表示名一覧（添付がある場合のみ） |
| `error` | 取得エラーが起きた場合のみ記録（`{"message": …, "at": …}`） |

重複判定のキーはサービスで異なります（Slack は `ts`、Discord は `id`）。分割保存の突合も
`id` があれば `id`、無ければ `ts` を使います。

## 分割形式

[分割]({{ '/split/' | relative_url }})すると、エントリファイル（例 `general.json`）は **マニフェスト** になり、本体は期間ごとの
**チャンク**（例 `general.2024.json`）に分かれます。

```json
{
  "channel": "general",
  "format": 2,
  "by": "year",
  "service": "discord",
  "users": { "1002": "bob" },
  "chunks": [
    { "file": "general.2024.json", "from": "…", "to": "…",
      "count": 1200, "dates": ["2024/01/15", "…"] }
  ],
  "maxTs": "…",
  "retrievedAt": "…"
}
```

チャンクは `{ "messages": [ … ] }` の形。`users` や `service` はマニフェスト側に持ちます。
`convert/merge.py` で単一形式に戻せます。
