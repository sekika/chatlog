---
layout: page
title: chatlog
---

**Slack / Discord のチャンネルログを取得して JSON に蓄積し、ブラウザで閲覧するツール。**
差分取得で少しずつ追記していき、ログが大きくなったらファイルの分割・統合もできます。

- ソース: [github.com/sekika/chatlog](https://github.com/sekika/chatlog)
- **ライブデモ: [デモを開く](demo/)**（`#general` は Discord、`#random` は Slack のサンプルデータ）

---

## 特徴

- **Slack と Discord の両方**に対応（設定ファイルの `service` で選択）。
- 保存済みの**最新メッセージ以降だけを差分取得**。実行のたびに差分だけが追記される。
- 添付ファイルは**ファイル名だけ**を記録（本体は取得しない）。
- ブラウザ用ビューア付き（チャンネル切替・日付ジャンプ・全ログ・検索）。
- ログが大きくなったら**分割**でき、初期表示が速くなる（いつでも統合して元に戻せる＝可逆）。
- パッケージ不要。`chatlog.py` を直接コマンドから実行するだけ。

## 動作環境

- Python 3 系
- Slack を取得する場合: Slack API トークン（下記スコープ）。追加ライブラリは不要。
- Discord を取得する場合: Discord Bot トークンと `discord` ライブラリ
  （`python3 -m pip install discord`）。`discord` は Discord 取得時にのみ読み込むので、
  Slack だけ使うなら未インストールで構いません。

## インストール

```
git clone https://github.com/sekika/chatlog.git
cd chatlog
```

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
ビューアで公開する際は「ビューア」節のとおり `chatLog(...)` の名前と合わせます。

## ログの分割・統合 (convert/)

チャンネルの JSON が大きくなったら分割できます。日付・年ごとに必要なぶんだけ読み込むので
**ビューアの初期表示が速くなり**、`chatlog.py` の追記も軽くなります（過去ぶんのチャンクは
変化しなくなる）。分割は任意で、いつでも元に戻せます（可逆）。ビューアは分割形式にも対応します。

```
python3 convert/split.py <JSONファイル> [--by year|month] [--force]
python3 convert/merge.py <JSONファイル> [--keep-chunks]
```

| コマンド | 説明 |
| --- | --- |
| `split.py` | 単一形式のファイルを、マニフェスト＋期間チャンクに分割する |
| `split.py --by year\|month` | 分割の粒度（既定は年単位）。期間は JST で決める |
| `split.py --force` | 既に分割済みでも、粒度を変えて分割し直す |
| `merge.py` | 分割した JSON を 1 ファイルに統合して元に戻す |
| `merge.py --keep-chunks` | 統合してもチャンクファイルを消さずに残す |

分割した状態でも `chatlog.py` はそのまま実行でき、差分を追記できます（差分取得に必要な最近の
チャンクと、変更のあった期間のチャンク・マニフェストだけを読み書きします）。

## ビューア

`chatlog.py` が作った JSON を、付属のビューアでそのまま閲覧できます（[デモ](demo/)）。
ビューアはこのリポジトリの `docs/` とは独立した、任意の静的ファイル公開用フォルダに配置します。
`docs/demo/` から `index.html`、`chat.css`、`chat.js` をコピーし、表示するログ JSON も**同じ
ディレクトリ**へ置いてください。

```
viewer/                       # 任意の静的ファイル公開用フォルダ
├── index.html                # docs/demo/index.html をコピーして編集
├── chat.css                  # docs/demo/chat.css をコピー
├── chat.js                   # docs/demo/chat.js をコピー
├── general.json              # 表示するログ
└── random.json
```

`index.html` 末尾の `chatLog(...)` に、読み込ませる JSON ファイル名の拡張子を除いた名前を
配列で指定します。配列の先頭が最初に表示され、それ以外はチャンネル選択メニューに並びます。
チャンネル名に `#` は含めず、JSON のファイル名と正確に一致させてください。

```html
<script src="chat.js"></script>
<script>
  // general.json を初期表示し、random.json も選択可能にする。
  chatLog(['general', 'random']);
</script>
```

たとえば `team-news.json` と `雑談.json` を公開する場合は、次のように指定します。

```html
<script>
  // #team-news を初期表示。#雑談 は選択メニューから開ける。
  chatLog(['team-news', '雑談']);
</script>
```

1 チャンネルだけなら `chatLog(['general'])` とします。JSON にある `channel` の値ではなく、
**実際に置いたファイル名**が読み込み先を決めます。たとえば `chatLog(['team-news'])` は
`team-news.json` を取得します。各 JSON の `service`（`slack` / `discord`）はビューアが
自動で読み取るため、Slack と Discord のログを同じ画面に混在させても `chatLog` 側で
サービスを指定する必要はありません。

`convert/split.py` で分割したログでは、`general.json`（マニフェスト）だけでなく、そこから
参照される `general.2024.json` などのチャンクも **すべて同じディレクトリ**へ置いてください。
マニフェスト内の `file` のパスを変える場合は、実際の配置に合わせて更新します。

公開後はビューアの URL を開き、ブラウザの開発者ツールで `<チャンネル名>.json` が 404 に
なっていないことを確認してください。`file://` で直接 `index.html` を開くと `fetch` が失敗する
ブラウザがあるため、ローカル確認も HTTP サーバーを使います。

```
cd viewer
python3 -m http.server
# → http://localhost:8000/ を開く
```

できること:

- チャンネルの切り替え
- 最新日のログを既定表示 ／ **日付一覧**から特定の日へジャンプ ／ **前の日・次の日**への移動
- **全ログ**の表示（分割時は代わりに **年一覧** → その年の全ログ、前の年・次の年への移動）
- 発言の**検索**（一致箇所を強調表示）

本文の描画は JSON の `service` で切り替わります（未指定は `slack`）。

- **Slack**: `& < >` は Slack が実体参照済みなので再エスケープしない。メンション `<@ID>` と
  Slack 形式リンク `<url|表示テキスト>` を解釈。
- **Discord**: 生テキストなので `& < >` を完全にエスケープ。メンション `<@ID>` / `<@!ID>` を
  名前解決し、生 URL をリンク化。

`service` はチャンネル単位（JSON 単位）なので、Slack と Discord のチャンネルを 1 つのビューアに
混在させても、各 JSON の `service` に従って描画されます。

### 取得対象の範囲

取得するのは通常のチャンネル履歴の本文・投稿者・時刻・添付ファイル名です。添付ファイルの本体は
ダウンロードしません。Slack のスレッド返信は取得しません（スレッドの親メッセージのみが対象です）。
絵文字リアクション、ピン留め、投稿の編集履歴、削除済みメッセージ、埋め込み表示なども保存・再現
しません。ビューアは保存された本文を簡易表示するもので、Slack / Discord の画面を完全に再現する
ものではありません。

## JSON の形式

### 単一形式

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
| `messages[].time` | `ts` を整形した日時（UTC, `YYYY-MM-DD HH:MM:SS`） |
| `messages[].name` | 発言者名 |
| `messages[].text` | 本文（Slack は実体参照済み・`<@ID>`／`<url\|text>`、Discord は生テキスト・`<@ID>`／`<@!ID>`） |
| `messages[].files` | 添付ファイルの表示名一覧（添付がある場合のみ） |
| `error` | 取得エラーが起きた場合のみ記録（`{"message": …, "at": …}`） |

重複判定のキーはサービスで異なります（Slack は `ts`、Discord は `id`）。分割保存の突合も
`id` があれば `id`、無ければ `ts` を使います。

### 分割形式

分割すると、エントリファイル（例 `general.json`）は **マニフェスト** になり、本体は期間ごとの
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
