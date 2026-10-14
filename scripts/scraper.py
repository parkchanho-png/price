import json
import urllib.parse
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright
from parser import parse_mobile_coupang_search_html

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    config = load_config()
    delay = config.get("delay_seconds", 2)
    best_results = []

    with sync_playwright() as p:
        # 내 컴퓨터(로컬 IP)를 사용하므로 모바일 기기로 위장하여 접속
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844}
        )
        page = context.new_page()

        for idx, item in enumerate(config.get("queries", [])):
            if not item.get("active", True):
                continue

            keyword = item["keyword"]
            must_include = item.get("must_include")  # 상품명에 꼭 있어야 하는 단어 (config.json에서 설정)
            exclude = item.get("exclude")            # 상품명에 있으면 제외할 단어
            print(f"\n[쿠팡 검색 중] 검색어: '{keyword}'")
            encoded_kw = urllib.parse.quote(keyword)
            search_url = f"https://m.coupang.com/nm/search?q={encoded_kw}"

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)  # 상품 리스트가 렌더링될 때까지 충분히 대기
                html = page.content()

                candidates = parse_mobile_coupang_search_html(html, keyword, must_include, exclude)

                if candidates:
                    candidates.sort(key=lambda x: x["개당 단가(원)"])
                    best_deal = candidates[0]
                    best_deal["수집시각"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    best_results.append(best_deal)
                    print(f"  ✅ 최저가 확정: {best_deal['추천 상품명']}")
                    print(f"  📌 산출 근거: {best_deal['산출 근거']}")
                else:
                    # 원인 분석용으로 받아온 페이지를 저장 (차단 페이지인지, 태그가 바뀐 건지 확인)
                    debug_path = OUTPUT_DIR / f"debug_{idx}.html"
                    debug_path.write_text(html, encoding="utf-8")
                    print(f"  ❌ '{keyword}' 수집 가능한 매물 없음 (페이지 {len(html):,}자, 저장: {debug_path.name})")

            except Exception as e:
                print(f"  ⚠️ 검색 에러 발생 ({keyword}): {str(e)}")

            time.sleep(delay)

        browser.close()

    # CSV 저장 및 Git push 중단 방지(빈 배열이어도 생성)
    csv_path = OUTPUT_DIR / "results.csv"
    columns = ["검색어", "추천 상품명", "개당 단가(원)", "결제 금액(원)", "추출 수량", "산출 근거", "상품 링크", "수집시각"]
    df = pd.DataFrame(best_results) if best_results else pd.DataFrame(columns=columns)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n📁 결과 파일 저장 완료: {csv_path}")

if __name__ == "__main__":
    main()
