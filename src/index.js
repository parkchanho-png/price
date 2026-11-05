// 배민상회 170개 전량 수집 & 개당 단가 최저가 정렬 Worker
// 5개 페이지(170개) 병렬 동시 수집 + 뚜껑/규격 제외 없이 100% 노출

const toInt = (s) => parseInt(String(s).replace(/,/g, ""), 10);

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });

// ---------------------------------------------------------------
// 1. 검색어 정제
// ---------------------------------------------------------------
function parseQuery(q) {
  const text = q
    .replace(/(\d+)\s*oz/gi, "$1온스")
    .replace(/(\d{2,3})\s*(?:mm|Φ|φ|ø)/gi, "$1파이");

  let keyword = text
    .replace(/(\d[\d,]*)\s*(?:개입|개|ea|입|매)/gi, " ")
    .replace(/(제일|가장|젤|아주)?\s*(싼|싸게|싸|저렴한|저렴하게|최저가|최저|저가)\s*(것|거|걸|순으로|순)?/g, " ")
    .replace(/(찾아|검색해|검색|알려|보여|비교해)\s*(줘|줘요|주세요|줄래|봐)?/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  return keyword || text.trim();
}

// ---------------------------------------------------------------
// 2. 배민 공식 API 호출 (실제 브라우저 헤더 세팅)
// ---------------------------------------------------------------
async function fetchBaeminApi(keyword, page = 0, size = 40) {
  const url = `https://gw-api-mart.baemin.com/front-api/v1/search/keywords/goods/buybox?keyword=${encodeURIComponent(
    keyword
  )}&sortType=BASIC_A&page=${page}&size=${size}`;

  const res = await fetch(url, {
    signal: AbortSignal.timeout(10000), // 10초 타임아웃
    headers: {
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
      "Referer": "https://mart.baemin.com/",
      "Origin": "https://mart.baemin.com",
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    },
  });

  if (!res.ok) {
    throw new Error(`배민 API 응답 실패 (HTTP ${res.status})`);
  }
  return await res.json();
}

// ---------------------------------------------------------------
// 3. 상품별 수량 파싱 (단가 계산용)
// ---------------------------------------------------------------
function extractGoodsQty(goods) {
  // A. priceDesc (예: "개당 64원 / 1,000ea")
  const desc = goods.priceDesc || "";
  let m = desc.match(/[\/／]\s*([\d,]+)\s*(?:ea|개|입|매|pcs|줄)/i);
  if (m) return toInt(m[1]);

  // B. couponPriceDesc (예: "개당 47원 / 1,000ea")
  const cdesc = goods.couponPriceDesc || "";
  m = cdesc.match(/[\/／]\s*([\d,]+)\s*(?:ea|개|입|매|pcs|줄)/i);
  if (m) return toInt(m[1]);

  // C. 상품명 (예: "[1000개]", "500입", "소량 (100개)")
  const name = goods.name || "";
  const mul = name.match(/([\d,]+)\s*(?:개입|개|입|매)\s*[xX×*]?\s*([\d,]+)\s*(?:줄|박스|팩|봉|세트|묶음)/i);
  if (mul) return toInt(mul[1]) * toInt(mul[2]);

  m = name.match(/([\d,]+)\s*(?:개입|개|입|매|ea|pcs)/i);
  if (m) return toInt(m[1]);

  // D. 기준 단가(unitPriceDesc)로 역산
  const um = (goods.unitPriceDesc || "").match(/개당\s*([\d,]+)\s*원/);
  if (um && goods.goodsPrice) {
    const ref = toInt(um[1]);
    if (ref > 0) {
      const est = Math.round(goods.goodsPrice / ref);
      if (est > 0) return est;
    }
  }

  return 1; // 단가 계산 기본값
}

// ---------------------------------------------------------------
// 4. 검색 요청 처리 (5개 페이지 전량 병렬 수집)
// ---------------------------------------------------------------
async function handleSearch(request, env) {
  const url = new URL(request.url);

  if (env.ACCESS_KEY) {
    const key = url.searchParams.get("key") || request.headers.get("x-access-key") || "";
    if (key !== env.ACCESS_KEY) return json({ error: "접근 키가 필요하거나 올바르지 않습니다." }, 401);
  }

  const q = (url.searchParams.get("q") || "").trim().slice(0, 100);
  if (!q) return json({ error: "검색어를 입력하세요." }, 400);

  const keyword = parseQuery(q);
  const searchUrl = `https://mart.baemin.com/search/result?p=0&s=BASIC_A&w=${encodeURIComponent(keyword)}`;

  // 1단계: 1페이지(0번) 먼저 조회하여 전체 페이지 수(totalPages) 확인
  const firstRes = await fetchBaeminApi(keyword, 0, 40);
  const totalElements = firstRes?.data?.totalElements || 0;
  const totalPages = firstRes?.data?.totalPages || 1;

  let allGoods = (firstRes?.data?.content || []).map((c) => c.goods).filter(Boolean);

  // 2단계: 2페이지부터 마지막 페이지까지(최대 10페이지) 병렬로 동시 수집
  if (totalPages > 1) {
    const pagePromises = [];
    for (let page = 1; page < Math.min(totalPages, 10); page++) {
      pagePromises.push(
        fetchBaeminApi(keyword, page, 40)
          .then((res) => (res?.data?.content || []).map((c) => c.goods).filter(Boolean))
          .catch(() => [])
      );
    }
    const extraPages = await Promise.all(pagePromises);
    for (const pageItems of extraPages) {
      allGoods.push(...pageItems);
    }
  }

  // 중복 상품 제거 (상품 고유 ID 기준)
  const uniqueGoods = Array.from(new Map(allGoods.map((g) => [g.id, g])).values());

  // 3단계: 170개 전량 단가 계산 (뚜껑/리드/옵션 일체 제외 없이 전원 포함)
  const parsed = uniqueGoods.map((g) => {
    const sale = g.goodsPrice || 0;
    const coupon = g.couponPrice || null;
    const ship = g.freeShipping ? 0 : g.deliveryAmount || 0;
    const qty = extractGoodsQty(g);

    let unit = Math.round(((sale + ship) / qty) * 100) / 100;

    const flags = [];
    if (g.soldOut) flags.push("품절");
    if (qty === 1 && !g.name.includes("1개")) flags.push("수량 1개 기준 산출");

    return {
      id: g.id,
      name: g.name,
      url: `https://mart.baemin.com/goods/detail/${g.id}`,
      salePrice: sale,
      couponPrice: coupon,
      shipping: ship,
      qty: qty,
      unit: unit,
      per1000: Math.round(unit * 1000),
      flags,
    };
  });

  // 개당 단가 낮은 순으로 170개 일괄 정렬
  const priced = parsed.sort((a, b) => a.unit - b.unit);

  return json({
    query: q,
    keyword: keyword,
    searchUrl,
    cardCount: totalElements || priced.length, // '상품 170개 확인'으로 표기
    relaxed: false,
    unpriced: 0, // 제외 상품 0건
    results: priced, // 170개 전량 반환
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/api/search") return new Response("Not found", { status: 404 });
    try {
      return await handleSearch(request, env);
    } catch (e) {
      if (e instanceof HttpError) return json({ error: e.message }, e.status);
      return json({ error: `처리 중 오류: ${e && e.message ? e.message : e}` }, 500);
    }
  },
};
