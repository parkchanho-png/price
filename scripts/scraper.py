import json
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
import pandas as pd
from parser import parse_baemin_price, parse_coupang_price

# 설정 로드
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def scrape_product(config_item):
    """플랫폼별 가격 수집"""
    platform = config_item["platform"]
    url = config_item["url"]
    
    print(f"[수집 중] {config_item['name']} ({url})")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # 동적 콘텐츠 로딩 대기
            page.wait_for_timeout(3000)
            
            html = page.content()
            
            # 플랫폼별 파서 호출
            if platform == "baemin":
                price_data = parse_baemin_price(html, config_item)
            elif platform == "coupang":
                price_data = parse_coupang_price(html, config_item)
            else:
                price_data = None
            
            browser.close()
            
            if price_data:
                print(f"✅ 수집 완료: {price_data}")
                return price_data
            else:
                print(f"❌ 파싱 실패: {url}")
                return None
                
    except Exception as e:
        print(f"❌ 에러: {url} - {str(e)}")
        return None

def main():
    config = load_config()
    results = []
    
    for product in config["products"]:
        if not product["active"]:
            continue
        
        result = scrape_product(product)
        if result:
            result["timestamp"] = datetime.now().isoformat()
            results.append(result)
        
        time.sleep(config["delay_seconds"])
    
    # CSV 저장
    if results:
        df = pd.DataFrame(results)
        csv_path = OUTPUT_DIR / "results.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n✅ CSV 저장: {csv_path}")
        
        # 비교표 생성
        from compare import generate_report
        generate_report(df, OUTPUT_DIR)
    else:
        print("\n❌ 수집된 데이터 없음")

if __name__ == "__main__":
    main()
