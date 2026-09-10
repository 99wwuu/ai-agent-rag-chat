# 网络搜索API工具类
import requests
from pydantic import Field
from configs.setting import TIME_OUT

class WebSearch:
    query: str = Field(description="需要网上查找的内容")

    def __init__(self, api_key):
        # 初始化函数，用于创建类的实例
        self.api_key = api_key

    def run(self, query):
        base_url = "https://serpapi.com/search"

        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "baidu",
            "rn": 5,           # 检索结果前5个
            "proxy": "http://api.wlai.vip" # 代理（用了这个好像不会减使用次数）
        }

        # 发送请求到网络搜索API
        # print(url)
        response = requests.get(base_url, params=params, timeout=TIME_OUT)
        # print(response.status_code)
        # 如果请求成功，解析返回数据
        if response.status_code == 200:
            data = response.json()
            print(data)
            organic_results = data['organic_results'][0]['related_news'] if data['organic_results'][0].get('related_news') else data['organic_results']

            # 获取网络信息
            results = "".join([f"titles:\n{result.get('title', '')} \nlinks:\n{result.get('link', '')}\nsnippets:\n{result.get('snippet', '')}\n" for result in organic_results])
            return results

        else:
            return f"无法获取{query}的信息"


web_search = WebSearch("0c38eac10d9b5c03b6007ece56f6c84372cdf86358e5c780fc4b87ae471ff582")
