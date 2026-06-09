import requests
from bs4 import BeautifulSoup

url = 'https://bluearchive.wikiru.jp/?イベント'

response = requests.get(url)
response.encoding = 'utf-8'
soup = BeautifulSoup(response.text, 'html.parser')

tables = soup.find_all('table')
text = tables[1].get_text().strip()
lines = [line.strip() for line in text.splitlines() if line.strip()]
events = lines[1:]

for event in events:
    print(repr(event))