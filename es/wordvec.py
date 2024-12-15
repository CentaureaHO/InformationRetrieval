from config import config, es_client, script_dir
from pathlib import Path
from elasticsearch import Elasticsearch, exceptions, helpers
from sentence_transformers import SentenceTransformer
import torch
from tqdm import tqdm

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Using: {device}")

model = SentenceTransformer(config['w2v_model'], device=device)

actions = []
cnt = 0
batch_size = 1000

search_body = {
    "query": {
        "match_all": {}
    },
    "_source": ["title", "body"],
    "size": batch_size
}

try:
    total_docs = es_client.count(index="web_pages")['count']
except exceptions.ElasticsearchException as e:
    total_docs = None

page = es_client.search(
    index="web_pages",
    body=search_body,
    scroll='2m'
)

scroll_id = page['_scroll_id']
hits = page['hits']['hits']

if total_docs:
    pbar = tqdm(total=total_docs, desc="Processing documents", unit="doc")
else:
    pbar = tqdm(desc="Processing documents", unit="doc")

try:
    while hits:
        titles = []
        bodies = []
        doc_ids = []

        for hit in hits:
            doc_id = hit['_id']
            title = hit['_source'].get('title')
            if title is None:
                title = ''
            elif not isinstance(title, str):
                title = str(title)
            if title == '':
                title = 'Not found'

            body = hit['_source'].get('body')
            if body is None:
                body = ''
            elif not isinstance(body, str):
                body = str(body)
            if body == '':
                body = title

            titles.append(title)
            bodies.append(body)
            doc_ids.append(doc_id)

        try:
            title_vectors = model.encode(titles, convert_to_tensor=False, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
            body_vectors = model.encode(bodies, convert_to_tensor=False, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
        except Exception as e:
            page = es_client.scroll(scroll_id=scroll_id, scroll='2m')
            scroll_id = page.get('_scroll_id')
            hits = page['hits']['hits']
            continue

        for i in range(len(doc_ids)):
            actions.append({
                "_op_type": "update",
                "_index": "web_pages",
                "_id": doc_ids[i],
                "doc": {
                    "title_vector": title_vectors[i],
                    "body_vector": body_vectors[i]
                }
            })
            cnt += 1

        if len(actions) >= batch_size:
            try:
                helpers.bulk(es_client, actions)
                actions = []
                pbar.update(batch_size)
            except exceptions.ElasticsearchException as e:
                actions = []

        page = es_client.scroll(scroll_id=scroll_id, scroll='2m')
        scroll_id = page.get('_scroll_id')
        hits = page['hits']['hits']

    if actions:
        try:
            helpers.bulk(es_client, actions)
            pbar.update(len(actions))
        except exceptions.ElasticsearchException as e:
            pass

finally:
    pbar.close()