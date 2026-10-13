import re
from bs4 import BeautifulSoup

def extract_quantity(title: str) -> int:
    """상품명에서 수량 추출"""
    match = re.search(r'(\d+)\s*(?:개입|개|입|팩|박스|box|매)', title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match_x = re.search(r'[xX*]\s*(\d+)', title)
    if match_x:
        return int(match_x.group(1))
    return 1

def parse_mobile_coupang_search_html(html: str, keyword: str) -> list[dict]:
    """모바일 쿠팡 검색 결과 HTML 파싱 및 단가 계산"""
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    
    # 모바일 쿠팡 검색 결과 상품 리스트 태그
    items = soup.select("li.search-product, li[class*='product']")

    for item in items[:10]:
        title_el = item.select_one(".name, .title")
        price_el = item.select_one(".price-value, strong.price")
        link_el = item.select_one("a")

        if not title_el or not price_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        
        # 가격 정수 변환
        price_str = re.sub(r'[^\d]', '', price_el.get_text())
        if not price_str:
            continue
        price = int(price_str)

        # 링크에서 상품 ID 파싱 및 PC버전 상세 URL로 변환
        raw_href = link_el.get("href", "")
        match_id = re.search(r'products/(\d+)', raw_href)
        if match_id:
            product_url = f"https://www.coupang.com/vp/products/{match_id.group(1)}"
        else:
            product_url = f"https://www.coupang.com{raw_href}" if raw_href.startswith("/") else raw_href

        # 배송비 판별 (로켓/무료 배송 뱃지가 없으면 기본 3000원 부여)
        full_text = item.get_text()
        shipping_fee = 0 if ("무료" in full_text or "로켓" in full_text) else 3000

        qty = extract_quantity(title)
        final_pay = price + shipping_fee
        unit_price = round(final_pay / qty, 2)

        evidence = f"(상품가 {price:,}원 + 배송비 {shipping_fee:,}원) ÷ 추출수량 {qty}개 = 개당 {unit_price:,}원"

        candidates.append({
            "검색어": keyword,
            "추천 상품명": title,
            "개당 단가(원)": unit_price,
            "결제 금액(원)": final_pay,
            "추출 수량": qty,
            "산출 근거": evidence,
            "상품 링크": product_url
        })
        
    return candidates
