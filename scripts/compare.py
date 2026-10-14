import pandas as pd
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
UNIT_BASE = 1000  # 1,000개 기준 환산


def generate_report(df, output_dir):
    """results.csv 기준 비교 보고서(comparison.md) 생성"""
    if df.empty:
        print("⚠️ 비교할 결과가 없어 보고서를 만들지 않았습니다.")
        return

    df = df.sort_values("개당 단가(원)").reset_index(drop=True)
    df["환산가"] = df["개당 단가(원)"] * UNIT_BASE

    report = f"""# 🛍️ 가격 조사 보고서

**기준**: 최종가(배송비 포함) | **환산 단위**: {UNIT_BASE:,}개

## 📈 최저가 순위

| 순위 | 상품명 | 결제금액 | 수량 | 개당 단가 | {UNIT_BASE:,}개 환산 | 링크 |
|------|--------|----------|------|-----------|------------|------|
"""

    for i, row in df.iterrows():
        name = str(row["추천 상품명"]).replace("|", "/")
        report += (
            f"| {i + 1} | {name} | {row['결제 금액(원)']:,.0f}원 | "
            f"{row['추출 수량']:,.0f}개 | {row['개당 단가(원)']:,.2f}원 | "
            f"{row['환산가']:,.0f}원 | [보기]({row['상품 링크']}) |\n"
        )

    min_price = df["환산가"].min()
    max_price = df["환산가"].max()
    diff = max_price - min_price
    pct = (diff / max_price * 100) if max_price else 0

    report += f"""

## 💰 분석 ({UNIT_BASE:,}개 환산 기준)

- **최저가**: {min_price:,.0f}원
- **최고가**: {max_price:,.0f}원
- **가격차**: {diff:,.0f}원 ({pct:.1f}%)

---
*마지막 업데이트: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

    report_path = Path(output_dir) / "comparison.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"✅ 보고서 저장: {report_path}")


def main():
    csv_path = OUTPUT_DIR / "results.csv"
    if not csv_path.exists():
        print(f"⚠️ {csv_path} 파일이 없습니다. 먼저 scraper.py를 실행하세요.")
        return
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    generate_report(df, OUTPUT_DIR)


if __name__ == "__main__":
    main()
