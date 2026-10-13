import re
from bs4 import BeautifulSoup

def extract_quantity(title: str) -> int:
    """상품명에서 수량(개수/박스/팩) 추출"""
    # 1. 1000개, 500입, 20팩 등
    match = re.search(r'(\d+)\s*(?:개입|개|입|팩|박스|box|매)', title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # 2. x 1000 등 곱하기 표현
    match_x = re.search(r'[xX*]\s*(\d+)', title)
    if match_x:
        return int(match_x.group(1))
        
    return 1

def parse_coupang_page(html: str, url: str, keyword: str) -> dict | None:
    """쿠팡 상세 페이지 HTML 파싱 및 단가 계산"""
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. 상품명 추출
    title_el = (
        soup.select_one("h1.prod-buy-header__title") or 
        soup.select_one("h2.prod-buy-header__title") or 
        soup.select_one("title")
    )
    if not title_el:
        return None
    title = title_el.get_text(strip=True).replace("쿠팡! - ", "")

    # 2. 판매 가격 추출
    price = 0
    price_selectors = [
        "span.total-price > strong",
        "span.prod-sale-price",
        "span.price-value",
        "div.prod-price span.price"
    ]
    for sel in price_selectors:
        price_el = soup.select_one(sel)
        if price_el:
            digits = re.sub(r'[^\d]', '', price_el.get_text())
            if digits:
                price = int(digits)
                break
                
    if price == 0:
        return None

    # 3. 배송비 추출
    shipping_fee = 0
    full_text = soup.get_text()
    if "무료배송" not in full_text and "로켓배송" not in full_text:
        fee_match = re.search(r'배송비\s*([0-9,]+)원', full_text)
        if fee_match:
            shipping_fee = int(fee_match.group(1).replace(",", ""))
        else:
            shipping_fee = 3000  # 기본 일반 택배비 보정치

    # 4. 수량 및 개당 단가 산출
    qty = extract_quantity(title)
    total_payment = price + shipping_fee
    unit_price = round(total_payment / qty, 2)

    # 5. 산출 근거 텍스트 작성
    if shipping_fee > 0:
        evidence = f"(상품가 {price:,}원 + 배송비 {shipping_fee:,}원) ÷ 추출수량 {qty}개 = 개당 {unit_price:,}원"
    else:
        evidence = f"(상품가 {price:,}원 / 무료배송) ÷ 추출수량 {qty}개 = 개당 {unit_price:,}원"

    return {
        "검색어": keyword,
        "추천 상품명": title,
        "개당 단가(원)": unit_price,
        "결제 금액(원)": total_payment,
        "추출 수량": qty,
        "산출 근거": evidence,
        "상품 링크": url
    }
