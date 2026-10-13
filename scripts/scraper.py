import json
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
import pandas as pd

# 설정 및 경로 로드
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

BASE_COUPANG_URL = "https://www.coupang.com"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_quantity(title: str) -> int:
    """상품명에서 수량 추출 (기본값: 1)"""
    patterns = [
        r'(\d+)\s*(?:개입|개|입|팩|박스|box|매)',
        r'x\s*(\d+)',
        r'총\s*(\d+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 1

def search_coupang_best_deal(page, keyword: str) -> dict | None:
    """키워드로 쿠팡 검색 후 상위 상품 중 개당 단가 최저 상품 선별"""
    encoded_kw = urllib.parse.quote(keyword)
    search_url = f"{BASE_COUPANG_URL}/np/search?component=&q={encoded_kw}&channel=user"
    
    print(f"\n[쿠팡 검색 중] 검색어: '{keyword}'")
    page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(2500)  # 동적 콘텐츠 렌더링 대기

    items = page.locator("li.search-product").all()
    if not items:
        print(f"❌ 검색 결과 없음 또는 차단 발생: {keyword}")
        return None

    candidate_products = []

    for item in items[:15]:  # 상위 15개 상품 분석
        try:
            # 1. 상품명
            name_el = item.locator("div.name")
            if not name_el.is_visible():
                continue
            title = name_el.inner_text().strip()

            # 2. 가격
            price_el = item.locator("strong.price-value")
            if not price_el.is_visible():
                continue
            price_str = price_el.inner_text().replace(",", "").strip()
            total_price = int(price_str)

            # 3. 링크 추출 및 완전한 URL 결합
            link_el = item.locator("a.search-product-link")
            raw_href = link_el.get_attribute("href")
            if not raw_href:
                continue
            product_url = BASE_COUPANG_URL + raw_href if raw_href.startswith("/") else raw_href

            # 4. 배송비 확인 (별도 표기 없을 시 0원, 배송비 감지 시 반영)
            shipping_fee = 0
            delivery_el = item.locator("span.badge.delivery")
            if not delivery_el.is_visible():
                # 일반 배송비(예: 3,000원) 등이 표기되어 있는 경우 감지
                fee_el = item.locator("span.delivery-fee")
                if fee_el.is_visible():
                    fee_match = re.search(r'\d[\d,]*', fee_el.inner_text())
                    if fee_match:
                        shipping_fee = int(fee_match.group(0).replace(",", ""))

            # 5. 수량 추출 및 개당 단가 계산
            qty = extract_quantity(title)
            final_pay = total_price + shipping_fee
            unit_price = round(final_pay / qty, 2)

            # 6. 산출 근거 텍스트 구성
            evidence = f"(상품가 {total_price:,}원 + 배송비 {shipping_fee:,}원) ÷ 추출수량 {qty}개 = 개당 {unit_price:,.1f}원"

            candidate_products.append({
                "검색어": keyword,
                "추천 상품명": title,
                "개당 단가(원)": unit_price,
                "결제 금액(원)": final_pay,
                "추출 수량": qty,
                "산출 근거": evidence,
                "상품 링크": product_url
            })
        except Exception:
            continue

    if not candidate_products:
        return None

    # 개당 단가가 가장 저렴한 1위 상품 반환
    candidate_products.sort(key=lambda x: x["개당 단가(원)"])
    return candidate_products[0]

def main():
    config = load_config()
    results = []

    with sync_playwright() as p:
        # 봇 탐지 우회를 위한 User-Agent 및 뷰포트 설정
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        for item in config.get("queries", []):
            if not item.get("active", True):
                continue

            keyword = item.get("keyword")
            best_deal = search_coupang_best_deal(page, keyword)

            if best_deal:
                best_deal["수집시각"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                results.append(best_deal)
                print(f"✅ 최저가 매칭: {best_deal['추천 상품명']} | {best_deal['산출 근거']}")
            else:
                print(f"❌ '{keyword}' 수집 실패")

            time.sleep(config.get("delay_seconds", 3))

        browser.close()

    # CSV 저장 (구글 스프레드시트 및 엑셀 지원)
    if results:
        df = pd.DataFrame(results)
        csv_path = OUTPUT_DIR / "results.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n✅ 최종 결과 CSV 저장 완료: {csv_path}")
    else:
        print("\n❌ 수집된 결과가 없습니다.")

if __name__ == "__main__":
    main()
