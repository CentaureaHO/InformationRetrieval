from sentence_transformers import SentenceTransformer
import torch
from datetime import datetime
import numpy as np
from elasticsearch import Elasticsearch, exceptions
import urllib3
import json
from pathlib import Path
import hashlib

script_dir = Path(__file__).resolve().parent

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', device=device)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

es = Elasticsearch(
    ["https://localhost:9200"],
    basic_auth=("elastic", "1234567"),
    verify_certs=False
)

def log_search_query(user_id, query, domain):
    index_name = "search_history"
    document = {
        "user_id": user_id,
        "search_query": query,
        "domain": domain,
        "timestamp": datetime.now().isoformat()
    }
    try:
        es.index(index=index_name, document=document)
        print(f"Logged search query: {query}")
    except Exception as e:
        print(f"Failed to log search query: {str(e)}")

def get_user_search_history(user_id, max_records=20):
    search_body = {
        "size": max_records * 2,
        "query": {
            "term": {
                "user_id": user_id
            }
        },
        "sort": [
            {
                "timestamp": {
                    "order": "desc"
                }
            }
        ],
        "_source": ["search_query"]
    }
    try:
        response = es.search(index="search_history", body=search_body)
        history = []
        seen_queries = set()
        for hit in response['hits']['hits']:
            query = hit['_source']['search_query']
            if query not in seen_queries:
                seen_queries.add(query)
                history.append(query)
            if len(history) >= max_records:
                break
        return history
    except Exception as e:
        print(f"Failed to fetch search history for user {user_id}: {str(e)}")
        return []
    
def get_global_search_history(max_records=50):
    search_body = {
        "size": max_records,
        "query": {
            "match_all": {}
        },
        "sort": [
            {
                "timestamp": {
                    "order": "desc"
                }
            }
        ],
        "_source": ["search_query"]
    }
    response = es.search(index="search_history", body=search_body)
    global_history = [hit['_source']['search_query'] for hit in response['hits']['hits']]
    return global_history
    
def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def recommend(query, user_id=None, top_k=10):
    global_history = get_global_search_history(max_records=50)
    user_history = get_user_search_history(user_id, max_records=20) if user_id else []
    query_embedding = model.encode(query, convert_to_tensor=True)

    global_results = []
    for history_query in global_history:
        history_embedding = model.encode(history_query, convert_to_tensor=True)
        similarity = cosine_similarity(query_embedding.cpu().numpy(), history_embedding.cpu().numpy())
        global_results.append({"query": history_query, "score": similarity})

    weighted_results = []
    for result in global_results:
        query_text = result["query"]
        base_score = result["score"]
        
        if not user_history:
            weighted_results.append({"query": query_text, "score": base_score})
            continue
        
        user_scores = []
        for user_query in user_history:
            user_embedding = model.encode(user_query, convert_to_tensor=True)
            user_similarity = cosine_similarity(
                model.encode(query_text, convert_to_tensor=True).cpu().numpy(),
                user_embedding.cpu().numpy()
            )
            user_scores.append(user_similarity)
        
        weighted_score = base_score + 0.5 * max(user_scores)
        weighted_results.append({"query": query_text, "score": weighted_score})

    unique_results = {}
    for result in weighted_results:
        if result["query"] not in unique_results:
            unique_results[result["query"]] = result["score"]
    sorted_results = sorted(unique_results.items(), key=lambda x: x[1], reverse=True)[:top_k]

    return [{"query": query, "score": score} for query, score in sorted_results]

