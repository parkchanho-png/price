from playwright.sync_api import sync_playwright
import json

def get_price():
    api_url = "https://mart.baemin.com/api/v3/goods?goodsIds=29605"
    
    print("🔄 Playwright로 가격 조회 중...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        try:
            page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
            
            content = page.locator('body').text_content()
            
            # 👇 뭐가 반환되는지 확인
            print(f"📊 반환 내용: {content[:200]}")
            
            data = json.loads(content)
            price = data["data"]["content"][0]["goodsPrice"]
            
            print(f"✅ 가격: {price:,}원")
            return True
            
        except json.JSONDecodeError:
            print("❌ JSON이 아니라 HTML이 반환됨")
            return False
        except Exception as e:
            print(f"❌ 에러: {str(e)}")
            return False
        
        finally:
            browser.close()

if __name__ == "__main__":
    get_price()
