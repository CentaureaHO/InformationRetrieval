from config import config, es_client, script_dir
from pathlib import Path
from elasticsearch import Elasticsearch, exceptions, helpers
import networkx as nx
import numpy as np
import json
from math import log
from tqdm import tqdm

data_path = script_dir / '../crawler/crawled_data'
web_path = data_path / 'web'
page_files = list(web_path.glob('*.json'))

Graph = nx.DiGraph()

for json_file in tqdm(page_files, desc="构建有向图", unit="文件"):
    with open(json_file, 'r', encoding='utf-8') as f:
        page = json.load(f)
        url = page.get("url")
        outlinks = list(set(page.get("outlinks", [])))
        for link in outlinks:
            Graph.add_edge(url, link)

pagerank_scores = nx.pagerank(Graph, alpha=0.85)
pagerank_dict = dict(pagerank_scores)
max_pr = max(pagerank_dict.values())
min_pr = min(pagerank_dict.values())
pagerank_scores = {k: (np.exp((v - min_pr) / (max_pr - min_pr)) / np.exp(1)) for k, v in pagerank_dict.items()}

actions, cnt, batch_size = [], 0, 1000

for url, score in tqdm(pagerank_scores.items(), desc="更新 Elasticsearch", total=len(pagerank_scores), unit="文档"):
    query = {
        "query": {
            "term": {
                "url": url
            }
        },
        "_source": False,
        "size": 1
    }
    res = es_client.search(index="web_pages", body=query)
    hits = res['hits']['hits']
    if hits:
        doc_id = hits[0]['_id']
        actions.append({
            "_op_type": "update",
            "_index": "web_pages",
            "_id": doc_id,
            "doc": {
                "pagerank": score
            }
        })
        cnt += 1

        if cnt % batch_size == 0:
            helpers.bulk(es_client, actions)
            actions = []

if actions:
    helpers.bulk(es_client, actions)