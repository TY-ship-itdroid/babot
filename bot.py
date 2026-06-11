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
    text = tables[1].get_text().strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    events = lines[1:]
    
    today = datetime.now()
    current_events = []
    
    for event in events:
        try:
            # 末尾の MM/DD を取得
            match = re.search(r'(\d{2})/(\d{2})\s*$', event)
            if match:
                end_month = int(match.group(1))
                end_day = int(match.group(2))
                end_date = datetime(today.year, end_month, end_day)
                if end_date >= datetime(today.year, today.month, today.day):
                    current_events.append(event)
        except:
            continue
    
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
        if now.hour == 12 and now.minute == 50:
            events = get_events()
            if events:
                message = '**【ブルアカ イベント一覧】**\n'
                for event in events:
                    message += f'・{event}\n'
                await channel.send(message)
            await asyncio.sleep(60) # 1分待って二重送信防止
        else:
            await asyncio.sleep(30)  # 30秒ごとに時刻チェック

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
        async with message.channel.typing():
            claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
            response = claude.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=1000,
                system='あなたはブルーアーカイブのサークルDiscordサーバーのアシスタントBotです。ブルアカに関する質問に日本語で答えてください。',
                messages=[
                    {'role': 'user', 'content': question}
                ]
            )
            await message.channel.send(response.content[0].text)

client.run(os.environ['DISCORD_TOKEN'])
