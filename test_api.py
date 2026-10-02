from playwright.sync_api import sync_playwright

def get_price():
    url = "https://mart.baemin.com/goods/detail/29605"
    
    print("🔄 Playwright로 페이지 렌더링 중...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # 👇 렌더링된 페이지에서 가격 찾기
            page.wait_for_timeout(2000)
            
            # 모든 텍스트 가져오기
            all_text = page.locator('body').text_content()
            
            print(f"📊 페이지 텍스트 처음 500자:")
            print(all_text[:500])
            
            # "원" 포함된 라인 찾기
            lines = all_text.split('\n')
            for line in lines:
                if '원' in line and any(c.isdigit() for c in line):
                    print(f"✅ 가격: {line.strip()}")
                    return True
            
            print("❌ 가격을 찾을 수 없음")
            return False
            
        except Exception as e:
            print(f"❌ 에러: {str(e)}")
            return False
        
        finally:
            browser.close()

if __name__ == "__main__":
    get_price()
