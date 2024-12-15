from flask import Flask, render_template, request, redirect, url_for, session
from es import login, register, search, recommend, get_user_search_history
import os
import hashlib
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse

app = Flask(__name__)
app.secret_key = 'appdotsecretunderlinekey'

@app.route('/')
def home():
    logged_in = 'user_id' in session
    username = session.get('user_id', '')
    query = session.get('query', '')
    search_type = session.get('search_type', 'full')
    domain = session.get('domain', '')
    fileonly = session.get('fileonly', False)
    wildcard = session.get('wildcard', False)
    domain_value = session.get('domain_value', '')

    search_history = []
    if logged_in:
        search_history = get_user_search_history(username, max_records=10)

    return render_template('index.html', logged_in=logged_in, username=username,
                           query=query, search_type=search_type, domain=domain,
                           fileonly=fileonly, wildcard=wildcard, domain_value=domain_value,
                           search_history=search_history)

@app.route('/login', methods=['GET', 'POST'])
def login_route():
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        success, message = login(user_id, password)
        if success:
            session['user_id'] = user_id
            return redirect(url_for('home'))
        else:
            return render_template('login.html', message=message)
    logged_in = 'user_id' in session
    username = session.get('user_id', '')
    return render_template('login.html', logged_in=logged_in, username=username)

@app.route('/register', methods=['GET', 'POST'])
def register_route():
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        success, message = register(user_id, password)
        if success:
            return redirect(url_for('login_route'))
        else:
            return render_template('register.html', message=message)
    logged_in = 'user_id' in session
    username = session.get('user_id', '')
    return render_template('register.html', logged_in=logged_in, username=username)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

@app.route('/search', methods=['GET'])
def search_route():
    query = request.args.get('query', '')
    search_type = request.args.get('search_type', 'full')
    domain = request.args.get('domain', '')
    fileonly = request.args.get('fileonly', '') == 'true'
    wildcard = request.args.get('wildcard', '') == 'true'
    domain_value = request.args.get('domain_value', '')

    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    per_page = 10
    from_ = (page - 1) * per_page

    session['query'] = query
    session['search_type'] = search_type
    session['domain'] = domain
    session['fileonly'] = fileonly
    session['wildcard'] = wildcard
    session['domain_value'] = domain_value

    user_id = session.get('user_id')

    results = []
    total = 0
    search_history = []

    if query:
        results, total = search(query, top_k=per_page, search_type=search_type, user_id=user_id,
                                domain=domain_value if domain else 'nankai.edu.cn',
                                fileonly=fileonly, regex_match=wildcard, from_=from_)
    elif user_id:
        search_history = get_user_search_history(user_id, max_records=10)

    pages = (total - 1) // per_page + 1 if total > 0 else 1

    logged_in = 'user_id' in session
    username = session.get('user_id', '')
    return render_template('search_results.html', logged_in=logged_in, username=username,
                           query=query, search_type=search_type, domain=domain,
                           fileonly=fileonly, wildcard=wildcard, domain_value=domain_value,
                           results=results, page=page, pages=pages, search_history=search_history)

@app.route('/get_search_history', methods=['GET'])
def get_search_history():
    user_id = session.get('user_id')
    if user_id:
        search_history = get_user_search_history(user_id, max_records=10)
        return {'search_history': search_history}
    return {'search_history': []}

@app.route('/get_search_suggestions', methods=['GET'])
def get_search_suggestions():
    query = request.args.get('query', '')
    user_id = session.get('user_id')
    if query:
        suggestions = recommend(query, user_id=user_id, top_k=5)
        return {'suggestions': suggestions}
    return {'suggestions': []}

@app.route('/snapshot/<path:url>')
def show_snapshot(url):
    url_md5 = hashlib.md5(url.encode()).hexdigest()
    snapshot_base_dir = Path('./crawler/crawled_data/snapshot') / url_md5
    
    if not snapshot_base_dir.exists():
        return "未找到该页面的快照", 404
    
    snapshot_dirs = [d for d in snapshot_base_dir.iterdir() if d.is_dir()]
    if not snapshot_dirs:
        return "未找到该页面的快照", 404
    
    latest_snapshot = max(snapshot_dirs, key=lambda x: x.name)
    snapshot_file = latest_snapshot / 'index.html'
    
    if not snapshot_file.exists():
        return "快照文件不存在", 404

    with open(snapshot_file, 'r', encoding='utf-8') as f:
        content = f.read()

    soup = BeautifulSoup(content, 'html.parser')
    
    def process_resource_links(tag, attr):
        for element in soup.find_all(tag):
            if element.get(attr):
                src = element[attr]
                if not src.startswith(('http://', 'https://', '//')):
                    element[attr] = urljoin(url, src)

    process_resource_links('img', 'src')
    process_resource_links('script', 'src')
    process_resource_links('link', 'href')
    
    head_content = ''.join(str(tag) for tag in soup.head.contents if tag.name not in ['title'])
    body_content = ''.join(str(tag) for tag in soup.body.contents)
    title = soup.title.string if soup.title else "无标题"

    snapshot_time = datetime.strptime(latest_snapshot.name, '%Y%m%d_%H')
    formatted_time = snapshot_time.strftime('%Y年%m月%d日 %H时')

    return render_template('snapshot.html',
                         title=title,
                         head_content=head_content,
                         body_content=body_content,
                         snapshot_time=formatted_time,
                         original_url=url)

if __name__ == '__main__':
    app.run(debug=True)
