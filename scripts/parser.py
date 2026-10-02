import json
import re
from bs4 import BeautifulSoup

def parse_baemin_price(html, config_item):
    """배민상회 가격 추출 (API 응답 JSON 기반)"""
    try:
        # HTML이 아닌 JSON 응답일 경우
        if isinstance(html, str) and html.strip().startswith('{'):
            data = json.loads(html)
        else:
            # HTML에서 JSON 추출 시도
            soup = BeautifulSoup(html, "html.parser")
            data = json.loads(html)
        
        # API 응답 파싱
        if "data" in data and "content" in data["data"]:
            product = data["data"]["content"][0]
            
            goods_price = product.get("goodsPrice", 0)
            delivery_amount = product.get("deliveryAmount", 0)
            coupon_price = product.get("couponPrice", None)
            
            # 최종가 = 판매가 + 배송료
            final_price = goods_price + delivery_amount
            
            return {
                "id": config_item["id"],
                "name": config_item["name"],
                "platform": "배민상회",
                "goodsPrice": goods_price,
                "deliveryAmount": delivery_amount,
                "final_price": final_price,
                "couponPrice": coupon_price,
                "currency": "KRW",
                "unit": config_item["unit"],
                "url": config_item["url"],
                "priceDesc": product.get("priceDesc", ""),
                "couponPriceDesc": product.get("couponPriceDesc", "")
            }
    except Exception as e:
        print(f"배민상회 파싱 실패: {str(e)}")
    
    return None

def parse_coupang_price(html, config_item):
    """쿠팡 가격 추출 (추후 구현)"""
    pass
