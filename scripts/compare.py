import pandas as pd
from pathlib import Path

def generate_report(df, output_dir):
    """비교 보고서 생성"""
    
    # 단가 계산 (1000개 기준)
    df["unit_price"] = df["final_price"]  # 이미 1000개 기준이면 그대로
    df = df.sort_values("unit_price")
    
    # 마크다운 보고서
    report = f"""# 🛍️ 가격 조사 보고서

**기준**: 최종가(배송비 포함) | **단위**: {df['unit'].iloc[0]}

## 📈 최저가 순위

| 순위 | 상품명 | 플랫폼 | 가격 | 링크 |
|------|--------|--------|------|------|
"""
    
    for idx, row in df.iterrows():
        rank = idx + 1
        price = f"{row['final_price']:,.0f}원"
        report += f"| {rank} | {row['name']} | {row['platform']} | {price} | [보기]({row['url']}) |\n"
    
    # 최저가 하이라이트
    min_price = df['unit_price'].min()
    max_price = df['unit_price'].max()
    savings = max_price - min_price
    
    report += f"""

## 💰 분석

- **최저가**: {min_price:,.0f}원
- **최고가**: {max_price:,.0f}원
- **가격차**: {savings:,.0f}원 ({(savings/max_price*100):.1f}%)

---
*마지막 업데이트: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    # 저장
    report_path = output_dir / "comparison.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"✅ 보고서 저장: {report_path}")