def search(query, top_k=10, search_type='full', user_id=None, domain='nankai.edu.cn',
           fileonly=False, regex_match=False, from_=0):
    try:
        if user_id:
            log_search_query(user_id, query, domain)

        history = get_user_search_history(user_id) if user_id else []

        if search_type in ['title', 'full']:
            query_vector = model.encode(query, normalize_embeddings=True).tolist()

        domain_filter = {
            "bool": {
                "must": [
                    {
                        "wildcard": {
                            "url": f"*{domain}*"
                        }
                    }
                ]
            }
        }

        if fileonly:
            domain_filter["bool"]["must"].append({
                "term": {
                    "is_file": True
                }
            })

        terms = query.split()

        if search_type == 'exact':
            with open(script_dir / "es/query/exact.json", "r") as f:
                search_body = json.load(f)
            search_body["size"] = top_k
            search_body["query"]["bool"]["must"].append(domain_filter)
            for term in terms:
                search_body["query"]["bool"]["must"][0]["bool"]["must"].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["title", "body"],
                        "type": "phrase"
                    }
                })      
        elif search_type == 'title':
            with open(script_dir / "es/query/title.json", "r") as f:
                search_body = json.load(f)
            search_body["size"] = top_k
            if regex_match:
                wildcard_conditions = []
                for term in terms:
                    wildcard_conditions.append({
                        "wildcard": {
                            "raw_title": f"*{term}*"
                        }
                    })
                search_body["query"]["bool"]["must"][0]["bool"]["should"].extend(wildcard_conditions)
                search_body["query"]["bool"]["must"][0]["bool"]["minimum_should_match"] = len(terms)
            else:
                for term in terms:
                    search_body["query"]["bool"]["must"][0]["bool"]["should"].append({
                        "match": {
                            "title": {
                                "query": term,
                                "boost": 2
                            }
                        }
                    })
            search_body["query"]["bool"]["must"][1]["function_score"]["functions"][0]["script_score"]["script"]["params"]["query_vector"] = query_vector
            search_body["query"]["bool"]["filter"] = domain_filter
        else:
            with open("es/query/full.json", "r") as f:
                search_body = json.load(f)
            search_body["size"] = top_k
            for term in terms:
                search_body["query"]["bool"]["must"][0]["bool"]["should"].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["title", "body"],
                        "type": "most_fields"
                    }
                })
            search_body["query"]["bool"]["must"][1]["function_score"]["functions"][0]["script_score"]["script"]["params"]["query_vector"] = query_vector
            search_body["query"]["bool"]["filter"] = domain_filter
        
        if history:
            history_query = " ".join(history[:20])
            search_body["query"]["bool"]["should"] = [
                {
                    "match": {
                        "title": {
                            "query": history_query,
                            "boost": 1
                        }
                    }
                },
                {
                    "match": {
                        "body": {
                            "query": history_query,
                            "boost": 0.5
                        }
                    }
                }
            ]

        search_body["from"] = from_
        search_body["size"] = top_k

        response = es.search(index="web_pages", body=search_body)
        total = response['hits']['total']['value']

        results = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            results.append({
                "url": source.get('url', ''),
                "title": source.get('title', ''),
                "pagerank": source.get('pagerank', 0),
                "score": hit['_score'],
                "body": source.get('body', ''),
                "is_file": source.get('is_file', False)
            })

        return results, total
    
    except exceptions.BadRequestError as e:
        print("BadRequestError:", e.info)
        return [], 0
    except exceptions.RequestError as e:
        print("RequestError:", e.info)
        return [], 0
    except Exception as e:
        print("Unexpected error:", str(e))
        return [], 0
    
def hash_password(password):
    """使用 SHA-256 对密码进行哈希加密"""
    return hashlib.sha256(password.encode()).hexdigest()

def register(user_id, password):
    search_body = {
        "query": {
            "term": {
                "user_id": user_id
            }
        }
    }
    response = es.search(index='users', body=search_body)
    if response['hits']['total']['value'] > 0:
        return False, "用户已存在，请选择其他用户名。"

    document = {
        "user_id": user_id,
        "password": hash_password(password)
    }
    try:
        es.index(index='users', document=document)
        return True, "注册成功。"
    except Exception as e:
        return False, f"注册失败：{str(e)}"

def login(user_id, password):
    search_body = {
        "query": {
            "term": {
                "user_id": user_id
            }
        }
    }
    response = es.search(index='users', body=search_body)
    if response['hits']['total']['value'] == 0:
        return False, "用户不存在，请先注册。"

    stored_password = response['hits']['hits'][0]['_source']['password']
    if stored_password == hash_password(password):
        return True, "登录成功。"
    else:
        return False, "密码错误，请重试。"