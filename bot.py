import sys
sys.stdout.reconfigure(line_buffering=True)
import os
from dotenv import load_dotenv
load_dotenv()
import discord
import anthropic
import asyncio
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

intents = discord.Intents.default()
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
    channel = client.get_channel(1513838887758463059)
    while not client.is_closed():
        now = datetime.now(timezone.utc)  # UTCに変更
        print(f'UTC時刻: {now.hour}:{now.minute}') 
        # 日本時間12時 = UTC 3時
        if now.hour == 3 and now.minute == 00:
            events = get_events()
            message = '**【ブルアカ イベント一覧】**\n'
            if events:
                 for event in events:
                     message += f'・{event}\n'
            else:
                 message += '現在開催中のイベントはありません'
            await channel.send(message)
            await asyncio.sleep(60) # 1分待って二重送信防止
        else:
            await asyncio.sleep(300)  # 300秒ごとに時刻チェック

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content == '!ping':
        await message.channel.send('pong!')
    elif message.content == '!イベント':
        events = get_events()
        message_text = '**【ブルアカ イベント一覧】**\n'
        for event in events:
            message_text += f'・{event}\n'
        await message.channel.send(message_text)
    elif message.content.startswith('!聞く ') or message.content.startswith('!聞く\u3000'):
        question = message.content[4:].strip()
        enhanced_question = f'「{question}」※キャラ名は完全一致で検索すること。例えば「水着ナグサ」と「水着ナギサ」は別キャラなので混同しないこと。'
        async with message.channel.typing():
            claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
            response = claude.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=1000,
                system='あなたはブルーアーカイブのサークルDiscordサーバーのアシスタントBotです。ブルアカに関する質問に答えてください。必ずweb検索で最新情報を調べてから答えてください。キャラ名が含まれる場合は正式名称で検索し、似た名前のキャラと混同しないよう注意してください。知らないことや不確かなことは「わかりません」と答えてください。回答はDiscordのチャット向けにシンプルな形式で書いてください。箇条書きは「・テキスト」の形式で改行なしで書いてください。見出しは「**〇〇**」の形式にしてください。'
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
            print(fullResponse)  # これを追加！
            await message.channel.send(fullResponse)

client.run(os.environ['DISCORD_TOKEN'])