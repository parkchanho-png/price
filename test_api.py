import requests
from bs4 import BeautifulSoup
import json

def get_price():
    url = "https://mart.baemin.com/goods/detail/29605"
    
    print("🔄 배민상회 가격 조회 중...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        # 👇 HTML 처음 1000자 확인
        print(f"📊 HTML 처음 1000자:")
        print(response.text[:1000])
        print("\n")
        
        # JSON 데이터 찾기
        if "__INITIAL_STATE__" in response.text:
            print("✅ JSON 데이터 발견!")
            return True
        elif "price" in response.text:
            print("✅ price 발견!")
            return True
        elif "가격" in response.text:
            print("✅ 가격 발견!")
            return True
        else:
            print("❌ 가격 정보 못 찾음")
            return False
            
    except Exception as e:
        print(f"❌ 에러: {str(e)}")
        return False

if __name__ == "__main__":
    get_price()
