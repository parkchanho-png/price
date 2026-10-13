import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import pandas as pd

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_quantity(title: str) -> int:
    """상품명에서 수량(개수/박스/팩) 추출"""
    match = re.search(r'(\d+)\s*(?:개입|개|입|팩|박스|box|매)', title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match_x = re.search(r'[xX*]\s*(\d+)', title)
    if match_x:
        return int(match_x.group(1))
    return 1

def search_products_by_keyword(keyword: str) -> list[dict]:
    """다나와 검색을 통해 쿠팡 및 온라인 최저가 상품 후보군 수집"""
    encoded_kw = urllib.parse.quote(keyword)
    url = f"https://search.danawa.com/dsearch.php?query={encoded_kw}&volumeType=allvs"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9"
    }

    candidates = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("ul.product_list > li.prod_item")

        for item in items[:10]:
            title_el = item.select_one("p.prod_name > a")
            price_el = item.select_one("p.price_sect strong")
            link_el = item.select_one("p.prod_name > a")

            if not title_el or not price_el:
                continue

            title = title_el.get_text(strip=True)
            price_str = re.sub(r'[^\d]', '', price_el.get_text(strip=True))
            if not price_str:
                continue

            price = int(price_str)
            raw_link = link_el.get("href", "")
            qty = extract_quantity(title)
            
            # 단가 및 근거 계산
            unit_price = round(price / qty, 2)
            evidence = f"총 상품가 {price:,}원 ÷ 제목 추출수량 {qty}개 = 개당 {unit_price:,}원"

            candidates.append({
                "검색어": keyword,
                "추천 상품명": title,
                "개당 단가(원)": unit_price,
                "결제 금액(원)": price,
                "추출 수량": qty,
                "산출 근거": evidence,
                "상품 링크": raw_link
            })
    except Exception as e:
        print(f"⚠️ 검색 요청 실패 ({keyword}): {str(e)}")

    return candidates

def main():
    config = load_config()
    best_results = []

    for item in config.get("queries", []):
        if not item.get("active", True):
            continue

        keyword = item["keyword"]
        print(f"\n[상품 탐색 중] '{keyword}'")
        candidates = search_products_by_keyword(keyword)

        if candidates:
            # 개당 단가 기준 최저가 선별
            candidates.sort(key=lambda x: x["개당 단가(원)"])
            best_deal = candidates[0]
            best_deal["수집시각"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            best_results.append(best_deal)
            print(f"  ✅ 최저가 확정: {best_deal['추천 상품명']} ({best_deal['개당 단가(원)']}원/개)")
            print(f"  📌 산출 근거: {best_deal['산출 근거']}")
        else:
            print(f"  ❌ '{keyword}' 검색 결과 없음")

    csv_path = OUTPUT_DIR / "results.csv"
    columns = ["검색어", "추천 상품명", "개당 단가(원)", "결제 금액(원)", "추출 수량", "산출 근거", "상품 링크", "수집시각"]

    # 결과가 없더라도 항상 CSV 파일을 생성하여 Git 오류 방지
    if best_results:
        df = pd.DataFrame(best_results)
    else:
        df = pd.DataFrame(columns=columns)

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n📁 결과 파일 저장 완료: {csv_path}")

if __name__ == "__main__":
    main()
