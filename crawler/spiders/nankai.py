import scrapy
from urllib.parse import urlparse, unquote, urljoin
import os
import json
from docx import Document
from bs4 import BeautifulSoup
import fitz
import hashlib
import io
import time
from ..items import WebItem, DocItem
from datetime import datetime
import re
import requests

class Nankai(scrapy.Spider):
    begin_time = time.time()

    name = 'nankai'
    allowed_domains = [
        # 'nankai.edu.cn',
        # 下面两个网站响应速度太慢，爬够10w后再爬
        'shsj.nankai.edu.cn',
        'zyfw.nankai.edu.cn',
    ]
    start_urls = [
        'http://shsj.nankai.edu.cn/',
        'https://zyfw.nankai.edu.cn/',
    ]
    output_directory = './crawled_data/'
    web_directory = './crawled_data/web/'
    file_directory = './crawled_data/file/'
    snapshot_directory = './crawled_data/snapshot/'
    max_pages = 20000
    pages_crawled = 0

    def __init__(self, *args, **kwargs):
        super(Nankai, self).__init__(*args, **kwargs)
        if not os.path.exists(self.output_directory):
            os.makedirs(self.output_directory)
        if not os.path.exists(self.web_directory):
            os.makedirs(self.web_directory)
        if not os.path.exists(self.file_directory):
            os.makedirs(self.file_directory)
        if not os.path.exists(self.snapshot_directory):
            os.makedirs(self.snapshot_directory)

        self.done_log = False

    def parse(self, response):
        """主页面解析方法"""
        if self.pages_crawled >= self.max_pages:
            if not self.done_log:
                self.done_log = True
                self.logger.info(f"Reached max page count: {self.max_pages}, stopping crawl.")
            return
        
        if response.status != 200:
            self.logger.error(f"Failed to fetch {response.url}: {response.status}")
            return

        # if 'zyfw.nankai.edu.cn' in response.url or 'shsj.nankai.edu.cn' in response.url:
        #     self.logger.info(f"Skipping {response.url} due to slow response.")
        #     return
        
        url = response.url
        if "text/html" in response.headers.get('Content-Type', '').decode():
            soup = BeautifulSoup(response.text, 'lxml')
            for script in soup(["script", "style", "header", "footer", "nav"]):
                script.decompose()
        
            body = self.clean_text(soup.get_text(separator=' ', strip=True))

            item = WebItem()
            item['url'] = response.url
            item['title'] = response.css('title::text').get()
            item['body'] = body
            item['outlinks'] = []

            self.pages_crawled += 1

            for link in soup.find_all('a', href=True):
                full_url = response.urljoin(link['href'])
                if not full_url.startswith('http'):
                    continue
                if 'nankai.edu.cn' not in full_url:
                    continue
                # if 'zyfw.nankai.edu.cn' in full_url or 'shsj.nankai.edu.cn' in full_url:
                #     continue
                item['outlinks'].append(full_url)
                if self.pages_crawled < self.max_pages:
                    yield scrapy.Request(full_url, callback=self.parse)

            url_md5 = hashlib.md5(url.encode()).hexdigest()
            filepath = os.path.join(self.web_directory, f'w_{url_md5}.json')

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(dict(item), f, ensure_ascii=False, indent=4)

            snapshot_dir, resource_urls = self.save_snapshot(response, url_md5)
            for res_url in resource_urls:
                yield scrapy.Request(
                res_url,
                callback=self.save_resource,
                meta={'snapshot_dir': snapshot_dir, 'resource_url': res_url}
            )

            self.save_snapshot(response, url_md5)
        else:
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            filename = unquote(filename)

            if not filename:
                filename = hashlib.md5(url.encode('utf-8')).hexdigest()
                content_type = response.headers.get('Content-Type', b'').decode()
                extension = self.get_extension(content_type)
                filename += extension

            filename_noext, ext = os.path.splitext(filename)
            if ext not in ['.pdf', '.docx', '.doc', '.xls', '.xlsx', '.jpg', '.png', '.txt']:
                return

            filepath = os.path.join(self.file_directory, filename_noext)
            if os.path.exists(filepath):
                unique_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
                filename_noext = f"{filename_noext}_{unique_hash}"
                filepath = os.path.join(self.file_directory, filename_noext)

            os.mkdir(filepath)

            try:
                with open(f'{filepath}/url.txt', 'w') as f:
                    f.write(url)
                with open(f'{filepath}/{filename_noext}{ext}', 'wb') as f:
                    f.write(response.body)
            except Exception as e:
                self.logger.error(f"Failed to save file {filename}: {str(e)}")
                return
        
            if ext.lower() not in ['.pdf', '.docx', '.doc']:
                return
            self.pages_crawled += 1
            item = WebItem()
            item['url'] = response.url
            item['title'] = filename_noext
            item['body'] = ''
            if ext.lower() == '.pdf':
                item['body'] = self.extract_pdf_text(response)
            elif ext.lower() == '.docx':
                item['body'] = self.extract_docx_text(response)
            item['outlinks'] = []
            with open(f'{self.web_directory}/f_{filename_noext}.json', 'w', encoding='utf-8') as f:
                json.dump(dict(item), f, ensure_ascii=False, indent=4)
        
        if self.pages_crawled % 100 == 0:
            elapsed_time = time.time() - self.begin_time
            self.logger.info(f"Pages crawled: {self.pages_crawled}, elapsed time: {elapsed_time:.2f} s")

    def save_snapshot(self, response, url_md5):
        """
        保存网页快照，包括 index.html 和相关的资源文件。
    
        返回:
            snapshot_dir (str): 快照目录的路径。
            resource_urls (list): 资源文件的绝对 URL 列表。
        """
        url = response.url
        snapshot_dir = os.path.join(self.snapshot_directory, url_md5)
        if not os.path.exists(snapshot_dir):
            os.makedirs(snapshot_dir)
        formatted_time = datetime.now().strftime('%Y%m%d_%H')
        snapshot_dir = os.path.join(snapshot_dir, formatted_time)
        if os.path.exists(snapshot_dir):
            return snapshot_dir, []

        os.makedirs(snapshot_dir)

        # 1. 保存 index.html
        index_path = os.path.join(snapshot_dir, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(response.text)

        # 2. 解析 index.html 并提取资源链接
        soup = BeautifulSoup(response.text, 'lxml')
        resource_links = set()

        # 提取 <img> 标签的 src 属性
        for img in soup.find_all('img', src=True):
            src = img['src']
            if not src.startswith(('http://', 'https://')):
                resource_links.add(src)

        # 提取 <script> 标签的 src 属性
        for script in soup.find_all('script', src=True):
            src = script['src']
            if not src.startswith(('http://', 'https://')):
                resource_links.add(src)

        # 提取 <link> 标签的 href 属性（仅限 CSS）
        for link in soup.find_all('link', href=True):
            rel = link.get('rel')
            if rel and 'stylesheet' in rel:
                href = link['href']
                if not href.startswith(('http://', 'https://')):
                    resource_links.add(href)

        # 3. 构造资源的绝对 URL
        resource_urls = [response.urljoin(link) for link in resource_links]

        return snapshot_dir, resource_urls
    
    def save_resource(self, response):
        """
        保存资源文件（.jpg, .png, .js, .css）到快照目录中。
        """
        snapshot_dir = response.meta['snapshot_dir']
        resource_url = response.meta['resource_url']

        parsed_url = urlparse(resource_url)
        resource_path = parsed_url.path.lstrip('/')  # 去除前导斜杠

        # 构造保存路径
        resource_full_path = os.path.join(snapshot_dir, resource_path)
        resource_dir = os.path.dirname(resource_full_path)

        if not os.path.exists(resource_dir):
            os.makedirs(resource_dir)

        try:
            with open(resource_full_path, 'wb') as f:
                f.write(response.body)
            # self.logger.info(f"Saved resource: {resource_full_path}")
        except Exception as e:
            self.logger.error(f"Failed to save resource {resource_url}: {str(e)}")

    def get_extension(self, content_type):
        """根据 Content-Type 返回文件扩展名"""
        mapping = {
            'application/pdf': '.pdf',
            'application/msword': '.doc',
            'application/vnd.ms-excel': '.xls',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'application/zip': '.zip',
            'text/plain': '.txt',
        }
        return mapping.get(content_type.split(';')[0].lower(), '')

    def extract_pdf_text(self, response):
        try:
            # 使用 PyMuPDF 读取 PDF 文件
            doc = fitz.open(stream=response.body, filetype="pdf")
            text = ''
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                text += page.get_text("text")
            return self.clean_text(text)
        except Exception as e:
            self.logger.error(f"Failed to extract PDF text from {response.url}: {str(e)}")
            return ''

    def extract_docx_text(self, response):
        try:
            doc = Document(io.BytesIO(response.body))
            text = ''
            for para in doc.paragraphs:
                text += para.text + '\n'
            return self.clean_text(text)
        except Exception as e:
            self.logger.error(f"Failed to extract DOCX text from {response.url}: {str(e)}")
            return ''

    def clean_text(self, text):
        """清洗文本：去除换行符、空格及不需要的符号，包括乱码字符"""
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').strip()
        text = ' '.join(text.split())
        return text