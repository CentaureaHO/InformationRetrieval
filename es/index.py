from config import config, es_client, script_dir
from pathlib import Path
from elasticsearch import Elasticsearch, exceptions, helpers
from tqdm import tqdm
import json

data_path = script_dir / '../crawler/crawled_data'
web_path = data_path / 'web'
page_files = list(web_path.glob('*.json'))

actions, cnt, batch_size = [], 0, 1000

for json_file in tqdm(page_files, desc="Processing JSON files", unit="file"):
    with open(json_file, 'r', encoding='utf-8') as f:
        page = json.load(f)
        url = page.get("url")
        title = page.get("title", "")
        body = page.get("body", "")

        actions.append({
            "_index": "web_pages",
            "_source": {
                "url": url,
                "title": title,
                "raw_title": title,
                "body": body,
                "is_file": True if json_file.name.startswith('f_') else False
            }
        })
        cnt += 1

        if cnt % batch_size == 0:
            helpers.bulk(es_client, actions)
            actions = []

if actions:
    helpers.bulk(es_client, actions)