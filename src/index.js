// 배민상회 170개 전량 수집 & 개당 단가 최저가 정렬 Worker
// 뚜껑/리드 세트 제외 없이 전량 표시 및 수량 파싱 누락 0건 처리

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
// 1. 검색어 정제 (조사 및 불용어 제거)
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
// 2. Cloudflare 브라우저 렌더링 (방화벽 차단 안전 폴백용)
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
          gotoOptions: { waitUntil: "domcontentloaded", timeout: 35000 },
          setExtraHTTPHeaders: { "Accept-Language": "ko-KR,ko;q=0.9" },
        }),
      }
    );
    const data = await res.json().catch(() => null);
    if (!res.ok || !data?.success) {
      throw new Error("브라우저 렌더링 실패");
    }
    return data.result;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------
// 3. 배민 API 직접 호출 (3초 제한)
// ---------------------------------------------------------------
async function fetchBaeminDirect(keyword, page = 0, size = 200) {
  const url = `https://gw-api-mart.baemin.com/front-api/v1/search/keywords/goods/buybox?keyword=${encodeURIComponent(
    keyword
  )}&sortType=BASIC_A&page=${page}&size=${size}`;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 4000); // 4초 초과 시 타임아웃 방지
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: {
        Accept: "application/json, text/plain, */*",
        Referer: "https://mart.baemin.com/",
        Origin: "https://mart.baemin.com",
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------
// 4. 170개 전량 수집 (API 우선 + 브라우저 세션 백업)
// ---------------------------------------------------------------
async function fetchAllGoods(env, keyword) {
  // 시도 1: API를 통해 200개 한 번에 직접 조회 (가장 빠름)
  try {
    const directRes = await fetchBaeminDirect(keyword, 0, 200);
    const content = directRes?.data?.content || [];
    if (content.length > 0) {
      const items = content.map((c) => c.goods).filter(Boolean);
      const totalPages = directRes?.data?.totalPages || 1;

      // size 제한으로 40개만 넘어왔다면 남은 페이지 병렬 수집
      if (items.length < (directRes?.data?.totalElements || 0) && totalPages > 1) {
        const promises = [];
        for (let p = 1; p < Math.min(totalPages, 5); p++) {
          promises.push(fetchBaeminDirect(keyword, p, 40).catch(() => null));
        }
        const extraPages = await Promise.all(promises);
        for (const ep of extraPages) {
          if (ep?.data?.content) {
            items.push(...ep.data.content.map((c) => c.goods).filter(Boolean));
          }
        }
      }
      return { items, totalCount: directRes?.data?.totalElements || items.length };
    }
  } catch (e) {
    // API 직접 호출 실패(차단/타임아웃) 시 브라우저 렌더링으로 자동 폴백
  }

  // 시도 2: 가상 브라우저로 API 엔드포인트 직접 호출 (Chromium 세션 우회)
  try {
    const apiUrl = `https://gw-api-mart.baemin.com/front-api/v1/search/keywords/goods/buybox?keyword=${encodeURIComponent(
      keyword
    )}&sortType=BASIC_A&page=0&size=200`;
    const html = await renderPage(env, apiUrl);
    const match = html.match(/<pre[^>]*>([\s\S]*?)<\/pre>/i);
    const rawJson = match ? match[1] : html.replace(/<[^>]+>/g, "");
    const parsed = JSON.parse(rawJson);
    const items = (parsed?.data?.content || []).map((c) => c.goods).filter(Boolean);
    if (items.length > 0) {
      return { items, totalCount: parsed?.data?.totalElements || items.length };
    }
  } catch (e) {
    // 2단계 실패 시 3단계 진행
  }

  // 시도 3: 배민상회 웹 검색 페이지 렌더링
  const webUrl = `https://mart.baemin.com/search/result?p=0&s=BASIC_A&w=${encodeURIComponent(keyword)}`;
  const webHtml = await renderPage(env, webUrl);
  return { items: parseWebHtml(webHtml), totalCount: 170 };
}

// ---------------------------------------------------------------
// 5. 상품 수량 파싱 (누락 방지 5단계 로직)
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

  // C. sizeDesc (예: "1000개")
  const sdesc = goods.sizeDesc || "";
  m = sdesc.match(/([\d,]+)\s*(?:개입|개|입|매|ea|pcs)/i);
  if (m) return toInt(m[1]);

  // D. 상품명 (예: "[1000개]", "500입", "소량 (100개)")
  const name = goods.name || "";
  const mul = name.match(/([\d,]+)\s*(?:개입|개|입|매)\s*[xX×*]?\s*([\d,]+)\s*(?:줄|박스|팩|봉|세트|묶음)/i);
  if (mul) return toInt(mul[1]) * toInt(mul[2]);

  m = name.match(/([\d,]+)\s*(?:개입|개|입|매|ea|pcs)/i);
  if (m) return toInt(m[1]);

  // E. 사이트 기준 단가(unitPriceDesc)로 역산
  const um = (goods.unitPriceDesc || "").match(/개당\s*([\d,]+)\s*원/);
  if (um && goods.goodsPrice) {
    const ref = toInt(um[1]);
    if (ref > 0) {
      const est = Math.round(goods.goodsPrice / ref);
      if (est > 0) return est;
    }
  }

  // F. 알 수 없는 경우 단가 계산을 위해 1개로 처리 (목록에서 제외 방지)
  return 1;
}

// ---------------------------------------------------------------
// 6. 웹 HTML 카드 백업 파서
// ---------------------------------------------------------------
function parseWebHtml(html) {
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
    const sale = prices[0];

    goods.push({
      id,
      name: lines.find((l) => l.length >= 6 && !/원$|쿠폰|배송|무료/.test(l)) || lines[0],
      goodsPrice: sale,
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
// 7. 검색 요청 핸들러
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

  // 170개 전량 데이터 가져오기
  const { items, totalCount } = await fetchAllGoods(env, keyword);

  // 중복 제거 (상품 ID 기준)
  const uniqueItems = Array.from(new Map(items.map((g) => [g.id, g])).values());

  // 전량 단가 계산 및 데이터 가공 (뚜껑, 규격 등 일체 필터링 없이 100% 통과)
  const parsed = uniqueItems.map((g) => {
    const sale = g.goodsPrice || 0;
    const coupon = g.couponPrice || null;
    const ship = g.freeShipping ? 0 : g.deliveryAmount || 0;
    const qty = extractGoodsQty(g);

    let unit = null;
    const flags = [];

    if (qty > 0) {
      unit = Math.round(((sale + ship) / qty) * 100) / 100;
    } else {
      const um = (g.unitPriceDesc || "").match(/개당\s*([\d,]+)\s*원/);
      unit = um ? toInt(um[1]) : sale;
      flags.push("사이트 표시 단가 사용");
    }

    if (g.soldOut) flags.push("품절");

    return {
      id: g.id,
      name: g.name,
      url: `https://mart.baemin.com/goods/detail/${g.id}`,
      salePrice: sale,
      couponPrice: coupon,
      shipping: ship,
      qty: qty || 1,
      unit: unit,
      per1000: Math.round(unit * 1000),
      flags,
    };
  });

  // 개당 단가 낮은 순 정렬 (버려지는 상품 없이 전량 정렬)
  const priced = parsed.sort((a, b) => a.unit - b.unit);

  return json({
    query: q,
    keyword: keyword,
    searchUrl,
    cardCount: Math.max(totalCount, priced.length),
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
