from playwright.sync_api import sync_playwright
import json

def get_price():
    api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"
    
    print("🔄 Playwright로 가격 조회 중...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
            
            # 👇 수정: body 선택자 추가
            content = page.locator('body').text_content()
            
            # JSON 파싱
            data = json.loads(content)
            price = data["data"]["content"][0]["goodsPrice"]
            
            print(f"✅ 가격: {price:,}원")
            return True
            
        except Exception as e:
            print(f"❌ 에러: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            browser.close()

if __name__ == "__main__":
    get_price()
