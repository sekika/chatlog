# coding:utf-8
#!/usr/bin/env python3

# chatlog.py - Slack / Discord のチャンネルログを取得して JSON に蓄積する。
#   python3 chatlog.py <出力JSONファイル> <チャンネル名> <設定JSONファイル>
#
# 取得元(slack / discord)は設定ファイルの "service" で選ぶ(必須。無ければ終了する)。
# 出力 JSON に保存済みの最新メッセージ以降だけを差分取得するので、実行するたびに
# 差分だけが追記される。出力 JSON が無い(初回)場合はチャンネルの最古から全て取得する。
# 重複排除のキーは Slack が ts、Discord が id。期間が重なって複数回実行しても二重保存されない。
# 生成した JSON は付属のビューア(demo/index.html)でそのまま閲覧でき、ログが大きくなったら
# convert/split.py で分割できる。

from datetime import *
import os
import sys
import time
import urllib.parse
import urllib.request
import json


# 表示・分割は日本時間(JST = UTC+9)基準。convert/split.py と同じ期間・日付の決め方にする。
JST = timezone(timedelta(hours=9))


""" Slack Web API 関連のグローバル変数 """
# 旧 channels.* API は廃止されたため conversations.* API を使用する
api_base_url = "https://slack.com/api/"
api_channel_history_url = api_base_url + "conversations.history"
api_channel_info_url = api_base_url + "conversations.info"
api_channel_list_url = api_base_url + "conversations.list"
api_channel_members_url = api_base_url + "conversations.members"
api_user_list_url = api_base_url + "users.list"

# 取りこぼし対策のマージン(秒)の既定値。
# 保存済みの最新メッセージからこの秒数だけさかのぼった時点を取得の起点にする。
# サービス側の反映遅延やメッセージ可視化順の前後で前回取り切れなかったメッセージを拾い直すため。
# 重なった分は重複排除(ts/id)で弾かれるので、二重保存にはならない。
# config.json の "overlap_seconds" で上書きできる(未指定ならこの既定値を使う)。
DEFAULT_OVERLAP_SECONDS = 86400  # 1 日ぶんさかのぼる(安全側に大きめ)

now = datetime.now()

