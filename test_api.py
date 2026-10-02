from playwright.sync_api import sync_playwright
import json

def get_price():
    api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"
    
    print("🔄 Playwright로 가격 조회 중...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # API URL 직접 접속 (HTML이 아니라 JSON 반환)
            page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
            
            # 페이지 내용 추출 (JSON)
            content = page.text_content()
            
            # JSON 파싱
            data = json.loads(content)
            price = data["data"]["content"][0]["goodsPrice"]
            
            print(f"✅ 가격: {price:,}원")
            return True
            
        except Exception as e:
            print(f"❌ 에러: {str(e)}")
            return False
        
        finally:
            browser.close()

if __name__ == "__main__":
    get_price()
