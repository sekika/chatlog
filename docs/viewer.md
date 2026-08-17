---
layout: page
title: ビューア
---

`chatlog.py` が作った JSON を、付属のビューアでそのまま閲覧できます（[デモ]({{ '/demo/' | relative_url }})）。このページでは、まずビューアで**何ができるか・どう表示されるか**（[閲覧](#閲覧)）を説明し、続いて自分のサイトへ**どう配置・設定するか**（[設置](#設置)）を説明します。

## 閲覧

できること:

- チャンネルの切り替え
- 最新日のログを既定表示 ／ **日付一覧**から特定の日へジャンプ ／ **前の日・次の日**への移動
- **全ログ**の表示（分割時は代わりに**年一覧** → その年の全ログ、前の年・次の年への移動）
- 発言の**検索**（一致箇所を強調表示）

本文の描画は JSON の `service` で切り替わります（未指定は `slack`）。

- **Slack**: `& < >` は Slack が実体参照済みなので再エスケープしない。メンション `<@ID>` と Slack 形式リンク `<url|表示テキスト>` を解釈。書式付きメッセージで `blocks`（Slack の `rich_text`）があれば、**太字・斜体・取り消し線・コード・箇条書き／番号付きリスト・引用・コードブロック**を再現して描画する（`blocks` が無いメッセージは `text` を描画）。
- **Discord**: 生テキストなので `& < >` を完全にエスケープ。メンション `<@ID>` / `<@!ID>` を名前解決し、生 URL をリンク化。

`service` はチャンネル単位（JSON 単位）なので、Slack と Discord のチャンネルを 1 つのビューアに混在させても、各 JSON の `service` に従って描画されます。

日付・時刻の表示は**日本時間（JST = UTC+9）に固定**されています（`chat.js` が UTC+9 で計算）。JSON に保存される `time` は UTC ですがビューアは使わず、`ts`（エポック秒）から JST を計算して表示します。分割の期間区切り（年・月）も JST で決まります。

### 取得状況の表示

画面下部のフッタには、その JSON の取得状況が表示されます。

- 正常に取得できている場合は「Data retrieved at &lt;日時&gt;」を表示します（`retrievedAt` を JST で表示）。
- ログ取得時に失敗して JSON に `error` が記録されている場合は、代わりに「Error retrieving at &lt;日時&gt;: &lt;メッセージ&gt;」を強調表示します。表示済みのログは直前まで保存された内容のままで、失敗した時刻とエラー内容（`error.at` / `error.message`）が分かります。次回の取得が成功すると `error` は消え、通常の取得日時表示に戻ります（[取得のタイミングと失敗時の扱い]({{ '/collect/#取得のタイミングと失敗時の扱い' | relative_url }})）。

`retrievedAt` も `error` も持たない場合は、フッタには何も表示されません。

## 設置

ビューアはこのリポジトリの `docs/` とは独立した、任意の静的ファイル公開用フォルダに配置します。`docs/demo/` から `index.html`、`chat.css`、`chat.js` をコピーし、表示するログ JSON も**同じディレクトリ**へ置いてください。

```
viewer/                       # 任意の静的ファイル公開用フォルダ
├── index.html                # docs/demo/index.html をコピーして編集
├── chat.css                  # docs/demo/chat.css をコピー
├── chat.js                   # docs/demo/chat.js をコピー
├── general.json              # 表示するログ
└── random.json
```

### 表示するチャンネルの指定

`index.html` 末尾の `chatLog(...)` に、読み込ませる JSON ファイル名の拡張子を除いた名前を配列で指定します。配列の先頭が最初に表示され、それ以外はチャンネル選択メニューに並びます。チャンネル名に `#` は含めず、JSON のファイル名と正確に一致させてください。

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

1 チャンネルだけなら `chatLog(['general'])` とします。JSON にある `channel` の値ではなく、**実際に置いたファイル名**が読み込み先を決めます。たとえば `chatLog(['team-news'])` は `team-news.json` を取得します。各 JSON の `service`（`slack` / `discord`）はビューアが自動で読み取るため、Slack と Discord のログを同じ画面に混在させても `chatLog` 側でサービスを指定する必要はありません。

### 分割ログの配置

`convert/split.py` で[分割]({{ '/split/' | relative_url }})したログでは、`general.json`（マニフェスト）だけでなく、そこから参照される `general.2024.json` などのチャンクも**すべて同じディレクトリ**へ置いてください。マニフェスト内の `file` のパスを変える場合は、実際の配置に合わせて更新します。

### ローカル確認と公開後のチェック

公開後はビューアの URL を開き、ブラウザの開発者ツールで `<チャンネル名>.json` が 404 になっていないことを確認してください。`file://` で直接 `index.html` を開くと `fetch` が失敗するブラウザがあるため、ローカル確認も HTTP サーバーを使います。

```
cd viewer
python3 -m http.server
# → http://localhost:8000/ を開く
```

### そのほかの編集箇所

`index.html` は末尾の `chatLog(...)` を書き換えるのが最低限の作業ですが、見出しや説明文も公開先に合わせて自由に編集できます。次の箇所はテキストを差し替えても動作に影響しません。

- **`<title>`**（`<head>` 内）: ブラウザのタブや履歴に表示される名前。
- **ヘッダ**（`<header class="site-header">`）: サイト名の `<p class="brand">` と副題の `<p class="subtitle">`。組織名や対象チャンネルの説明に置き換えます。不要なら `<header>` ごと削除しても構いません。
- **フッタ**（`<footer>`）: 説明文（デモではサンプルデータの注記）を自由に書き換えられます。ただし末尾の `<span id="retrieved-at"></span>` は[取得状況](#取得状況の表示)をビューアが自動で埋め込む場所なので、残しておいてください。
- **見た目**: 色やフォントなどの調整は `chat.css` を編集します。

一方、次の要素は `chat.js` / `chat.css` が名前で参照しているため、**id や class、要素そのものは変更・削除しないでください**（表示ラベルの文言だけなら変更可）。

- `<select id="channel-select">`（チャンネル選択）とラベル
- `<button id="show-all">` `<button id="show-dates">`（全ログ・日付一覧）
- `<form id="search-form">` と `<input id="search-input">` `<button id="search-btn">`（検索）
- `<div id="log">`（ログ本文の描画先）と、それを囲む `<div class="log-card">`
- `<span id="retrieved-at">`（取得状況の表示先）

`<script src="chat.js">` と、その下の `chatLog(...)` を呼ぶ `<script>` も必須です。

### アクセス制限が必要な場合

このビューアは認証機能を持たないため、URL を知っていれば誰でも閲覧できます。閲覧者を限定したい場合は、配置先の Web サーバー側で BASIC 認証や Digest 認証などを設定してください。
