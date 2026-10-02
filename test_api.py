# test_api.py (저장소 루트에 생성)

import requests
import json

# 배민상회 API 직접 호출
api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

print("🔄 배민상회 API 호출 중...")
response = requests.get(api_url, headers=headers, timeout=10)

print(f"📊 상태 코드: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print("✅ API 성공!")
    print("\n📝 응답 데이터:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print(f"❌ API 실패: {response.status_code}")
    print(response.text)
