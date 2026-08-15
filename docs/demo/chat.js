// coding:utf-8
//
// <チャンネル名>.json を fetch で読み取り、チャットログを表示する。
//
// index.html から次のように呼び出す:
//   chatLog(['general', 'random']);
// 引数はチャンネル名の配列。先頭のチャンネルをデフォルトで表示する。
//
// エントリ JSON は単一形式(messages を持つ)と、分割形式(chunks を持つ
// マニフェスト。convert/split.py が生成)の両方に対応する。
// 本文の描画は JSON の service('slack' / 'discord'。既定 'slack')で切り替える。

// 表示は日本時間(JST = UTC+9)
function jstDate(ts) {
  // ts はエポック秒。JST の YYYY/MM/DD を返す。
  const d = new Date(parseFloat(ts) * 1000);
  const j = new Date(d.getTime() + 9 * 3600 * 1000);
  const y = j.getUTCFullYear();
  const m = String(j.getUTCMonth() + 1).padStart(2, '0');
  const day = String(j.getUTCDate()).padStart(2, '0');
  return y + '/' + m + '/' + day;
}

// JST の YYYY/MM/DD HH:MM:SS を返す(Date またはエポック秒を受け取る)
function jstDateTime(value) {
  const d = (value instanceof Date) ? value : new Date(parseFloat(value) * 1000);
  const j = new Date(d.getTime() + 9 * 3600 * 1000);
  const y = j.getUTCFullYear();
  const m = String(j.getUTCMonth() + 1).padStart(2, '0');
  const day = String(j.getUTCDate()).padStart(2, '0');
  const hh = String(j.getUTCHours()).padStart(2, '0');
  const mm = String(j.getUTCMinutes()).padStart(2, '0');
  const ss = String(j.getUTCSeconds()).padStart(2, '0');
  return y + '/' + m + '/' + day + ' ' + hh + ':' + mm + ':' + ss;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, '&quot;');
}

