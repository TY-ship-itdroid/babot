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

import anthropic
import asyncio
import requests
import re
from bs4 import BeautifulSoup
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
        # 愛称変換
        for alias, official_name in aliases.items():
            if alias in question:
                question = question.replace(alias, official_name)
                print(f'愛称変換: {alias} → {official_name}')
        print(f'変換前のquestion: {repr(question)}')
        format_claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        format_response = format_claude.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=100,
            system='ユーザーの質問文からブルーアーカイブの生徒キャラ名のみを抽出し、正式名称に変換してください。入力が「衣装名+キャラ名」の形式なら「キャラ名（衣装名）」に変換してください。例：水着ナグサ→ナグサ（水着）、私服ホシノ→ホシノ（私服）。ゲブラ、グレゴリオなどのボス名・コンテンツ名はキャラ名ではないので変換しないでください。質問文にキャラ名が含まれない場合は「なし」と返してください。キャラ名が複数ある場合は全て列挙してください。変換結果以外の文章は出力しないでください。',
            messages=[
                 {'role': 'user', 'content': question}
            ]
        )
        character_name = format_response.content[0].text.strip()
        print(f'抽出したキャラ名: {character_name}')

        if character_name == 'なし':
            enhanced_question = f'{question}'
        else:
            enhanced_question = f'{question}　※キャラ名「{character_name}」は完全一致で検索すること。例えば「水着ナグサ」と「水着ナギサ」は別キャラなので混同しないこと。'
        async with message.channel.typing():
            claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
            response = claude.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=1000,
                system='あなたはブルーアーカイブのサークルDiscordサーバーのアシスタントBotです。ブルアカに関する質問に答えてください。必ずweb検索で最新情報を調べてから答えてください。キャラ名が含まれる場合は正式名称で検索し、似た名前のキャラと混同しないよう注意してください。知らないことや不確かなことは「わかりません」と答えてください。質問の意図に応じて回答内容を変えてください。「強い？」など強さを聞かれた場合は性能評価を、「活躍場所は？」「どこで使える？」など使い道を聞かれた場合はおすすめのコンテンツ・ステージを、「可愛い？」など見た目や魅力を聞かれた場合は性能の話はせず見た目やキャラクター性について答えてください。回答はDiscordのチャット向けにシンプルな形式で書いてください。箇条書きは「・テキスト」の形式で改行なしで書いてください。見出しは「**〇〇**」の形式にしてください。回答の最初に「確認します」「調べます」などの前置きは不要です。同じ内容を繰り返さないでください。「お気軽にどうぞ」などの締めの文は不要です。結論から簡潔に答えてください。',
                messages=[
                    {'role': 'user', 'content': enhanced_question}
                ],
                tools=[
                    {
                        'type': 'web_search_20250305',
                        'name': 'web_search'
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