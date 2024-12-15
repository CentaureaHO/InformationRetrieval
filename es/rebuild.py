from config import config, es_client, script_dir
from pathlib import Path
from elasticsearch import Elasticsearch, exceptions
import json

index_json = script_dir / 'index.json'
history_index_json = script_dir / 'query_history_index.json'
user_index_json = script_dir / 'user_index.json'

page_idx_name = config["es"]["page_index"]
history_idx_name = config["es"]["history_index"]
user_idx_name = config["es"]["user_index"]
try:
    if es_client.indices.exists(index=page_idx_name):
        es_client.indices.delete(index=page_idx_name)
        print(f"索引 '{page_idx_name}' 已删除。")
    else:
        print(f"索引 '{page_idx_name}' 不存在，无需删除。")
    if es_client.indices.exists(index=history_idx_name):
        es_client.indices.delete(index=history_idx_name)
        print(f"索引 '{history_idx_name}' 已删除。")
    else:
        print(f"索引 '{history_idx_name}' 不存在，无需删除。")
    if es_client.indices.exists(index=user_idx_name):
        es_client.indices.delete(index=user_idx_name)
        print(f"索引 '{user_idx_name}' 已删除。")
    else:
        print(f"索引 '{user_idx_name}' 不存在，无需删除。")
except exceptions.ElasticsearchException as e:
    print(f"删除索引失败: {e}")
    exit(1)

with open(index_json, 'r', encoding='utf-8') as f:
    index_body = json.load(f)
with open(history_index_json, 'r', encoding='utf-8') as f:
    his_index_body = json.load(f)
with open(user_index_json, 'r', encoding='utf-8') as f:
    user_index_body = json.load(f)

try:
    es_client.indices.create(index = page_idx_name, body = index_body)
    print(f"索引 '{page_idx_name}' 已创建。")
    es_client.indices.create(index = history_idx_name, body = his_index_body)
    print(f"索引 '{history_idx_name}' 已创建。")
    es_client.indices.create(index = user_idx_name, body = user_index_body)
    print(f"索引 '{user_idx_name}' 已创建。")
except exceptions.ElasticsearchException as e:
    print(f"创建索引失败: {e}")
    exit(1)