import requests
import json

api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://mart.baemin.com/goods/detail/29605",
    "Accept-Language": "ko-KR,ko;q=0.9"
}

print("🔄 배민상회 API 호출 중...")
response = requests.get(api_url, headers=headers, timeout=10)

print(f"📊 상태 코드: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    price = data["data"]["content"][0]["goodsPrice"]
    print(f"✅ 가격: {price:,}원")
else:
    print(f"❌ API 실패: {response.status_code}")
