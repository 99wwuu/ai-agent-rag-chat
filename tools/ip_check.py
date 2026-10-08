# IP归属地查询工具类（使用 ip-api.com 免费接口，无需 API Key）
import requests
from configs.setting import TIME_OUT


class IpCheck:
    def run(self, ip):
        url = f"http://ip-api.com/json/{ip}"
        params = {"lang": "zh-CN"}

        # 发送GET请求查询IP归属地
        response = requests.get(url, params=params, timeout=TIME_OUT)

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return (
                    f"IP {data.get('query')} 的归属地："
                    f"{data.get('country')} {data.get('regionName')} {data.get('city')}，"
                    f"运营商：{data.get('isp')}"
                )
            return f"无法查询 IP {ip}"
        return f"无法获取 {ip} 的信息"


ip_check = IpCheck()
