import re
from bs4 import BeautifulSoup

NUM = r'\d{1,3}(?:,\d{3})+|\d+'  # 1,000 / 1000 둘 다 한 덩어리 숫자로 인식


def to_int(s: str) -> int:
    return int(s.replace(",", ""))


def extract_quantity(title: str) -> int:
    """상품명에서 총 수량 추출 (못 찾으면 0 반환)"""
    candidates = []

    # 1) "50개입 x 20줄", "100개 20박스" 같은 곱셈 표기 → 곱해서 총 수량 계산
    for m in re.finditer(
        rf'({NUM})\s*(?:개입|개|입|매)\s*[xX×*]?\s*({NUM})\s*(?:줄|박스|팩|봉|세트|묶음|box)',
        title, re.IGNORECASE
    ):
        candidates.append(to_int(m.group(1)) * to_int(m.group(2)))

    # 2) "1,000개", "1000매", "500입" 같은 단독 수량 표기
    for m in re.finditer(rf'({NUM})\s*(?:개입|개|입|매|ea|pcs)', title, re.IGNORECASE):
        candidates.append(to_int(m.group(1)))

    # 3) "50 x 20" 같은 숫자끼리 곱셈
    for m in re.finditer(rf'({NUM})\s*[xX×*]\s*({NUM})', title):
        candidates.append(to_int(m.group(1)) * to_int(m.group(2)))

    # 4) "20박스", "10팩"만 있는 경우
    if not candidates:
        for m in re.finditer(rf'({NUM})\s*(?:팩|박스|box|봉|줄)', title, re.IGNORECASE):
            candidates.append(to_int(m.group(1)))

    candidates = [c for c in candidates if c > 0]
    # 총 수량이 보통 가장 큰 숫자이므로 최댓값 사용
    return max(candidates) if candidates else 0


def parse_price(text: str) -> int:
    """가격 텍스트에서 첫 번째 금액만 추출 (원가/단가가 같이 있어도 숫자가 합쳐지지 않게)"""
    m = re.search(NUM, text)
    return to_int(m.group(0)) if m else 0


def matches_filters(title: str, must_include=None, exclude=None) -> bool:
    """상품명이 조건에 맞는지 검사
    - must_include: [["24온스","24oz"], ["98파이"]] → 바깥 목록은 모두(AND), 안쪽 목록은 하나라도(OR) 포함
    - exclude: ["뚜껑", "빨대"] → 하나라도 포함되면 제외
    """
    t = title.lower().replace(" ", "")
    for group in (must_include or []):
        if isinstance(group, str):
            group = [group]
        if not any(g.lower().replace(" ", "") in t for g in group):
            return False
    for word in (exclude or []):
        if word.lower().replace(" ", "") in t:
            return False
    return True


def parse_mobile_coupang_search_html(html: str, keyword: str, must_include=None, exclude=None) -> list[dict]:
    """모바일 쿠팡 검색 결과 HTML 파싱 및 단가 계산"""
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    # 모바일 쿠팡 검색 결과 상품 리스트 태그
    items = soup.select("li.search-product, li[class*='product']")

    for item in items[:40]:
        title_el = item.select_one(".name, .title")
        price_el = item.select_one(".price-value, strong.price")
        link_el = item.select_one("a")

        if not title_el or not price_el or not link_el:
            continue

        title = title_el.get_text(strip=True)

        # 뚜껑, 다른 용량 등 검색어와 무관한 상품 제외
        if not matches_filters(title, must_include, exclude):
            continue

        price = parse_price(price_el.get_text())
        if price <= 0:
            continue

        # 링크에서 상품 ID 파싱 및 PC버전 상세 URL로 변환
        raw_href = link_el.get("href", "")
        match_id = re.search(r'products/(\d+)', raw_href)
        if match_id:
            product_url = f"https://www.coupang.com/vp/products/{match_id.group(1)}"
        else:
            product_url = f"https://www.coupang.com{raw_href}" if raw_href.startswith("/") else raw_href

        # 배송비 판별: '무료반품' 같은 문구에 속지 않도록 '무료배송'/'로켓'만 인정
        full_text = re.sub(r'\s+', '', item.get_text())
        shipping_fee = 0 if ("무료배송" in full_text or "로켓" in full_text) else 3000

        qty = extract_quantity(title)
        qty_known = qty > 0
        if not qty_known:
            qty = 1  # 수량을 못 찾으면 1개로 계산하되 근거에 표시

        final_pay = price + shipping_fee
        unit_price = round(final_pay / qty, 2)

        qty_note = "" if qty_known else " ⚠수량 미확인(1개로 계산)"
        evidence = (
            f"(상품가 {price:,}원 + 배송비 {shipping_fee:,}원) "
            f"÷ 추출수량 {qty:,}개 = 개당 {unit_price:,}원{qty_note}"
        )

        candidates.append({
            "검색어": keyword,
            "추천 상품명": title,
            "개당 단가(원)": unit_price,
            "결제 금액(원)": final_pay,
            "추출 수량": qty,
            "산출 근거": evidence,
            "상품 링크": product_url,
            "_수량확인": qty_known,
        })

    # 수량을 확인한 상품을 우선 비교 대상으로 사용 (확인된 상품이 하나도 없으면 전체 사용)
    confirmed = [c for c in candidates if c["_수량확인"]]
    result = confirmed if confirmed else candidates
    for c in result:
        c.pop("_수량확인", None)
    return result
