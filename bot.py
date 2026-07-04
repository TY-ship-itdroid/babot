import sys
sys.stdout.reconfigure(line_buffering=True)
import os
from dotenv import load_dotenv
load_dotenv()
import discord
import json
import random

CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

config = load_config()
ALIASES_FILE = 'aliases.json'

def load_aliases():
    if os.path.exists(ALIASES_FILE):
        with open(ALIASES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

aliases = load_aliases()

import requests
import re
from bs4 import BeautifulSoup

STUDENTS_FILE = 'students.json'
STUDENTS_URL = 'https://bluearchive.wikiru.jp/?キャラクター一覧'

# ユーザーがよく使う衣装の略称 → wiki上の正式な衣装タグ
COSTUME_ALIASES = {
    '水着': '水着', '水': '水着',
    '私服': '私服', '私': '私服',
    '体操服': '体操服', '体': '体操服',
    'ドレス': 'ドレス', 'ド': 'ドレス',
    'アイドル': 'アイドル', 'ドル': 'アイドル',
    'メイド': 'メイド', 'メ': 'メイド',
    'パジャマ': 'パジャマ', 'パ': 'パジャマ',
    'キャンプ': 'キャンプ', 'キャン': 'キャンプ',
    'クリスマス': 'クリスマス', 'クリ': 'クリスマス',
    '正月': '正月', '正': '正月',
    '臨戦': '臨戦', '臨': '臨戦',
    'バニーガール': 'バニーガール', 'バニー': 'バニーガール',
    'アルバイト': 'アルバイト', 'バイト': 'アルバイト',
    'ライディング': 'ライディング',
    'チーパオ': 'チーパオ',
    'マジカル': 'マジカル',
    'バンド': 'バンド',
    'ガイド': 'ガイド',
    '幼女': '幼女',
    '応援団': '応援団', '応援': '応援団',
    '温泉': '温泉',
}

def fetch_students():
    response = requests.get(STUDENTS_URL)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    body = soup.find(id='body')
    table = body.find('table')

    students = {}
    seen = set()
    for link in table.find_all('a'):
        name = link.get_text(strip=True)
        if not name or name in ('追加', '編集') or name in seen:
            continue
        seen.add(name)
        match = re.match(r'^(.+?)（(.+)）$', name)
        if match:
            base, costume = match.group(1), match.group(2)
        else:
            base, costume = name, None
        students.setdefault(base, set())
        if costume:
            students[base].add(costume)
    return students

def load_students():
    if os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {base: set(costumes) for base, costumes in data.items()}
    return {}

def save_students(students):
    with open(STUDENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({base: sorted(costumes) for base, costumes in students.items()}, f, ensure_ascii=False)

students = load_students()

def refresh_students():
    global students
    try:
        fetched = fetch_students()
        if fetched:
            students = fetched
            save_students(students)
            print(f'生徒リストを更新しました: {len(students)}件')
    except Exception as e:
        print(f'生徒リストの取得に失敗しました: {e}')

if not students:
    refresh_students()

def build_name_candidates():
    """aliases.json（不規則な省略形）と、衣装略称×生徒名から機械的に組み立てた
    候補（例：水ナグサ→ナグサ（水着））をまとめ、パターンが長い順に並べる。
    長い一致を優先しないと、「水ナグサ」が短い別名「水ナ」（→イズナ（水着））に
    部分一致して誤変換されてしまう。"""
    candidates = list(aliases.items())
    for abbrev, costume in COSTUME_ALIASES.items():
        for base, costumes in students.items():
            if costume not in costumes:
                continue
            official = f'{base}（{costume}）'
            candidates.append((abbrev + base, official))
            candidates.append((base + abbrev, official))
    candidates.sort(key=lambda pair: len(pair[0]), reverse=True)
    return candidates

def normalize_character_references(question):
    """質問文中のキャラのあだ名・略称をローカルだけで正式名称に変換する。
    ここで解決できなければ呼び出し側がClaudeでの抽出にフォールバックする。"""
    result = question
    matched = []
    for pattern, official in build_name_candidates():
        if official in result:
            continue
        if pattern in result:
            result = result.replace(pattern, official)
            if official not in matched:
                matched.append(official)
    return result, matched

import anthropic
import asyncio
from datetime import datetime, timezone

intents = discord.Intents.default()
TARGET_ROLE_ID = 1282666189243416669
message_counts = {}  # {ユーザー名: 件数} を記録する辞書
intents.message_content = True

client = discord.Client(intents=intents)

def get_events():
    url = 'https://bluearchive.wikiru.jp/?イベント'
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    tables = soup.find_all('table')

    text = tables[0].get_text().strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    today = datetime.now()
    current_events = []
    event_name = None

    for line in lines:
        # 最新かつ開催中のイベントのみピックアップ
        if '過去のイベント' in line or '開催予定のイベント' in line:
            break

        match = re.search(r'～\s*(\d+)/(\d+)', line)
        if match and event_name:
            end_month = int(match.group(1))
            end_day = int(match.group(2))
            try:
                end_date = datetime(today.year, end_month, end_day)
                if end_date >= datetime(today.year, today.month, today.day):
                    current_events.append(f'{event_name}（～{end_month}/{end_day}）')
            except:
                pass
            event_name = None
        else:
            event_name = line

    print(f'イベント件数: {len(current_events)}')
    for event in current_events:
        print(event)

    return current_events

@client.event
async def on_ready():
    print(f'{client.user} が起動しました！')
    client.loop.create_task(event_notification())

async def event_notification():
    await client.wait_until_ready()
    while not client.is_closed():
        now = datetime.now(timezone.utc)
        channel_id = config.get('event_channel') or int(os.environ.get('EVENT_CHANNEL_ID', 0))
        print(f'チャンネルID: {channel_id}')
        ranking_channel_id = config.get('ranking_channel')
        channel = client.get_channel(channel_id) if channel_id else None
        ranking_channel = client.get_channel(ranking_channel_id) if ranking_channel_id else None
        print(f'UTC時刻: {now.hour}:{now.minute}')
        # 月初0時（日本時間9時）に集計送信
        if now.day == 1 and now.hour == 0 and now.minute == 0:
            if message_counts:
                msg = '**【今月の書き込み件数ランキング】**\n'
                for name, count in message_counts.items():
                    msg += f'・{name}：{count}件\n'
            else:
                msg = '今月は対象ロールの書き込みがありませんでした'
            if ranking_channel: 
                await ranking_channel.send(msg)
            message_counts.clear()
            await asyncio.sleep(60)

        # 日本時間12時 = UTC 3時
        elif now.hour == 3 and now.minute == 00:
            events = get_events()
            message = '**【ブルアカ イベント一覧】**\n'
            if events:
                 for event in events:
                     message += f'・{event}\n'
            else:
                 message += '現在開催中のイベントはありません'
            if channel:
                await channel.send(message)
            await asyncio.sleep(60) # 1分待って二重送信防止
        # 日本時間9時 = UTC 0時　→　リマインド
        elif now.hour == 0 and now.minute == 0:
            events = get_events()
            reminders = []
            today = datetime.now(timezone.utc)
            for event in events:
                # イベント名から終了日を取り出す（例：～6/24）
                match = re.search(r'～(\d+)/(\d+)', event)
                if match:
                    end_month = int(match.group(1))
                    end_day = int(match.group(2))
                    end_date = datetime(today.year, end_month, end_day, tzinfo=timezone.utc)
                    days_left = (end_date - today).days
                    if days_left == 1:
                        reminders.append(f'⚠️ {event}　**明日終了！**')
                    elif days_left == 2:
                        reminders.append(f'📢 {event}　**あと2日！**')
            if reminders:
                message = '**【ブルアカ イベント終了リマインド】**\n'
                for r in reminders:
                    message += f'・{r}\n'
                if channel:
                    await channel.send(message)
            await asyncio.sleep(60)

        # 生徒・衣装一覧の更新（UTC 6時）
        elif now.hour == 6 and now.minute == 0:
            refresh_students()
            await asyncio.sleep(60)

        else:
            await asyncio.sleep(300)  # 300秒ごとに時刻チェック

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    # 特定ロールを持つユーザーのメッセージをカウント
    target_role_id = config.get('target_role', TARGET_ROLE_ID)
    if hasattr(message.author, 'roles'):
        role_ids = [role.id for role in message.author.roles]
        if target_role_id in role_ids:
            name = message.author.display_name
            message_counts[name] = message_counts.get(name, 0) + 1
    
    if message.content == '!ping':
        await message.channel.send('pong!')
    
    elif message.content == '!コマンド':
        msg = '**【使えるコマンド一覧】**\n'
        msg += '・!ping：botが反応するか確認\n'
        msg += '・!イベント：現在開催中のイベント一覧を表示\n'
        msg += '・!聞く 質問内容：ブルアカに関する質問にAIが回答（例：!聞く 水着ナグサって強い？）\n'
        msg += '・!コマンド：このコマンド一覧を表示'
        await message.channel.send(msg)
    
    elif message.content == '!設定 イベント通知':
        config['event_channel'] = message.channel.id
        save_config(config)
        await message.channel.send('このチャンネルをイベント通知用に設定しました！')

    elif message.content == '!設定 ランキング':
        config['ranking_channel'] = message.channel.id
        save_config(config)
        await message.channel.send('このチャンネルをランキング用に設定しました！')
    
    elif message.content.startswith('!設定 集計ロール'):  # ← ここに追加
        if message.role_mentions:
            role = message.role_mentions[0]
            config['target_role'] = role.id
            save_config(config)
            await message.channel.send(f'集計対象ロールを「{role.name}」に設定しました！')
        else:
            await message.channel.send('ロールをメンションして指定してください（例：!設定 集計ロール @メンバー）')
    
    elif message.content == '!ランキング確認':
        if message_counts:
            msg = '**【現在の書き込み件数（今月分）】**\n'
            for name, count in message_counts.items():
                msg += f'・{name}：{count}件\n'
        else:
            msg = '現在、対象ロールの書き込みはありません'
        await message.channel.send(msg)

    elif message.content == '!イベント':
        events = get_events()
        message_text = '**【ブルアカ イベント一覧】**\n'
        for event in events:
            message_text += f'・{event}\n'
        await message.channel.send(message_text)
    
    elif message.content.startswith('!聞く ') or message.content.startswith('!聞く\u3000'):
        print(f'受け取った入力: {repr(message.content)}')
        question = message.content[4:].strip()

        # NGワードチェック
        ng_words = ['えっち', 'エッチ', 'セックス', 'sex', 'SEX', 'シコれ', 'しこれ']  # 必要に応じて追加
        if any(ng in question for ng in ng_words):
            responses = [
                'その質問、ふしだらすぎないかしら？',
                'そういうのはダメ！',
                'もしもしヴァルキューレ？',
            ]
            await message.channel.send(random.choice(responses))
            return

        question = question.replace('(', '（').replace(')', '）')
        # あだ名・略称（aliases.jsonの不規則なものと、衣装略称＋キャラ名の規則的なもの）をローカルで正式名称に変換
        question, matched_names = normalize_character_references(question)
        print(f'変換前のquestion: {repr(question)}')

        if matched_names:
            character_name = '、'.join(matched_names)
            print(f'ルールベースで変換したキャラ名: {character_name}')
        else:
            format_claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
            format_response = format_claude.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=100,
                system=[
                    {
                        'type': 'text',
                        'text': 'ユーザーの質問文からブルーアーカイブの生徒キャラ名のみを抽出し、正式名称に変換してください。入力が「衣装名+キャラ名」の形式なら「キャラ名（衣装名）」に変換してください。例：水着ナグサ→ナグサ（水着）、私服ホシノ→ホシノ（私服）。ゲブラ、グレゴリオなどのボス名・コンテンツ名はキャラ名ではないので変換しないでください。質問文にキャラ名が含まれない場合は「なし」と返してください。キャラ名が複数ある場合は全て列挙してください。変換結果以外の文章は出力しないでください。',
                        'cache_control': {'type': 'ephemeral'}
                    }
                ],
                messages=[
                     {'role': 'user', 'content': question}
                ]
            )
            character_name = format_response.content[0].text.strip()
            print(f'抽出したキャラ名: {character_name}')

        if character_name == 'なし':
            enhanced_question = f'{question}'
        else:
            enhanced_question = f'{question}　※キャラ名「{character_name}」は完全一致で検索すること。検索する際は「ブルーアーカイブ {character_name} wiki」で検索すること。例えば「水着ナグサ」と「水着ナギサ」は別キャラなので混同しないこと。'
        async with message.channel.typing():
            claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
            response = claude.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=1000,
                system=[
                    {
                        'type': 'text',
                        'text': 'あなたはブルーアーカイブのサークルDiscordサーバーのアシスタントBotです。ブルアカに関する質問に答えてください。情報を調べる際は必ず最初に「ブルーアーカイブ キャラ名 wiki」の形式で検索すること。日本語で回答すること。キャラ名が含まれる場合は正式名称で検索し、似た名前のキャラと混同しないよう注意してください。知らないことや不確かなことは「わかりません」と答えてください。質問の意図に応じて回答内容を変えてください。「強い？」など強さを聞かれた場合は性能評価を、「活躍場所は？」「どこで使える？」など使い道を聞かれた場合はおすすめのコンテンツ・ステージを、「可愛い？」など見た目や魅力を聞かれた場合は性能の話はせず見た目やキャラクター性について答えてください。回答はDiscordのチャット向けにシンプルな形式で書いてください。箇条書きは「・テキスト」の形式で改行なしで書いてください。見出しは「**〇〇**」の形式にしてください。回答の最初に「確認します」「調べます」などの前置きは不要です。同じ内容を繰り返さないでください。「お気軽にどうぞ」などの締めの文は不要です。結論から簡潔に答えてください。',  # 今のsystemプロンプト
                        'cache_control': {'type': 'ephemeral'}
                    }
                ],
                messages=[
                    {'role': 'user', 'content': enhanced_question}
                ],
                tools=[
                    {
                        'type': 'web_search_20250305',
                        'name': 'web_search',
                        'max_uses': 1
                    }
                ]
            )
            fullResponse = '\n'.join(
                item.text for item in response.content
                if hasattr(item, 'text')
            )
            # 箇条書きや見出しじゃない行の改行をスペースに変換
            lines = fullResponse.split('\n')
            result = []
            for i, line in enumerate(lines):
                if line.startswith('・') or line.startswith('**') or line.strip() == '':
                    result.append(line)
                elif i > 0 and result and not result[-1].startswith('・') and not result[-1].startswith('**') and result[-1].strip() != '':
                    # 前の行と結合
                    result[-1] += line
                else:
                    result.append(line)
            fullResponse = '\n'.join(result)
            
            fullResponse = re.sub(r'・\n+', '・', fullResponse)
            fullResponse = re.sub(r'\n{3,}', '\n\n', fullResponse)

            print(fullResponse)
            await message.channel.send(fullResponse)

client.run(os.environ['DISCORD_TOKEN'])