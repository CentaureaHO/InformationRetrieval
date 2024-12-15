from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
import threading
import time

def run_crawler():
    process = CrawlerProcess(get_project_settings())
    process.crawl("nankai")  # 爬虫名为 "nankai"
    process.start()  # 阻塞运行爬虫

if __name__ == "__main__":
    # 在独立线程中启动爬虫
    crawler_thread = threading.Thread(target=run_crawler)
    crawler_thread.start()

    print("爬虫已启动，输入 'stop' 停止运行")
    while True:
        command = input()
        if command.lower() == "stop":
            print("正在停止爬虫...")
            time.sleep(2)
            raise SystemExit("用户手动停止爬虫")
