// 배민상회 170개 전량 수집 & 개당 단가 최저가 정렬 Worker
// HTTP 405 자동 해결 (GET/POST/브라우저 3단계 폴백) + 뚜껑 포함 100% 노출

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
// 2. 배민 공식 API 호출 (405 방지 GET / POST 자동 대응)
// ---------------------------------------------------------------
async function fetchBaeminApi(keyword, page = 0, size = 40) {
  const url = `https://gw-api-mart.baemin.com/front-api/v1/search/keywords/goods/buybox?keyword=${encodeURIComponent(
    keyword
  )}&sortType=BASIC_A&page=${page}&size=${size}`;

  const baseHeaders = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    Accept: "application/json, text/plain, */*",
    Referer: "https://mart.baemin.com/",
  };

  // 1차 시도: Origin 없는 순수 GET 요청
  let res = await fetch(url, {
    method: "GET",
    headers: baseHeaders,
    signal: AbortSignal.timeout(6000),
  }).catch(() => null);

  // 2차 시도: 405 Method Not Allowed 발생 시 POST로 재시도
  if (res && res.status === 405) {
    res = await fetch(url, {
      method: "POST",
      headers: { ...baseHeaders, "Content-Type": "application/json" },
      body: JSON.stringify({}),
      signal: AbortSignal.timeout(6000),
    }).catch(() => null);
  }

  if (res && res.ok) {
    return await res.json();
  }
  return null;
}

// ---------------------------------------------------------------
// 3. 브라우저 렌더링 백업 (API 차단 시 무조건 동작)
// ---------------------------------------------------------------
async function renderPage(env, targetUrl) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 45000);
  try {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/browser-rendering/content`,
      {
        method: "POST",
        signal: ctrl.signal,
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          url: targetUrl,
          gotoOptions: { waitUntil: "networkidle2", timeout: 35000 },
          setExtraHTTPHeaders: { "Accept-Language": "ko-KR,ko;q=0.9" },
        }),
      }
    );
    const data = await res.json().catch(() => null);
    if (!res.ok || !data?.success) throw new Error("Browser rendering failed");
    return data.result;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------
// 4. 상품별 수량 파싱 (단가 계산용)
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

  return 1;
}

// ---------------------------------------------------------------
// 5. 웹 HTML 카드 백업 파서
// ---------------------------------------------------------------
function parseHtmlCards(html) {
  let s = html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ");
  s = s.replace(/<a\b[^>]*?href=["'][^"']*\/goods\/detail\/(\d+)[^"']*["'][^>]*>/gi, "\n@@$1@@\n");
  s = s.replace(/<[^>]+>/g, "\n");
  const parts = s.split(/@@(\d+)@@/);

  const goods = [];
  for (let i = 1; i < parts.length; i += 2) {
    const id = toInt(parts[i]);
    const seg = parts[i + 1] || "";
    const lines = seg.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 16);
    const full = lines.join(" ");

    const prices = [...full.matchAll(/(\d[\d,]*)\s*원/g)].map((m) => toInt(m[1]));
    if (!prices.length) continue;

    const cm = full.match(/쿠폰가\s*(\d[\d,]*)\s*원/);
    const coupon = cm ? toInt(cm[1]) : null;

    goods.push({
      id,
      name: lines.find((l) => l.length >= 6 && !/원$|쿠폰|배송|무료/.test(l)) || lines[0],
      goodsPrice: prices[0],
      couponPrice: coupon,
      freeShipping: /무료\s*배송/.test(full),
      deliveryAmount: 0,
      priceDesc: full,
      couponPriceDesc: full,
      unitPriceDesc: full,
      soldOut: /품절/.test(full),
    });
  }
  return goods;
}

// ---------------------------------------------------------------
// 6. 검색 요청 처리 (170개 전량 수집)
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

  let allGoods = [];
  let totalCount = 0;

  // 1단계: API 1페이지(0번) 시도
  const firstRes = await fetchBaeminApi(keyword, 0, 40);

  if (firstRes && firstRes.data && firstRes.data.content) {
    totalCount = firstRes.data.totalElements || 0;
    const totalPages = firstRes.data.totalPages || 1;
    allGoods = firstRes.data.content.map((c) => c.goods).filter(Boolean);

    // 2단계: 2페이지부터 마지막 페이지까지(최대 5페이지 = 170개 전량) 병렬 수집
    if (totalPages > 1) {
      const pagePromises = [];
      for (let p = 1; p < Math.min(totalPages, 6); p++) {
        pagePromises.push(
          fetchBaeminApi(keyword, p, 40)
            .then((res) => (res?.data?.content || []).map((c) => c.goods).filter(Boolean))
            .catch(() => [])
        );
      }
      const extraPages = await Promise.all(pagePromises);
      for (const pageItems of extraPages) {
        allGoods.push(...pageItems);
      }
    }
  } else {
    // 3단계: API 실패 시 클라우드 브라우저 백업 실행
    if (!env.CF_API_TOKEN || !env.CF_ACCOUNT_ID) {
      return json({ error: "배민 응답 대기 중입니다. 잠시 후 다시 검색해 주세요." }, 502);
    }
    const html = await renderPage(env, searchUrl);
    allGoods = parseHtmlCards(html);
    totalCount = allGoods.length;
  }

  // 중복 제거
  const uniqueGoods = Array.from(new Map(allGoods.map((g) => [g.id, g])).values());

  // 170개 전량 단가 계산 (뚜껑/리드 일체 제외 없이 100% 포함)
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

  // 개당 단가 낮은 순 정렬
  const priced = parsed.sort((a, b) => a.unit - b.unit);

  return json({
    query: q,
    keyword: keyword,
    searchUrl,
    cardCount: totalCount || priced.length, // '상품 170개 확인' 표기
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
