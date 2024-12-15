from pathlib import Path
from elasticsearch import Elasticsearch, helpers, exceptions
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

script_dir = Path(__file__).resolve().parent
config_path = script_dir / 'config.json'
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

es_addr = [f"https://{addr['host']}:{addr['port']}" for addr in config['es']['addr']]
es_auth = (config['es']['username'], config['es']['password'])
es_client = Elasticsearch(
    hosts = es_addr,
    basic_auth = es_auth,
    verify_certs = config['es']['verify_certs']
)