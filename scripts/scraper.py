import json
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

COLUMNS = ["검색어", "추천 상품명", "개당 단가(원)", "결제 금액(원)", "추출 수량", "산출 근거", "상품 링크", "수집시각"]
NUM = r"\d{1,3}(?:,\d{3})+|\d+"  # 58,820 / 1000 모두 한 덩어리 숫자로 인식
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def to_int(s: str) -> int:
    return int(s.replace(",", ""))


def parse_baemin_text(text: str, title: str):
    """렌더링이 끝난 배민상회 상품 페이지의 화면 텍스트에서 가격 정보를 뽑는다.
    (태그 이름 대신 화면에 보이는 글자를 기준으로 읽어서, 사이트 디자인이 바뀌어도 덜 깨지게 함)
    못 찾으면 None 반환.
    """
    start = text.find(title) if title else -1
    body = text[start:] if start >= 0 else text

    # 판매가: 상품명 아래 ~ '쿠폰가/배송' 앞까지의 금액 중 마지막 값 (정가 → 할인율 → 판매가 순서로 표시됨)
    ends = [body.find(k) for k in ("쿠폰가", "배송기간", "배송비") if body.find(k) > 0]
    head = body[:min(ends)] if ends else body[:1500]
    prices = [to_int(m) for m in re.findall(rf"({NUM})\s*원", head)]
    if not prices:
        return None
    sale_price = prices[-1]

    # 쿠폰가 (쿠폰을 받아야 적용되는 가격)
    m = re.search(rf"쿠폰가\s*({NUM})\s*원", body)
    coupon_price = to_int(m.group(1)) if m else None

    # 배송비
    ship_fee, ship_note = 0, ""
    m = re.search(r"배송비\s*([^\n]+)", body)
    if m:
        line = m.group(1)
        if "무료" in line:
            ship_fee = 0
        else:
            n = re.search(rf"({NUM})\s*원", line)
            if n:
                ship_fee = to_int(n.group(1))
            else:
                ship_note = " ⚠배송비 미확인(0원 처리)"
    else:
        ship_note = " ⚠배송비 미확인(0원 처리)"

    # 제공 수량 (예: 1,000ea)
    m = re.search(rf"제공\s*수량\s*({NUM})", body)
    qty = to_int(m.group(1)) if m else 0
    if qty <= 0:
        m = re.search(rf"({NUM})\s*(?:개입|개|입|ea|EA)", title or "")
        qty = to_int(m.group(1)) if m else 0
    if qty <= 0:
        return None

    # 사이트가 표시하는 기준 단가 (검산용)
    m = re.search(rf"기준\s*단가\s*개당\s*({NUM})\s*원", body)
    ref_unit = to_int(m.group(1)) if m else None

    sold_out = "품절" in body[:1500]

    return {
        "sale_price": sale_price,
        "coupon_price": coupon_price,
        "ship_fee": ship_fee,
        "ship_note": ship_note,
        "qty": qty,
        "ref_unit": ref_unit,
        "sold_out": sold_out,
    }


def build_row(info: dict, name: str, url: str, label: str, use_coupon: bool) -> dict:
    use_c = bool(use_coupon and info["coupon_price"])
    price = info["coupon_price"] if use_c else info["sale_price"]
    price_label = "쿠폰가" if use_c else "판매가"
    final_pay = price + info["ship_fee"]
    qty = info["qty"]
    unit = round(final_pay / qty, 2)

    evidence = (
        f"({price_label} {price:,}원 + 배송비 {info['ship_fee']:,}원) "
        f"÷ 수량 {qty:,}개 = 개당 {unit:,}원"
    )
    if not use_c and info["coupon_price"]:
        evidence += f" | 쿠폰 적용 시 {info['coupon_price']:,}원"
    if info["ref_unit"]:
        evidence += f" | 사이트 표시 기준단가 개당 {info['ref_unit']:,}원"
    evidence += info["ship_note"]
    if info["sold_out"]:
        evidence += " ⚠품절 표시 있음"

    return {
        "검색어": label,
        "추천 상품명": name,
        "개당 단가(원)": unit,
        "결제 금액(원)": final_pay,
        "추출 수량": qty,
        "산출 근거": evidence,
        "상품 링크": url,
        "수집시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_debug(page, idx: int, text: str):
    """가격을 못 읽었을 때 원인 확인용으로 화면 캡처와 HTML 저장"""
    try:
        (OUTPUT_DIR / f"debug_baemin_{idx}.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(OUTPUT_DIR / f"debug_baemin_{idx}.png"))
        preview = re.sub(r"\s+", " ", text)[:300]
        print(f"  🔎 화면 텍스트 앞부분: {preview}")
        print(f"  🔎 디버그 파일 저장: debug_baemin_{idx}.png / .html")
    except Exception as e:
        print(f"  (디버그 저장 실패: {e})")


def main():
    from playwright.sync_api import sync_playwright

    config = load_config()
    delay = config.get("delay_seconds", 3)
    use_coupon = config.get("use_coupon_price", False)
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = context.new_page()

        for idx, item in enumerate(config.get("products", [])):
            if not item.get("active", True):
                continue

            url = item["url"]
            label = item.get("label", "배민상회")
            print(f"\n[배민상회 조회 중] {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    # 가격은 자바스크립트로 나중에 그려지므로 '제공 수량' 글자가 나타날 때까지 대기
                    page.wait_for_selector("text=제공 수량", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)

                title = ""
                try:
                    title = page.locator('meta[property="og:title"]').first.get_attribute("content", timeout=3000) or ""
                except Exception:
                    pass
                if not title:
                    title = item.get("name", "")

                text = page.inner_text("body")
                info = parse_baemin_text(text, title)

                if info:
                    row = build_row(info, item.get("name") or title, url, label, use_coupon)
                    rows.append(row)
                    print(f"  ✅ {row['추천 상품명']}")
                    print(f"  📌 산출 근거: {row['산출 근거']}")
                else:
                    print("  ❌ 가격 정보를 읽지 못했습니다 (로그인 화면/차단 화면/페이지 구조 변경일 수 있음)")
                    save_debug(page, idx, text)

            except Exception as e:
                print(f"  ⚠️ 조회 에러 발생: {str(e)}")

            time.sleep(delay)

        browser.close()

    csv_path = OUTPUT_DIR / "results.csv"
    if rows:
        df = pd.DataFrame(rows, columns=COLUMNS).sort_values("개당 단가(원)")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n📁 결과 파일 저장 완료: {csv_path} ({len(rows)}건)")
    elif not csv_path.exists():
        pd.DataFrame(columns=COLUMNS).to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n📁 수집 결과가 없어 빈 파일을 만들었습니다: {csv_path}")
    else:
        print("\n📁 수집 결과가 없어 기존 results.csv를 그대로 유지합니다.")


if __name__ == "__main__":
    main()
