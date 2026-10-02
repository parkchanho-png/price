# Price Tracker (가격 조사 자동화)

배민상회, 쿠팡, 네이버쇼핑 등에서 **24온스 98파이 컵** 최저가를 자동으로 추적합니다.
최종가(배송비 포함) 기준으로 비교 보고서를 생성합니다.

## 🚀 빠른 시작

### 1. 저장소 클론
\`\`\`bash
git clone https://github.com/parkchanho-png/price.git
cd price
\`\`\`

### 2. 환경 설정
\`\`\`bash
pip install -r requirements.txt
\`\`\`

### 3. 상품 URL 추가
\`config.json\` 편집:
\`\`\`json
{
  "products": [
    {
      "name": "배민상회 24온스 98파이",
      "url": "https://mart.baemin.com/goods/detail/29605",
      "unit": "1000개",
      "platform": "baemin"
    }
  ]
}
\`\`\`

### 4. 실행
\`\`\`bash
python scripts/scraper.py
\`\`\`

결과는 \`outputs/results.csv\`, \`outputs/comparison.md\` 에 자동 저장됩니다.

## 📁 폴더 구조

\`\`\`
price/
├── README.md
├── config.json              # 조사할 상품 목록
├── requirements.txt
├── scripts/
│   ├── scraper.py          # 가격 수집
│   ├── parser.py           # HTML/JSON 파싱
│   └── compare.py          # 비교표 생성
└── outputs/
    ├── results.csv         # 가격 결과
    ├── comparison.md       # 최저가 보고서
    └── history/            # 시간별 기록
\`\`\`

## ⚙️ 주의사항
- 각 쇼핑몰의 로봇정책(robots.txt) 준수
- 과도한 요청 방지 (delay 설정 포함)

---
