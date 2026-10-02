from playwright.sync_api import sync_playwright
import json

api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"

print("🔄 Playwright로 API 호출 중...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    try:
        # 네트워크 응답 가로채기
        def handle_response(response):
            if "goodsIds" in response.url and response.status == 200:
                print(f"✅ 응답 URL: {response.url}")
                data = response.json()
                price = data["data"]["content"][0]["goodsPrice"]
                print(f"✅ 가격: {price:,}원")
        
        page.on("response", handle_response)
        page.goto("https://mart.baemin.com/goods/detail/29605", wait_until="networkidle", timeout=15000)
        
        page.wait_for_timeout(2000)  # 2초 대기
        
    except Exception as e:
        print(f"❌ 에러: {str(e)}")
    
    finally:
        browser.close()
