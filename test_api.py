from playwright.sync_api import sync_playwright
import json
import sys

def extract_price():
    api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"
    product_url = "https://mart.baemin.com/goods/detail/29605"
    
    print("🔄 Playwright로 가격 조회 중...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        captured_data = {"response": None}
        
        def handle_response(response):
            if "goodsIds=29605" in response.url and response.status == 200:
                try:
                    captured_data["response"] = response.json()
                except:
                    pass
        
        page.on("response", handle_response)
        
        try:
            page.goto(product_url, wait_until="networkidle", timeout=30000)
            
            # API 응답 대기
            page.wait_for_timeout(2000)
            
            if captured_data["response"]:
                data = captured_data["response"]
                price = data["data"]["content"][0]["goodsPrice"]
                print(f"✅ 가격: {price:,}원")
                return True
            else:
                print("❌ API 응답 캡처 실패")
                return False
                
        except Exception as e:
            print(f"❌ 에러: {str(e)}")
            return False
        
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    success = extract_price()
    sys.exit(0 if success else 1)
