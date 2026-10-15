import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

COLUMNS = ["검색어", "추천 상품명", "개당 단가(원)", "결제 금액(원)", "추출 수량", "산출 근거", "상품 링크", "수집시각"]
NUM = r"\d{1,3}(?:,\d{3})+|\d+"  # 58,820 / 1000 모두 한 덩어리 숫자로 인식


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def to_int(s: str) -> int:
    return int(s.replace(",", ""))


# ---------------------------------------------------------------
# 1. Cloudflare Browser Rendering (클라우드 브라우저) 호출
# ---------------------------------------------------------------
def cf_post(endpoint: str, payload: dict, binary: bool = False):
    """Cloudflare Browser Rendering REST API 호출.
    필요한 환경변수(GitHub Secrets): CF_ACCOUNT_ID, CF_API_TOKEN
    """
    account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not account or not token:
        raise RuntimeError("CF_ACCOUNT_ID / CF_API_TOKEN 이 설정되지 않았습니다 (GitHub Secrets 확인)")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/browser-rendering/{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )

    raw = b""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                raw = res.read()
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            if e.code == 429 and attempt == 0:
                print("  ⏳ 요청 한도(429) — 20초 후 한 번 더 시도합니다")
                time.sleep(20)
                continue
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}")

    if binary:
        return raw
    data = json.loads(raw.decode("utf-8"))
    if not data.get("success", False):
        raise RuntimeError(f"Cloudflare 오류 응답: {str(data.get('errors'))[:300]}")
    return data["result"]


def fetch_rendered_html(url: str) -> str:
    """클라우드 브라우저로 페이지를 열고, 자바스크립트 실행이 끝난 HTML을 받아온다."""
    return cf_post("content", {
        "url": url,
        "gotoOptions": {"waitUntil": "networkidle0", "timeout": 45000},
        "setExtraHTTPHeaders": {"Accept-Language": "ko-KR,ko;q=0.9"},
    })


def html_to_text(html: str):
    """렌더링된 HTML → (상품명, 화면 텍스트)"""
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    tag = soup.find("meta", attrs={"property": "og:title"})
    if tag and tag.get("content"):
        title = tag["content"].strip()
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return title, text


# ---------------------------------------------------------------
# 2. 화면 텍스트에서 가격 정보 읽기
# ---------------------------------------------------------------
def find_title_pos(text: str, title: str) -> int:
    for t in (title, re.sub(r"^\[[^\]]*\]\s*", "", title or "")):
        if t:
            i = text.find(t)
            if i >= 0:
                return i
    return -1


def parse_baemin_text(text: str, title: str):
    """배민상회 상품 페이지의 화면 텍스트에서 가격 정보를 뽑는다. 못 찾으면 None."""
    start = find_title_pos(text, title)
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


# ---------------------------------------------------------------
# 3. 실패 시 원인 확인용 파일 저장
# ---------------------------------------------------------------
def save_debug(idx: int, url: str, html: str, text: str):
    try:
        (OUTPUT_DIR / f"debug_baemin_{idx}.html").write_text(html, encoding="utf-8")
        preview = re.sub(r"\s+", " ", text)[:300]
        print(f"  🔎 화면 텍스트 앞부분: {preview}")
        print(f"  🔎 디버그 파일 저장: debug_baemin_{idx}.html")
    except Exception as e:
        print(f"  (HTML 디버그 저장 실패: {e})")
    try:
        png = cf_post("screenshot", {
            "url": url,
            "gotoOptions": {"waitUntil": "networkidle0", "timeout": 45000},
        }, binary=True)
        if png[:4] == b"\x89PNG":
            (OUTPUT_DIR / f"debug_baemin_{idx}.png").write_bytes(png)
            print(f"  🔎 디버그 파일 저장: debug_baemin_{idx}.png")
    except Exception as e:
        print(f"  (스크린샷 저장 실패: {e})")


def main():
    config = load_config()
    delay = config.get("delay_seconds", 12)  # 무료 플랜 REST 한도(분당 6회)를 넘지 않도록 넉넉히
    use_coupon = config.get("use_coupon_price", False)
    rows = []

    if not os.environ.get("CF_ACCOUNT_ID") or not os.environ.get("CF_API_TOKEN"):
        print("❌ CF_ACCOUNT_ID / CF_API_TOKEN 이 없습니다. GitHub 저장소 Settings → Secrets and variables → Actions 에 등록하세요.")
        sys.exit(1)

    products = [p for p in config.get("products", []) if p.get("active", True)]
    for idx, item in enumerate(products):
        url = item["url"]
        label = item.get("label", "배민상회")
        print(f"\n[배민상회 조회 중] {url}")

        html, text = "", ""
        try:
            html = fetch_rendered_html(url)
            title, text = html_to_text(html)
            if not title:
                title = item.get("name", "")
            info = parse_baemin_text(text, title)

            if info:
                row = build_row(info, item.get("name") or title, url, label, use_coupon)
                rows.append(row)
                print(f"  ✅ {row['추천 상품명']}")
                print(f"  📌 산출 근거: {row['산출 근거']}")
            else:
                print("  ❌ 가격 정보를 읽지 못했습니다 (차단/로그인 화면이거나 페이지 구조가 바뀐 경우일 수 있음)")
                save_debug(idx, url, html, text)

        except Exception as e:
            print(f"  ⚠️ 조회 에러 발생: {str(e)}")

        if idx < len(products) - 1:
            time.sleep(delay)

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
