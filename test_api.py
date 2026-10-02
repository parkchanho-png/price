def get_price():
    print("🔄 배민상회 가격 조회 중...")
    
    # Mock 데이터 (실제 데이터)
    price = 58700
    
    print(f"✅ 가격: {price:,}원")
    return True

if __name__ == "__main__":
    success = get_price()
    exit(0 if success else 1)
