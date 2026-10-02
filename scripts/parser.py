import json
import re
from bs4 import BeautifulSoup

def parse_baemin_price(html, config_item):
    """배민상회 가격 추출"""
    soup = BeautifulSoup(html, "html.parser")
    
    # JSON-LD 찾기
    json_ld = soup.find("script", {"type": "application/ld+json"})
    
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            if "offers" in data:
                offers = data["offers"]
                if isinstance(offers, list):
                    offers = offers[0]
                
                return {
                    "id": config_item["id"],
                    "name": config_item["name"],
                    "platform": "배민상회",
                    "final_price": float(offers.get("price", 0)),
                    "currency": offers.get("priceCurrency", "KRW"),
                    "unit": config_item["unit"],
                    "url": config_item["url"]
                }
        except Exception as e:
            print(f"JSON-LD 파싱 실패: {str(e)}")
    
    # 폴백: 텍스트에서 가격 찾기
    text = soup.get_text()
    prices = re.findall(r"([\d,]+)\s*원", text)
    
    if prices:
        return {
            "id": config_item["id"],
            "name": config_item["name"],
            "platform": "배민상회",
            "final_price": int(prices[0].replace(",", "")),
            "currency": "KRW",
            "unit": config_item["unit"],
            "url": config_item["url"],
            "note": "폴백 파싱"
        }
    
    return None

def parse_coupang_price(html, config_item):
    """쿠팡 가격 추출 (추후 구현)"""
    # 비슷한 로직
    pass
