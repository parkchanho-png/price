import json
import re
import time
from datetime import datetime
from pathlib import Path
from duckduckgo_search import DDGS
from playwright.sync_api import sync_playwright
import pandas as pd
from parser import parse_coupang_page

# 경로 설정
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_coupang_urls_by_keyword(keyword: str, max_count: int = 4) -> list[str]:
    """자연어 검색어를 기반으로 쿠팡 상세 상품 링크 목록 획득"""
    print(f"\n[검색어 링크 탐색] '{keyword}'")
    query = f"site:coupang.com/vp/products {keyword}"
    urls = []
    
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_count * 2)
            for r in results:
                href = r.get("href", "")
                # 쿠팡 상세 페이지 URL 형태 정규화
                match = re.search(r'(https://www\.coupang\.com/vp/products/\d+)', href)
                if match:
                    clean_url = match.group(1)
                    if clean_url not in urls:
                        urls.append(clean_url)
                if len(urls) >= max_count:
                    break
    except Exception as e:
        print(f"⚠️ 검색 엔진 호출 오류: {str(e)}")
        
    print(f"🔗 탐색된 쿠팡 상품 링크: {len(urls)}개")
    return urls

def main():
    config = load_config()
    delay = config.get("delay_seconds", 3)
    max_candidates = config.get("max_candidates_per_query", 4)
    best_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        for item in config.get("queries", []):
            if not item.get("active", True):
                continue

            keyword = item["keyword"]
            urls = get_coupang_urls_by_keyword(keyword, max_candidates)
            
            candidates = []
            for url in urls:
                try:
                    print(f"  [상품 수집 중] {url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    html = page.content()
                    parsed = parse_coupang_page(html, url, keyword)
                    if parsed:
                        candidates.append(parsed)
                except Exception as e:
                    print(f"  ⚠️ 페이지 조회 실패 ({url}): {str(e)}")
                
                time.sleep(delay)

            # 해당 키워드의 후보 중 '개당 단가' 기준 최저가 선정
            if candidates:
                candidates.sort(key=lambda x: x["개당 단가(원)"])
                best_deal = candidates[0]
                best_deal["수집시각"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                best_results.append(best_deal)
                print(f"  ✅ 최저가 확정: {best_deal['추천 상품명']} | {best_deal['산출 근거']}")
            else:
                print(f"  ❌ '{keyword}' 조건에 부합하는 상품을 찾지 못했습니다.")

        browser.close()

    # CSV 파일로 최종 저장
    if best_results:
        df = pd.DataFrame(best_results)
        csv_path = OUTPUT_DIR / "results.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n🎉 [성공] 결과 저장 완료: {csv_path}")
    else:
        print("\n❌ 저장할 수집 결과가 없습니다.")

if __name__ == "__main__":
    main()