def main(filename, channel_name, path_to_configure ):

  notice_config = json_parse(path_to_configure)

  # 取得元サービス(slack / discord)は config.json で明示する。
  # 記載が無ければ、その旨を表示して終了する(既定では動かさない)。
  service = notice_config.get('service')
  if service is None:
    sys.stderr.write(
      "config error: \"service\" is not specified in " + path_to_configure
      + " (set \"service\": \"slack\" or \"discord\")\n")
    sys.exit(1)
  if service not in ('slack', 'discord'):
    sys.stderr.write(
      "config error: unknown service " + repr(service) + " in " + path_to_configure
      + " (use \"slack\" or \"discord\")\n")
    sys.exit(1)

  token = notice_config['token']
  # 取りこぼし対策のマージン(秒)。config.json で指定が無ければ既定値を使う。
  overlap_seconds = notice_config.get('overlap_seconds', DEFAULT_OVERLAP_SECONDS)

  # 既存の JSON を読み込み(無ければ新規)。
  # 取得に失敗してもエラー情報を記録できるよう、取得より先に読み込む。
  # 分割形式(マニフェスト)なら差分取得に必要なチャンクだけ読み込む(overlap_seconds を使う)。
  store = load_store(filename, channel_name, overlap_seconds)
  # どの取得元で作った JSON かを常に記録する(ビューアが描画方式の切替に使う)。
  store['service'] = service

  try:
    # サービスごとに取得経路を分ける。追記・重複排除の作法だけが異なり、
    # 保存(単一/分割)・overlap・users マップの扱いは共通。
    if service == 'slack':
      added = fetch_slack(store, token, channel_name, overlap_seconds)
    else:
      added = fetch_discord(store, token, channel_name, overlap_seconds)

    # 取得に成功したので取得時刻(UTC の ISO 8601)を記録し、過去のエラー情報は消す。
    # フッタに「Data retrieved at ...」として表示される。
    store['retrievedAt'] = datetime.now(UTC).replace(microsecond=0).isoformat()
    store.pop('error', None)

  except Exception as e:
    # 取得中にエラーが発生した。エラー内容と時刻を JSON に記録して保存し、異常終了する。
    # フッタには「Error retrieving at ...: (メッセージ)」として強調表示される。
    store['error'] = {
      'message': str(e),
      'at': datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    save_store(filename, store)
    sys.stderr.write("Error retrieving: " + str(e) + "\n")
    sys.exit(1)

################### ログの保存 #########################

  # 実行のたびに取得時刻(retrievedAt)を更新するため、常に JSON を書き出す。
  # 新規メッセージがあった場合のみ ts 順に並べ替える。
  if added > 0:
    store['messages'].sort(key=lambda m: float(m['ts']))
  save_store(filename, store)

########################################################

# Slack Web API からチャンネル履歴を取得し、store に差分を追記して追加件数を返す。
# 重複排除は ts(Slack のメッセージ・タイムスタンプ)で行う。
def fetch_slack(store, token, channel_name, overlap_seconds):
  # user一覧を取得
  users = get_users_info(token)
  # メンション <@ユーザID> を @ユーザ名 に解決するための id→name マップ
  # (チャンネルメンバーに限らず全ユーザを対象にする)
  users_map = {u['id']: u.get('name') for u in users if u.get('name')}
  # チャンネル名からチャンネルを検索
  channel_list = find_channel(token, channel_name)
  if not channel_list:
    raise RuntimeError("channel not found: " + channel_name)
  c_id = channel_list[0]['id']

  # conversations.info はメンバー一覧を返さないので conversations.members で取得する
  member_ids = get_channel_members(token, c_id)

  # チャンネル内のユーザの詳細取得
  channel_users_list = []
  for user in users:
    if user['id'] in member_ids:
      channel_users_list.append(user)

  # ts で重複を排除する
  seen_ts = set(msg['ts'] for msg in store['messages'] if 'ts' in msg)

  # 出力 JSON に保存済みの最新メッセージから overlap_seconds だけさかのぼった時点を起点に、
  # それ以降を全て取得する。マージンぶんは既存メッセージと重なるが、重複は seen_ts で排除する。
  # まだ何も保存されていなければ(oldest_ts=0)、チャンネルの最古から全て取得する。
  if store['messages']:
    oldest_ts = max(float(msg['ts']) for msg in store['messages']) - overlap_seconds
    if oldest_ts < 0:
      oldest_ts = 0
  else:
    oldest_ts = 0
  latest_ts = time.mktime(now.timetuple())

  history = get_channel_history(token, c_id, oldest_ts, latest_ts)

  # id→name マップを更新する(退会したユーザ名も残せるよう既存に上書き)
  store.setdefault('users', {})
  for uid, uname in users_map.items():
    if store['users'].get(uid) != uname:
      store['users'][uid] = uname

  added = 0
  for msg in history:
    ts = msg.get('ts')
    if ts is None or ts in seen_ts:
      continue # 既に保存済み、または ts の無いメッセージはスキップ
    seen_ts.add(ts)

    dt = datetime.fromtimestamp(float(ts), UTC)
    if 'user' in msg:
      user = find_user(token, msg['user'], channel_users_list)
      if not isinstance(user, type(None)):
        name = user['name']
      else: # 既に存在しないユーザの場合
        name = msg['user']
      text = msg.get('text', '')
    elif 'attachments' in msg:
      # プラグインが投げてるjsonフォーマットはプラグインごとに違うので、とりあえず中身全部つっこむ
      name = "PLUGIN"
      text = str(msg['attachments'])
    else:
      # よくわからないメッセージはとりあえず突っ込む
      name = "UNKNOWN"
      text = str(msg.get('attachments'))

    # 添付ファイル(アップロードされたファイル)は取得しない。
    # 存在が分かるようにファイル名だけを記録しておく。
    files = get_file_names(msg)

    entry = {
      'ts': ts,
      'time': dt.strftime("%Y-%m-%d %H:%M:%S"),
      'name': name,
      'text': text,
    }
    if files:
      entry['files'] = files
    store['messages'].append(entry)
    # 分割形式の保存で、変更のあった期間だけを書き出すために新規ぶんを控えておく
    # (単一形式では未使用。保存時に取り除く)。
    store.setdefault('_added_entries', []).append(entry)
    added += 1
  return added

# Discord からチャンネル履歴を取得し、store に差分を追記して追加件数を返す。
# 重複排除は Discord のメッセージ ID(スノーフレーク、一意)で行う。
# discord ライブラリはこの経路でのみ使うので、ここで遅延 import する
# (Slack だけ使う環境では discord 未インストールでも動く)。
def fetch_discord(store, token, channel_name, overlap_seconds):
  import discord

  # メッセージ本文を読むには message_content インテントが必要。
  intents = discord.Intents.default()
  intents.message_content = True
  client = discord.Client(intents=intents)

  # on_ready の中で発生した例外・件数を main まで持ち出すための入れ物。
  result = {'error': None, 'added': 0}

  @client.event
  async def on_ready():
    try:
      result['added'] = await _discord_fetch(client, store, channel_name, overlap_seconds)
    except Exception as e:  # 何が起きても捕捉し、client を閉じてから main に投げ直す
      result['error'] = e
    finally:
      await client.close()

  client.run(token)

  if result['error'] is not None:
    raise result['error']
  return result['added']

# Discord チャンネルの履歴を取得し、store に差分を追記して追加件数を返す(非同期)。
async def _discord_fetch(client, store, channel_name, overlap_seconds):
  channel = _discord_find_channel(client, channel_name)
  if channel is None:
    raise RuntimeError("channel not found: " + channel_name)

  # Discord のメッセージ ID で重複を排除する
  seen_ids = set(msg['id'] for msg in store['messages'] if 'id' in msg)

  # 保存済みの最新メッセージから overlap_seconds だけさかのぼった時点を起点に取得する。
  # まだ何も保存されていなければチャンネルの最古から全て取得する(after=None)。
  after = None
  if store['messages']:
    oldest_ts = max(float(msg['ts']) for msg in store['messages']) - overlap_seconds
    if oldest_ts < 0:
      oldest_ts = 0
    after = datetime.fromtimestamp(oldest_ts, UTC)

  store.setdefault('users', {})
  added = 0
  # oldest_first=True で古い順に受け取り、limit=None で全件たどる
  async for msg in channel.history(limit=None, after=after, oldest_first=True):
    mid = str(msg.id)
    if mid in seen_ids:
      continue # 既に保存済み
    seen_ids.add(mid)

    dt = msg.created_at.astimezone(UTC)
    name = msg.author.name

    # メンション <@ユーザID> を @ユーザ名 に解決するための id→name マップを蓄積する
    # (退会ユーザ名も残せるよう既存に上書き)。
    store['users'][str(msg.author.id)] = name
    for user in msg.mentions:
      store['users'][str(user.id)] = user.name

    # 添付ファイルはファイル名だけを記録する(本体は取得しない)。
    files = [a.filename for a in msg.attachments]

    entry = {
      'id': mid,
      'ts': "%.6f" % msg.created_at.timestamp(),
      'time': dt.strftime("%Y-%m-%d %H:%M:%S"),
      'name': name,
      'text': msg.content,
    }
    if files:
      entry['files'] = files
    store['messages'].append(entry)
    store.setdefault('_added_entries', []).append(entry)
    added += 1
  return added

# 名前から Discord チャンネルを検索する(全ギルドのテキストチャンネルから完全一致を探す)
def _discord_find_channel(client, channel_name):
  for guild in client.guilds:
    for channel in guild.text_channels:
      if str(channel) == channel_name:
        return channel
  return None

# 名前から Slack チャンネル情報を取得する
def find_channel(token, channel_name):
  # conversations.list はページングされるため全ページを取得して完全一致を探す
  channels = request_to_json_all(api_channel_list_url, token, 'channels',
                                 {'exclude_archived': 'true',
                                  'types': 'public_channel,private_channel',
                                  'limit': 200})

  # 完全一致するものをリストで返す
  channelList = []
  for channel in channels:
    if(channel['name'] == channel_name):
        channelList.append(channel)

  return channelList

def json_parse(file_path):
  f = open(file_path, 'r')
  json_data = json.load(f)
  return json_data

# 出力先 JSON を読み込む。無ければ空の器を返す。
# 単一形式: {"channel": "<チャンネル名>", "messages": [ {ts, time, name, text}, ... ]}
# 分割形式(chunks を持つマニフェスト)なら load_split_store で扱う。
def load_store(filename, channel_name, overlap_seconds=DEFAULT_OVERLAP_SECONDS):
  try:
    f = open(filename, 'r', encoding='utf-8')
  except FileNotFoundError:
    return {'channel': channel_name, 'messages': []}
  data = json.load(f)
  f.close()
  if 'chunks' in data:
    return load_split_store(filename, channel_name, data, overlap_seconds)
  if 'messages' not in data:
    data['messages'] = []
  if 'channel' not in data:
    data['channel'] = channel_name
  return data

# メッセージの ts から所属期間キーを返す(year: "2022" / month: "2022-01")
def period_key(ts, by):
  d = datetime.fromtimestamp(float(ts), tz=JST)
  if by == 'month':
    return '%04d-%02d' % (d.year, d.month)
  return '%04d' % d.year

def jst_date(ts):
  return datetime.fromtimestamp(float(ts), tz=JST).strftime('%Y/%m/%d')

# メッセージの重複判定キー。Discord は id(一意)、Slack は ts を使う。
def dedup_key(m):
  return m.get('id') or m.get('ts')

# '<base>.<period>.json' から '<period>' を取り出す
def chunk_period(base, fname):
  return fname[len(base) + 1:-5]

# マニフェストに by が無い(古い)場合、チャンク名から粒度を推定する
def infer_by(data, base):
  for c in data.get('chunks', []):
    if '-' in chunk_period(base, c['file']):
      return 'month'
  return 'year'

# チャンク(<channel>.<period>.json)の messages 配列を読み込む
def read_chunk(dirname, fname):
  with open(os.path.join(dirname, fname), 'r', encoding='utf-8') as f:
    return json.load(f).get('messages', [])

# ソート済みメッセージからチャンクのメタ情報を作る
def build_chunk_meta(base, period, msgs):
  dates = sorted({jst_date(m['ts']) for m in msgs})
  return {
    'file': base + '.' + period + '.json',
    'from': msgs[0]['ts'],
    'to': msgs[-1]['ts'],
    'count': len(msgs),
    'dates': dates,
  }

# 分割形式(マニフェスト)を読み込む。差分取得に必要な範囲のチャンクだけを読む。
# overlap_seconds ぶんさかのぼった時点(after_ts)以降に触れるチャンクのみ読み込めば、
# 重複排除も新規ぶんの追記先も揃う。過去チャンクは触らない。
def load_split_store(filename, channel_name, data, overlap_seconds):
  dirname = os.path.dirname(filename)
  base = os.path.basename(filename)
  if base.endswith('.json'):
    base = base[:-5]
  by = data.get('by') or infer_by(data, base)

  chunks_meta = {}
  for c in data.get('chunks', []):
    chunks_meta[chunk_period(base, c['file'])] = c

  max_ts = data.get('maxTs')
  after_ts = None
  if max_ts is not None:
    after_ts = float(max_ts) - overlap_seconds
    if after_ts < 0:
      after_ts = 0.0

  loaded = set()
  messages = []
  for period, c in chunks_meta.items():
    if after_ts is None or float(c['to']) >= after_ts:
      messages.extend(read_chunk(dirname, c['file']))
      loaded.add(period)

  store = {
    '_split': True,
    'channel': data.get('channel', channel_name),
    'users': data.get('users', {}),
    'by': by,
    'dirname': dirname,
    'base': base,
    'chunks_meta': chunks_meta,
    'loaded': loaded,
    'maxTs': max_ts,
    'messages': messages,
    '_added_entries': [],
  }
  if 'service' in data:
    store['service'] = data['service']
  if 'retrievedAt' in data:
    store['retrievedAt'] = data['retrievedAt']
  if 'error' in data:
    store['error'] = data['error']
  return store

# 蓄積した JSON を書き出す。分割形式なら save_split_store に委譲する。
def save_store(filename, store):
  if store.get('_split'):
    save_split_store(filename, store)
    return
  # 単一形式(全件を上書き保存)。内部用キーは出力しない。
  store.pop('_added_entries', None)
  f = open(filename, 'w', encoding='utf-8')
  json.dump(store, f, ensure_ascii=False, indent=2)
  f.write("\n")
  f.close()

# 分割形式を書き出す。変更のあった期間のチャンクだけ書き換え、マニフェストを更新する。
# 過去チャンクは触らないので git の差分・rsync 転送を小さく保てる。
def save_split_store(filename, store):
  by = store['by']
  dirname = store['dirname']
  base = store['base']
  added = store.get('_added_entries', [])
  changed = set(period_key(e['ts'], by) for e in added)

  # 変更のある既存期間がまだ読み込まれていなければ、その期間のチャンクを読み込んで
  # 既存メッセージを取りこぼさないようマージする(年境界などで新規が旧期間に入る対策)。
  for p in list(changed):
    if p not in store['loaded'] and p in store['chunks_meta']:
      existing_keys = set(dedup_key(m) for m in store['messages'])
      for m in read_chunk(dirname, store['chunks_meta'][p]['file']):
        if dedup_key(m) not in existing_keys:
          store['messages'].append(m)
      store['loaded'].add(p)

  # メモリ上のメッセージ(読み込み済みチャンク + 新規)を期間ごとに分ける
  buckets = {}
  for m in store['messages']:
    buckets.setdefault(period_key(m['ts'], by), []).append(m)

  # 既存メタを土台に、変更のあった期間だけメタを作り直しチャンクを書き出す
  metas = dict(store['chunks_meta'])
  for p in changed:
    msgs = sorted(buckets.get(p, []), key=lambda m: float(m['ts']))
    with open(os.path.join(dirname, base + '.' + p + '.json'), 'w', encoding='utf-8') as f:
      json.dump({'messages': msgs}, f, ensure_ascii=False, indent=2)
      f.write("\n")
    metas[p] = build_chunk_meta(base, p, msgs)

  chunks = [metas[p] for p in sorted(metas)]
  max_ts = None
  for meta in metas.values():
    if max_ts is None or float(meta['to']) > float(max_ts):
      max_ts = meta['to']

  manifest = {
    'channel': store['channel'],
    'format': 2,
    'by': by,
    'users': store.get('users', {}),
    'chunks': chunks,
  }
  if store.get('service'):
    manifest['service'] = store['service']
  if max_ts is not None:
    manifest['maxTs'] = max_ts
  if 'retrievedAt' in store:
    manifest['retrievedAt'] = store['retrievedAt']
  if store.get('error'):
    manifest['error'] = store['error']

  with open(filename, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")

def get_users_info(token):
  return request_to_json_all(api_user_list_url, token, 'members', {'limit': 200})

# channel_idからチャンネルのメンバーID一覧を取得する
def get_channel_members(token, channel_id):
  return request_to_json_all(api_channel_members_url, token, 'members',
                             {'channel': channel_id, 'limit': 200})

# Slack のログを取得する
# oldest_ts:取得開始の Unix タイムスタンプ(この時刻より後を取得。inclusive=0)
# latest_ts:取得終了の Unix タイムスタンプ
def get_channel_history(token, channel_id, oldest_ts, latest_ts):
  return request_to_json_all(api_channel_history_url, token, 'messages',
                             {'channel': channel_id, 'inclusive': '0',
                              'oldest': oldest_ts, 'latest': latest_ts,
                              'limit': 200})

# メッセージに添付されたファイルの表示名一覧を返す(ファイル本体は取得しない)
def get_file_names(msg):
  names = []
  for f in msg.get('files', []):
    # 削除済みファイルなどは name/title が無いことがあるので順に代替する
    names.append(f.get('name') or f.get('title') or f.get('id') or 'file')
  return names

def find_user(token, id, channel_user):
  for member in channel_user:
    if member['id'] == id:
      return member

# Slack Web API を GET で呼び出す(トークンは Authorization ヘッダで渡す)
def request_to_json(url, token, params=None):
  if params is None:
    params = {}
  query = urllib.parse.urlencode(params)
  full_url = url + ("?" + query if query else "")
  req = urllib.request.Request(full_url)
  req.add_header("Authorization", "Bearer " + token)
  res = urllib.request.urlopen(req)
  json_data = json.loads(res.read().decode('utf-8'))

  if not json_data['ok']:
    # 正しく取得できなかったら例外を投げる(main 側で捕捉し JSON にエラーを記録する)
    raise RuntimeError("Slack API error: " + str(json_data.get('error')))

  return json_data

# カーソルページングに対応し、result_key の要素を全ページ分連結して返す
def request_to_json_all(url, token, result_key, params=None):
  if params is None:
    params = {}
  items = []
  cursor = None
  while True:
    page_params = dict(params)
    if cursor:
      page_params['cursor'] = cursor
    json_data = request_to_json(url, token, page_params)
    items.extend(json_data.get(result_key, []))
    cursor = json_data.get('response_metadata', {}).get('next_cursor')
    if not cursor:
      break

  return items


if __name__ == "__main__":
  argvs = sys.argv
  if(len(argvs) != 4):
    print("<usage> python3 " + argvs[0] + " [output json file] [channel name] [path to config json]")
    sys.exit()
  else:
    main(argvs[1], argvs[2], argvs[3])