// Slack のテキストは & < > が既に実体参照へエスケープ済みなので、
// & は再エスケープせず、生の < > (メンション等)だけを実体参照へ変換する。
function escapeAngles(s) {
  return String(s)
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// 1 行分のテキストを HTML に変換する
// users はユーザID→ユーザ名のマップ(メンション解決用、省略可)
// service は 'slack'(既定) か 'discord'。本文のエスケープ規則とメンション記法が異なる。
function convertLine(line, users, service) {
  line = String(line).trim();
  users = users || {};
  service = service || 'slack';

  // 変換済みの <a>/<span> タグをエスケープから守るためのプレースホルダ退避
  const tokens = [];
  function stash(html) {
    tokens.push(html);
    return '\x00' + (tokens.length - 1) + '\x00';
  }

  // ---- Discord ----
  // 本文は生テキスト(& < > は未エスケープ)。メンションは <@ID> / <@!ID>(ID は数字)。
  if (service === 'discord') {
    // メンションを @ユーザ名 に解決して退避(解決できないIDは後段でそのまま表示)
    line = line.replace(/<@!?(\d+)>/g, function (m, id) {
      const name = users[id];
      if (!name) return m;
      return stash('<span class="mention">@' + escapeHtml(name) + '</span>');
    });
    // 生 URL をリンク化して退避(この時点の URL は生テキストなのでエスケープは1回で正しい)
    line = line.replace(/(https?:\/\/[^\s<\x00]+)/g, function (url) {
      return stash('<a href="' + escapeAttr(url) + '">' + escapeHtml(url) + '</a>');
    });
    // 残りの生テキストを & < > 含め完全にエスケープする(未解決の <@ID> はそのまま表示)
    let s = escapeHtml(line);
    // プレースホルダを実際のタグに戻す
    s = s.replace(/\x00(\d+)\x00/g, function (m, i) { return tokens[i]; });
    return s;
  }

  // ---- Slack(既定) ----
  // Slack のメンション <@ユーザID> / <@ユーザID|ラベル> を @ユーザ名 に変換する。
  // 解決できたら青色表示用の <span class="mention"> で囲んで退避する。
  // マップに無いID(退会者など)は変換せず、後段で <@ID> のまま表示する。
  line = line.replace(/<@([A-Z0-9]+)(?:\|[^>]*)?>/g, function (m, id) {
    const name = users[id];
    if (!name) return m;
    return stash('<span class="mention">@' + escapeHtml(name) + '</span>');
  });

  // Slack 形式のリンク <url|表示テキスト> / <url> を通常のリンクにする
  line = line.replace(
    /<((?:https?|ftp|mailto):[^|>\s]+)(?:\|([^>]*))?>/g,
    function (m, url, disp) {
      const text = (disp && disp.length) ? disp : url;
      return stash('<a href="' + escapeAttr(url) + '">' + escapeAngles(text) + '</a>');
    }
  );

  // 残りのテキスト。Slack のテキストは & < > が実体参照へエスケープ済みなので、
  // & は再エスケープせず、生の < > (<@メンション> 等)だけを実体参照化する。
  let s = escapeAngles(line);

  // <> で囲まれていない生の URL もリンク化する
  s = s.replace(/(https?:\/\/[^\s<]+)/g, function (url) {
    return stash('<a href="' + escapeAttr(url) + '">' + escapeHtml(url) + '</a>');
  });

  // プレースホルダを実際のタグに戻す
  s = s.replace(/\x00(\d+)\x00/g, function (m, i) { return tokens[i]; });
  return s;
}

// store から出現する日付(JST の YYYY/MM/DD)を古い順の配列で返す
function collectDates(store) {
  const seen = {};
  (store.messages || []).forEach(function (msg) { seen[jstDate(msg.ts)] = true; });
  return Object.keys(seen).sort();
}

// store(パース済み JSON)とチャンネル名から本文の HTML を組み立てる
// dateFilter を渡すとその日(YYYY/MM/DD)のログだけを表示する。省略時は全ログ。
function renderChannel(store, channel, dateFilter) {
  const messages = (store.messages || []).slice();
  // メンション <@ユーザID> 解決用の id→name マップ(無ければ空)
  const users = store.users || {};
  // 本文の描画方式(slack / discord)。未指定は slack(既存 JSON との後方互換)
  const service = store.service || 'slack';
  // 念のため ts 順(時系列)に並べ替える
  messages.sort(function (a, b) { return parseFloat(a.ts) - parseFloat(b.ts); });

  let html = '<h1>#' + escapeHtml(channel) + ' channel log</h1>\n';
  let author = '';
  let currentDate = '';

  for (const msg of messages) {
    const date = jstDate(msg.ts);
    // 日付が指定されていれば、その日以外のメッセージは飛ばす
    if (dateFilter && date !== dateFilter) continue;
    // 日付が変わったら見出しを出す(#channel YYYY/MM/DD)
    if (date !== currentDate) {
      currentDate = date;
      author = '';
      html += '<h2>#' + escapeHtml(channel) + ' ' + date + '</h2>\n';
    }

    let block = '<div class="msg">';
    // 発言者が変わったときだけ名前を出す
    if (author !== msg.name) {
      author = msg.name;
      block += renderAuthor(author);
    }

    // 本文(改行を含む場合は行ごとに処理)
    const lines = String(msg.text).split('\n');
    for (const line of lines) {
      block += convertLine(line, users, service) + '<br />\n';
    }
    // 添付ファイルがあった場合はファイル名を表示する(本体は取得していない)
    if (Array.isArray(msg.files) && msg.files.length) {
      block += '<div class="attachment">📎 ' +
        msg.files.map(escapeHtml).join(', ') + '</div>\n';
    }
    block += '</div>\n';
    html += block;
  }
  return html;
}

// 正規表現の特殊文字をエスケープする(検索語をそのまま照合するため)
function escapeRegExp(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// convertLine が生成した HTML の「タグの外側のテキスト部分」だけを対象に
// 検索語を <mark> で囲んで強調する。タグ属性やタグ名は書き換えない。
function highlightHtml(html, query) {
  if (!query) return html;
  const re = new RegExp(escapeRegExp(query), 'gi');
  // <...> をキャプチャして分割すると、奇数番目がタグ・偶数番目がテキストになる
  return html.split(/(<[^>]*>)/).map(function (part, i) {
    if (i % 2 === 1) return part; // タグはそのまま
    return part.replace(re, function (m) { return '<mark>' + m + '</mark>'; });
  }).join('');
}

// 検索結果ページの HTML を組み立てる。
// query を含む発言を発言単位で、古い順に一覧表示する。
// 各発言には日付リンクを付け、クリックするとその日のログへ飛べるようにする。
function renderSearch(store, channel, query) {
  const q = String(query || '').trim();
  let html = '<h1>#' + escapeHtml(channel) + ' 検索: ' + escapeHtml(q) + '</h1>\n';
  if (!q) {
    html += '<p>検索語を入力してください。</p>\n';
    return html;
  }
  const users = store.users || {};
  const service = store.service || 'slack';
  const messages = (store.messages || []).slice();
  messages.sort(function (a, b) { return parseFloat(a.ts) - parseFloat(b.ts); });

  const lc = q.toLowerCase();
  const hits = messages.filter(function (msg) {
    return String(msg.text).toLowerCase().indexOf(lc) !== -1;
  });

  if (!hits.length) {
    html += '<p>「' + escapeHtml(q) + '」を含む発言は見つかりませんでした。</p>\n';
    return html;
  }

  html += '<p class="search-count">' + hits.length + ' 件の発言が見つかりました。</p>\n';
  for (const msg of hits) {
    const date = jstDate(msg.ts);
    let block = '<div class="msg search-result">';
    block += '<a href="#" class="date-link search-date" data-date="' +
      escapeAttr(date) + '">' + escapeHtml(date) + '</a> ';
    block += renderAuthor(msg.name);
    const lines = String(msg.text).split('\n');
    for (const line of lines) {
      block += highlightHtml(convertLine(line, users, service), q) + '<br />\n';
    }
    if (Array.isArray(msg.files) && msg.files.length) {
      block += '<div class="attachment">📎 ' +
        msg.files.map(escapeHtml).join(', ') + '</div>\n';
    }
    block += '</div>\n';
    html += block;
  }
  return html;
}

// 現在読み込んでいるチャンネルの状態(日付の絞り込み表示に使う)
let currentStore = null;
let currentChannel = '';
// 分割形式のときのマニフェスト(単一形式のときは null)。
let currentManifest = null;
// 読み込んだチャンク(<channel>.<period>.json の messages 配列)のキャッシュ。file 名をキーにする。
let chunkCache = {};

// 発言者名を表示する HTML を返す。
function renderAuthor(name) {
  return '<span class="author">' + escapeHtml(name) + ':</span> ';
}

// ===== 分割(マニフェスト)形式のサポート =====

// マニフェストの全チャンクの日付(JST YYYY/MM/DD)を古い順・重複なしで返す
function manifestDates(manifest) {
  const seen = {};
  (manifest.chunks || []).forEach(function (c) {
    (c.dates || []).forEach(function (d) { seen[d] = true; });
  });
  return Object.keys(seen).sort();
}

// マニフェストから年(YYYY)を古い順・重複なしで返す
function manifestYears(manifest) {
  const seen = {};
  manifestDates(manifest).forEach(function (d) { seen[d.slice(0, 4)] = true; });
  return Object.keys(seen).sort();
}

// 指定日(YYYY/MM/DD)を含むチャンクのメタ情報を返す
function chunksForDate(manifest, date) {
  return (manifest.chunks || []).filter(function (c) {
    return (c.dates || []).indexOf(date) !== -1;
  });
}

// 指定年(YYYY)のメッセージを含むチャンクのメタ情報を返す
function chunksForYear(manifest, year) {
  return (manifest.chunks || []).filter(function (c) {
    return (c.dates || []).some(function (d) { return d.slice(0, 4) === year; });
  });
}

// チャンク(<channel>.<period>.json)を読み込んで messages 配列を返す。
// 過去チャンクは不変なのでキャッシュ可。更新されうる最新チャンクは
// count をクエリに付けてキャッシュバストする。
function fetchChunk(meta) {
  if (chunkCache[meta.file]) return Promise.resolve(chunkCache[meta.file]);
  const url = meta.file + '?v=' + encodeURIComponent(meta.count);
  return fetch(url)
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(function (data) {
      const msgs = data.messages || [];
      chunkCache[meta.file] = msgs;
      return msgs;
    });
}

// 複数チャンクを読み込み、messages を結合して返す
function fetchChunks(metas) {
  return Promise.all(metas.map(fetchChunk)).then(function (arrays) {
    return arrays.reduce(function (a, b) { return a.concat(b); }, []);
  });
}

// 全チャンクを読み込む(検索用)
function fetchAllChunks(manifest) {
  return fetchChunks(manifest.chunks || []);
}

// renderChannel / renderSearch に渡す store を組み立てる。
// users はマニフェスト共通、messages は読み込んだぶんだけ。
function buildStore(messages) {
  return {
    channel: currentChannel,
    users: (currentManifest && currentManifest.users) || {},
    service: (currentManifest && currentManifest.service) || 'slack',
    messages: messages,
  };
}

// 年一覧ページの HTML を組み立てる(日付一覧と同じ見た目、項目は年)。
// これから年が増えるので、新しい年が上に来るよう新しい順で並べる。
function renderYearList(manifest, channel) {
  const years = manifestYears(manifest).slice().reverse();
  let html = '<h1>#' + escapeHtml(channel) + ' 年一覧</h1>\n';
  if (!years.length) {
    html += '<p>ログがありません。</p>\n';
    return html;
  }
  html += '<ul class="date-list">\n';
  years.forEach(function (y) {
    html += '<li><a href="#" class="year-link" data-year="' +
      escapeAttr(y) + '">' + escapeHtml(y) + '</a></li>\n';
  });
  html += '</ul>\n';
  return html;
}

// 年表示で使う、前の年/次の年への移動バーの HTML を組み立てる(日付の前後移動と同じ作り)。
function renderYearNav(manifest, year) {
  const years = manifestYears(manifest);
  const idx = years.indexOf(year);
  const prev = idx > 0 ? years[idx - 1] : null;                    // 前の年(古い方)
  const next = (idx >= 0 && idx < years.length - 1) ? years[idx + 1] : null; // 次の年(新しい方)

  let html = '<div class="day-nav">';
  if (prev) {
    html += '<a href="#" class="year-link nav-prev" data-year="' + escapeAttr(prev) +
      '">← 前の年 (' + escapeHtml(prev) + ')</a>';
  } else {
    html += '<span class="nav-disabled">← 前の年</span>';
  }
  html += '<a href="#" class="to-year-list nav-list">年一覧</a>';
  if (next) {
    html += '<a href="#" class="year-link nav-next" data-year="' + escapeAttr(next) +
      '">次の年 (' + escapeHtml(next) + ') →</a>';
  } else {
    html += '<span class="nav-disabled">次の年 →</span>';
  }
  html += '</div>\n';
  return html;
}

// 日付一覧ページの HTML を組み立てる。日付はクリックできるリンクにする。
// これから日付が増えるので、新しい日付が上に来るよう新しい順で並べる。
function renderDateList(store, channel, dateList) {
  const dates = (dateList || collectDates(store)).slice().reverse();
  let html = '<h1>#' + escapeHtml(channel) + ' 日付一覧</h1>\n';
  if (!dates.length) {
    html += '<p>ログがありません。</p>\n';
    return html;
  }
  html += '<ul class="date-list">\n';
  dates.forEach(function (d) {
    html += '<li><a href="#" class="date-link" data-date="' +
      escapeAttr(d) + '">' + escapeHtml(d) + '</a></li>\n';
  });
  html += '</ul>\n';
  return html;
}

// 1日分の表示で使う、前の日/次の日への移動バーの HTML を組み立てる。
// log が存在する日だけを対象にする(collectDates は古い順)。
function renderDayNav(store, date, dateList) {
  const dates = dateList || collectDates(store);
  const idx = dates.indexOf(date);
  const prev = idx > 0 ? dates[idx - 1] : null;                      // 前の日(古い方)
  const next = (idx >= 0 && idx < dates.length - 1) ? dates[idx + 1] : null; // 次の日(新しい方)

  let html = '<div class="day-nav">';
  if (prev) {
    html += '<a href="#" class="date-link nav-prev" data-date="' + escapeAttr(prev) +
      '">← 前の日 (' + escapeHtml(prev) + ')</a>';
  } else {
    html += '<span class="nav-disabled">← 前の日</span>';
  }
  html += '<a href="#" class="to-date-list nav-list">日付一覧</a>';
  if (next) {
    html += '<a href="#" class="date-link nav-next" data-date="' + escapeAttr(next) +
      '">次の日 (' + escapeHtml(next) + ') →</a>';
  } else {
    html += '<span class="nav-disabled">次の日 →</span>';
  }
  html += '</div>\n';
  return html;
}

// ログ本体を描画する。date を渡すとその日のログだけ、省略すると全ログ。
function displayLog(date) {
  // 分割形式のときは専用処理(必要なチャンクだけ非同期に読み込む)
  if (currentManifest) { displayLogSplit(date); return; }
  const logEl = document.getElementById('log');
  let html = renderChannel(currentStore, currentChannel, date || null);
  if (date) {
    // 1日分表示のときは前後の日へ移動できるバーを上下に付ける
    const nav = renderDayNav(currentStore, date);
    html = nav + html + nav;
  }
  logEl.innerHTML = html;
  setActiveNav(date ? null : 'show-all');
}

// 分割形式:指定日のチャンクだけ読み込んでその日のログを表示する。
// date 省略時(「年一覧」ボタン)は年一覧を表示する(全チャンク一括読み込みを避ける)。
function displayLogSplit(date) {
  const logEl = document.getElementById('log');
  if (!date) { showYearList(); return; }
  const metas = chunksForDate(currentManifest, date);
  logEl.textContent = '読み込み中...';
  fetchChunks(metas).then(function (messages) {
    const store = buildStore(messages);
    // 前後の日移動はマニフェストの全日付で計算する(別チャンクの日にも飛べる)
    const dates = manifestDates(currentManifest);
    const nav = renderDayNav(store, date, dates);
    logEl.innerHTML = nav + renderChannel(store, currentChannel, date) + nav;
    setActiveNav(null);
  }).catch(function (err) {
    logEl.innerHTML = '<p class="text-danger">読み込みに失敗しました: ' +
      escapeHtml(err.message) + '</p>';
  });
}

// 分割形式:指定年の全チャンクを読み込み、その年の全ログ(全日付)を表示する。
function displayYear(year) {
  const logEl = document.getElementById('log');
  const metas = chunksForYear(currentManifest, year);
  logEl.textContent = '読み込み中...';
  fetchChunks(metas).then(function (messages) {
    const store = buildStore(messages);
    // 前の年/次の年へ移動できるバーを上下に付ける
    const nav = renderYearNav(currentManifest, year);
    logEl.innerHTML = nav + renderChannel(store, currentChannel) + nav;
    setActiveNav(null);
    window.scrollTo(0, 0);
  }).catch(function (err) {
    logEl.innerHTML = '<p class="text-danger">読み込みに失敗しました: ' +
      escapeHtml(err.message) + '</p>';
  });
}

// 年一覧ページを表示する(分割形式のみ)
function showYearList() {
  const logEl = document.getElementById('log');
  logEl.innerHTML = renderYearList(currentManifest, currentChannel);
  setActiveNav('show-all');
}

// 日付一覧ページを表示する
function showDateList() {
  const logEl = document.getElementById('log');
  if (currentManifest) {
    // 分割形式では日付はマニフェストから取れるのでチャンクを読まない
    logEl.innerHTML = renderDateList(null, currentChannel, manifestDates(currentManifest));
  } else {
    logEl.innerHTML = renderDateList(currentStore, currentChannel);
  }
  setActiveNav('show-dates');
}

// 検索結果ページを表示する
function showSearch(query) {
  const logEl = document.getElementById('log');
  if (currentManifest) {
    // 検索は全メッセージが必要なので、全チャンクを読み込んでから実行する
    logEl.textContent = '読み込み中...';
    fetchAllChunks(currentManifest).then(function (messages) {
      logEl.innerHTML = renderSearch(buildStore(messages), currentChannel, query);
      setActiveNav(null);
      window.scrollTo(0, 0);
    }).catch(function (err) {
      logEl.innerHTML = '<p class="text-danger">読み込みに失敗しました: ' +
        escapeHtml(err.message) + '</p>';
    });
    return;
  }
  if (!currentStore) return;
  logEl.innerHTML = renderSearch(currentStore, currentChannel, query);
  setActiveNav(null);
  window.scrollTo(0, 0);
}

// フッタに取得状況(JST)を表示する。
// - 取得エラーが記録されている場合(ログ取得スクリプトが store.error に記録)は
//   「Error retrieving at <日時>: <メッセージ>」を強調表示する。
// - 正常時は「Data retrieved at <日時>」を表示する。
// - どちらも記録されていない古い JSON では何も表示しない。
function showRetrievedAt(store) {
  const el = document.getElementById('retrieved-at');
  if (!el) return;
  el.classList.remove('retrieve-error');
  el.textContent = '';
  if (store && store.error) {
    const at = store.error.at ? jstDateTime(new Date(store.error.at)) : '';
    el.textContent = 'Error retrieving at ' + at + ': ' + (store.error.message || '');
    el.classList.add('retrieve-error');
  } else if (store && store.retrievedAt) {
    el.innerHTML = 'Data retrieved at ' + jstDateTime(new Date(store.retrievedAt)) + ' by <a href="https://sekika.github.io/chatlog/">chatlog</a>';
  }
}

// ナビゲーションボタンの選択状態を切り替える
function setActiveNav(activeId) {
  ['show-all', 'show-dates'].forEach(function (id) {
    const btn = document.getElementById(id);
    if (btn) btn.classList.toggle('active', id === activeId);
  });
}

// 「全ログ」ボタンの表示を形式で切り替える(分割時は「年一覧」)
function updateShowAllLabel(isSplit) {
  const btn = document.getElementById('show-all');
  if (btn) btn.textContent = isSplit ? '年一覧' : '全ログ';
}

// 指定チャンネルの JSON を読み込んで表示する。
// エントリは単一形式(messages を持つ)と分割形式(chunks を持つマニフェスト)の両対応。
function loadChannel(channel) {
  const logEl = document.getElementById('log');
  logEl.textContent = '読み込み中...';
  fetch(channel + '.json', { cache: 'no-store' })
    .then(function (res) {
      if (!res.ok) {
        throw new Error('HTTP ' + res.status);
      }
      return res.json();
    })
    .then(function (entry) {
      currentChannel = channel;
      chunkCache = {};
      // JSON に記録された取得状況(取得時刻またはエラー)をフッタに表示する(slacklog.py が記録)
      showRetrievedAt(entry);
      if (entry.chunks) {
        // 分割形式(マニフェスト)。チャンクは必要になったときに読み込む。
        currentManifest = entry;
        currentStore = null;
        updateShowAllLabel(true);
        const dates = manifestDates(entry);
        if (dates.length) {
          displayLog(dates[dates.length - 1]);
        } else {
          logEl.innerHTML = renderChannel(buildStore([]), channel);
        }
      } else {
        // 単一形式(従来)
        currentManifest = null;
        currentStore = entry;
        updateShowAllLabel(false);
        // デフォルトは最新日のログを表示(ログが無ければ全ログ)
        const dates = collectDates(entry);
        if (dates.length) {
          displayLog(dates[dates.length - 1]);
        } else {
          displayLog();
        }
      }
    })
    .catch(function (err) {
      logEl.innerHTML = '<p class="text-danger">' + escapeHtml(channel) +
        '.json の読み込みに失敗しました: ' + escapeHtml(err.message) + '</p>';
    });
}

// エントリポイント。index.html から channels(チャンネル名の配列)を渡して呼ぶ。
function chatLog(channels) {
  const select = document.getElementById('channel-select');
  // チャンネル選択用の <option> を生成する
  select.innerHTML = '';
  channels.forEach(function (ch) {
    const opt = document.createElement('option');
    opt.value = ch;
    opt.textContent = '#' + ch;
    select.appendChild(opt);
  });
  select.addEventListener('change', function () {
    loadChannel(select.value);
  });

  // 「全ログ」ボタン:全ログを表示(分割形式では「年一覧」を表示)
  const showAllBtn = document.getElementById('show-all');
  if (showAllBtn) {
    showAllBtn.addEventListener('click', function () { displayLog(); });
  }
  // 「日付一覧」ボタン:日付一覧ページを表示
  const showDatesBtn = document.getElementById('show-dates');
  if (showDatesBtn) {
    showDatesBtn.addEventListener('click', showDateList);
  }
  // 検索フォーム:入力された語を含む発言を発言単位で一覧表示する
  const searchForm = document.getElementById('search-form');
  const searchInput = document.getElementById('search-input');
  if (searchForm && searchInput) {
    searchForm.addEventListener('submit', function (e) {
      e.preventDefault();
      showSearch(searchInput.value);
    });
  }
  // 日付一覧内の日付リンクをクリックしたら、その日のログを表示する(イベント委譲)
  const logEl = document.getElementById('log');
  if (logEl) {
    logEl.addEventListener('click', function (e) {
      // 「日付一覧」へ戻るリンク
      const back = e.target.closest('.to-date-list');
      if (back) {
        e.preventDefault();
        showDateList();
        return;
      }
      // 「年一覧」へ戻るリンク(分割形式)
      const yback = e.target.closest('.to-year-list');
      if (yback) {
        e.preventDefault();
        showYearList();
        return;
      }
      // 年リンク(年一覧)をクリックしたらその年の全ログを表示する(分割形式)
      const ylink = e.target.closest('.year-link');
      if (ylink) {
        e.preventDefault();
        displayYear(ylink.getAttribute('data-year'));
        window.scrollTo(0, 0);
        return;
      }
      // 日付リンク(一覧・前後移動)をクリックしたらその日のログを表示する
      const link = e.target.closest('.date-link');
      if (!link) return;
      e.preventDefault();
      displayLog(link.getAttribute('data-date'));
      // ページ先頭に戻して上部の移動バーを見せる
      window.scrollTo(0, 0);
    });
  }

  // デフォルトは先頭のチャンネル
  select.value = channels[0];
  loadChannel(channels[0]);
}

// Node からの単体テスト用(ブラウザでは無視される)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { convertLine, renderChannel, jstDate, jstDateTime, collectDates, renderDateList, renderDayNav, renderSearch, highlightHtml, manifestDates, manifestYears, chunksForDate, chunksForYear, renderYearList, renderYearNav };
}
