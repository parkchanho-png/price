import requests
from bs4 import BeautifulSoup

def get_price():
    url = "https://mart.baemin.com/goods/detail/29605"
    
    print("🔄 배민상회 가격 조회 중...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 페이지 HTML 출력 (뭐가 있는지 확인용)
        print(f"📊 페이지 길이: {len(response.text)}")
        
        # 전체 텍스트에서 "원" 찾기
        if "원" in response.text:
            print("✅ 페이지 로드 성공")
            return True
        else:
            print("❌ 페이지 로드 실패")
            return False
            
    except Exception as e:
        print(f"❌ 에러: {str(e)}")
        return False

if __name__ == "__main__":
    get_price()
