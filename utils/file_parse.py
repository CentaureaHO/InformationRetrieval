from pathlib import Path
import os
import json
import doc_parser as dp
from tqdm import tqdm

types = ['pdf', 'docx', 'xlsx', 'doc', 'xls']
script_dir = Path(__file__).resolve().parent
source_dir = script_dir / '../crawler/crawled_data'
file_dir = script_dir / 'file'
file_json_dir = script_dir / 'file_json'
web_dir = script_dir / 'web'

file_json_dir.mkdir(parents=True, exist_ok=True)

subdirs = [subdir for subdir in file_dir.iterdir() if subdir.is_dir()]

for subdir in tqdm(subdirs, desc="Processing directories"):
    file_path = None
    url_txt_path = None

    for file in subdir.iterdir():
        if file.name == 'url.txt':
            url_txt_path = file
        else:
            file_path = file

    filename, ext = file_path.stem, file_path.suffix.lstrip('.')
    if not (file_path and url_txt_path and ext in types): 
        continue
    
    json_file = f'f_{filename}.json'
    title = filename
    try:
        text = ''.join(dp.parse(file_path).split('\n'))
    except Exception as e:
        print(f"解析失败: {file_path} 错误信息: {e}")
        continue

    with open(url_txt_path, 'r', encoding='utf-8') as f:
        url = f.read().strip()

    json_data = {
        'url': url,
        'title': title,
        'body': text,
        'outlinks': []
    }

    with open(file_json_dir / json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)
