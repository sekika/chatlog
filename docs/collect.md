---
layout: page
title: 取得
---

`chatlog.py` で Slack / Discord のチャンネルログを取得し、JSON に蓄積します。まだの場合は
[トップページ]({{ '/' | relative_url }})の手順で `git clone` してください。

## 動作環境

- Python 3 系
- Slack を取得する場合: Slack API トークン（下記スコープ）。追加ライブラリは不要。
- Discord を取得する場合: Discord Bot トークンと `discord` ライブラリ
  （`python3 -m pip install discord`）。`discord` は Discord 取得時にのみ読み込むので、
  Slack だけ使うなら未インストールで構いません。

## 使い方

```
python3 chatlog.py <出力JSONファイル> <チャンネル名> <設定JSONファイル>
```

Slack / Discord のどちらを取得するかは、設定ファイルの `service` で決まります（引数は共通）。

| 引数 | 説明 |
| --- | --- |
| 出力JSONファイル | ログを蓄積する JSON のパス（既存があれば読み込んで追記） |
| チャンネル名 | 取得するチャンネル名（Slack は `#` 不要、Discord は表示名そのまま） |
| 設定JSONファイル | 下記の設定ファイルへのパス |

実行例:

```
python3 chatlog.py general.json general config.json
```

`general` チャンネルの新規メッセージ（前回保存分より後）を取得して `general.json` に追記します。
出力ファイルが無ければチャンネルの最古から全件取得します。チャンネル名とファイル名は独立して
いるので、日本語チャンネル名を英語ファイル名に振り分けてもかまいません。

## 設定ファイル (config.json)

**`service` は必須**です。記載が無い、または `slack`/`discord` 以外だと、その旨を表示して
終了します（既定では動かしません）。

Slack の例:

```json
{
  "service": "slack",
  "token": "xoxb-xxxxxxxx",
  "overlap_seconds": 86400
}
```

Discord の例:

```json
{
  "service": "discord",
  "token": "（Discord Bot トークン）",
  "overlap_seconds": 86400
}
```

| キー | 説明 |
| --- | --- |
| `service` | 取得元。`"slack"` または `"discord"`。**必須** |
| `token` | API トークン（Slack は Bot トークン `xoxb-` 推奨、Discord は Bot トークン） |
| `overlap_seconds` | 取りこぼし対策のマージン（秒）。保存済みの最新メッセージからこの秒数だけさかのぼって取得し直す。**省略可**（既定 `86400` = 1 日） |

## Slack の準備

Slack の Web API（`conversations.*`）を使います。

1. [Slack API: Your Apps](https://api.slack.com/apps) で **Create New App → From scratch**。
2. **OAuth & Permissions** の **Bot Token Scopes** に次を追加:
   `channels:read` / `channels:history` / `groups:read` / `groups:history` / `users:read`
   （パブリックチャンネルのみなら `groups:*` は不要）。
3. **Install to Workspace** して **Bot User OAuth Token**（`xoxb-`）を取得し、`token` に設定。
4. 取得したいチャンネルに Bot を招待する（`/invite @アプリ名`）。Bot が
   メンバーでないと履歴を取得できません。

チャンネル名は Slack 上の名前と完全一致で指定します。コマンド引数には先頭の `#` を付けません
（例: `#general` は `general`）。アーカイブ済みチャンネルは取得対象外です。

## Discord の準備

`discord` ライブラリで取得します。

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリ（Bot）を作成。
2. **Bot** 設定で **MESSAGE CONTENT INTENT** を **ON**（本文の取得に必須）。
3. Bot トークンを取得し、`token` に設定。
4. Bot を対象サーバーに招待し、対象チャンネルの
   **View Channel / Read Message History** 権限を与える。
5. `python3 -m pip install discord`。

コマンド引数のチャンネル名は表示名と完全一致させます（先頭の `#` は付けません）。現在の実装は
Bot が参加している全サーバーから最初に一致したテキストチャンネルを選ぶため、複数サーバーに
同名チャンネルがある場合は意図しないチャンネルを取得するおそれがあります。名前を一意にするか、
Bot を対象サーバーだけに参加させてください。

## 取得のタイミングと失敗時の扱い

このツールはコマンドを実行した時点で取得します。常駐や定期実行は行わないため、継続して蓄積
するには cron、launchd、GitHub Actions などで利用者が実行をスケジュールします。

- 初回実行は保存済みデータがないため、取得可能な最古のメッセージから全件を読み込みます。大きな
  チャンネルでは時間がかかることがあります。
- 2 回目以降は、最後に保存したメッセージの `overlap_seconds` 秒前から再取得し、重複を除いて
  追記します。既に保存した同一メッセージは重複として保持するため、投稿後の編集は反映しません。
- API 取得中に失敗すると終了コード 1 で終了し、出力 JSON の `error` に時刻とエラー内容を記録します。
  それまで保存済みのログは残ります。成功した次回実行時に `error` は消え、`retrievedAt` が更新されます。

保存先の親ディレクトリはあらかじめ作成してください。出力 JSON のファイル名は任意ですが、
ビューアで公開する際は[ビューア]({{ '/viewer/' | relative_url }})のとおり `chatLog(...)` の名前と合わせます。

ログが大きくなったら **[分割・統合]({{ '/split/' | relative_url }})** で初期表示を速くできます。
