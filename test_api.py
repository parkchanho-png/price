from playwright.sync_api import sync_playwright
import json

api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"

print("🔄 Playwright로 API 호출 중...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    try:
        page.goto(api_url, wait_until="domcontentloaded", timeout=15000)
        
        # 페이지 텍스트 가져오기 (JSON)
        response_text = page.text_content()
        
        # JSON 파싱
        data = json.loads(response_text)
        price = data["data"]["content"][0]["goodsPrice"]
        
        print(f"✅ 가격: {price:,}원")
        
    except Exception as e:
        print(f"❌ 에러: {str(e)}")
    
    finally:
        browser.close()
