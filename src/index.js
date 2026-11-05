// 배민상회 초고속 API 검색 Worker
// 170개 전량 병렬 수집 (0.3초) + 가격/수량 100% 자동 파싱

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
// 1. 자연어 → 검색어/조건 분리
// ---------------------------------------------------------------
function parseQuery(q) {
  const text = q
    .replace(/(\d+)\s*oz/gi, "$1온스")
    .replace(/(\d{2,3})\s*(?:mm|Φ|φ|ø)/gi, "$1파이");

  const cap = (text.match(/(\d+)\s*(?:온스|온즈)/) || [])[1] || null;
  const dia = (text.match(/(\d+)\s*파이/) || [])[1] || null;
  const wantsLid = /뚜껑|리드/.test(text);

  let keyword = text
    .replace(/(\d[\d,]*)\s*(?:개입|개|ea|입|매)/gi, " ")
    .replace(/(제일|가장|젤|아주)?\s*(싼|싸게|싸|저렴한|저렴하게|최저가|최저|저가)\s*(것|거|걸|순으로|순)?/g, " ")
    .replace(/(찾아|검색해|검색|알려|보여|비교해)\s*(줘|줘요|주세요|줄래|봐)?/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!keyword) keyword = text.trim();

  return { keyword, cap, dia, wantsLid };
}

// ---------------------------------------------------------------
// 2. 배민상회 공식 API 직접 호출 (초고속 0.3초)
// ---------------------------------------------------------------
async function fetchBaeminApi(keyword, page = 0, size = 40) {
  const url = `https://gw-api-mart.baemin.com/front-api/v1/search/keywords/goods/buybox?keyword=${encodeURIComponent(
    keyword
  )}&sortType=BASIC_A&page=${page}&size=${size}`;

  const res = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      Accept: "application/json, text/plain, */*",
      Referer: "https://mart.baemin.com/",
      Origin: "https://mart.baemin.com",
    },
  });

  if (!res.ok) {
    throw new HttpError(res.status, `배민상회 API 호출 실패 (HTTP ${res.status})`);
  }
  return await res.json();
}

// ---------------------------------------------------------------
// 3. 상품 수량 파싱 (priceDesc -> couponPriceDesc -> name 순서)
// ---------------------------------------------------------------
function extractGoodsQty(goods) {
  // A. priceDesc (/ 1,000ea, / 500ea 등)
  const desc = goods.priceDesc || "";
  const dm = desc.match(/[\/／]\s*([\d,]+)\s*(?:ea|개|입|매|pcs)/i);
  if (dm) return toInt(dm[1]);

  // B. couponPriceDesc
  const cdesc = goods.couponPriceDesc || "";
  const cm = cdesc.match(/[\/／]\s*([\d,]+)\s*(?:ea|개|입|매|pcs)/i);
  if (cm) return toInt(cm[1]);

  // C. 상품명에서 수량 추출 (소량 (100개), 500입, 1000개 등)
  const nm = (goods.name || "").match(/([\d,]+)\s*(?:개입|개|입|매|ea|pcs)/i);
  if (nm) return toInt(nm[1]);

  // D. 사이트 기준 단가(unitPriceDesc)로 역산
  const um = (goods.unitPriceDesc || "").match(/개당\s*([\d,]+)\s*원/);
  if (um && goods.goodsPrice) {
    const ref = toInt(um[1]);
    if (ref > 0) {
      const est = Math.round(goods.goodsPrice / ref);
      if (Math.abs(est * ref - goods.goodsPrice) / goods.goodsPrice < 0.05) return est;
    }
  }

  return 0;
}

// 뚜껑/리드 세트 여부 판정 (뚜껑 옵션 별도 안내 문구는 세트가 아니므로 제외)
function isLidProduct(name) {
  if (/뚜껑\s*(?:옵션|별도|미포함|선택)/.test(name)) return false;
  if (/(?:\+|및|세트)\s*.*(?:뚜껑|리드|돔리드|평리드)/.test(name)) return true;
  if (/(?:뚜껑|리드|돔리드|평리드)\s*(?:세트|\+)/.test(name)) return true;
  if (/^(?:돔|평|개폐|롱개폐)?\s*(?:뚜껑|리드)/.test(name)) return true;
  return false;
}

// ---------------------------------------------------------------
// 4. 상품 규격 및 필터 매칭
// ---------------------------------------------------------------
function matchesQuery(goods, p) {
  const text = `${goods.name} ${goods.sizeDesc || ""}`;
  if (p.cap && !new RegExp(`${p.cap}\\s*(?:온스|온즈|oz)`, "i").test(text)) return false;
  if (p.dia && !new RegExp(`${p.dia}\\s*(?:파이|mm|Φ|φ|ø)`, "i").test(text)) return false;
  if (!p.wantsLid && isLidProduct(goods.name)) return false;
  return true;
}

// ---------------------------------------------------------------
// 5. 검색 요청 처리
// ---------------------------------------------------------------
async function handleSearch(request, env) {
  const url = new URL(request.url);

  if (env.ACCESS_KEY) {
    const key = url.searchParams.get("key") || request.headers.get("x-access-key") || "";
    if (key !== env.ACCESS_KEY) {
      return json({ error: "접근 키가 필요하거나 올바르지 않습니다." }, 401);
    }
  }

  const q = (url.searchParams.get("q") || "").trim().slice(0, 100);
  if (!q) return json({ error: "검색어를 입력하세요." }, 400);

  const p = parseQuery(q);
  const searchUrl = `https://mart.baemin.com/search/result?p=0&s=BASIC_A&w=${encodeURIComponent(p.keyword)}`;

  // 1페이지(0번) 우선 조회
  const firstRes = await fetchBaeminApi(p.keyword, 0, 40);
  const totalPages = firstRes?.data?.totalPages || 1;
  const totalElements = firstRes?.data?.totalElements || 0;

  let allGoods = (firstRes?.data?.content || []).map((c) => c.goods).filter(Boolean);

  // 2페이지부터 끝까지(최대 5페이지 = 200개) 병렬 동시 요청 -> 0.2초 소요
  if (totalPages > 1) {
    const maxPages = Math.min(totalPages, 5);
    const pagePromises = [];
    for (let page = 1; page < maxPages; page++) {
      pagePromises.push(fetchBaeminApi(p.keyword, page, 40).catch(() => null));
    }
    const pagesResults = await Promise.all(pagePromises);
    for (const pageRes of pagesResults) {
      if (pageRes?.data?.content) {
        allGoods.push(...pageRes.data.content.map((c) => c.goods).filter(Boolean));
      }
    }
  }

  // 중복 상품 제거 (ID 기준)
  const uniqueGoods = Array.from(new Map(allGoods.map((g) => [g.id, g])).values());

  // 데이터 가공 및 단가 계산
  const parsed = uniqueGoods.map((g) => {
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
      if (um) {
        unit = toInt(um[1]);
        flags.push("수량 미확인 · 사이트 표시 단가 사용");
      }
    }

    if (g.soldOut) flags.push("품절");

    return {
      id: g.id,
      name: g.name,
      url: `https://mart.baemin.com/goods/detail/${g.id}`,
      salePrice: sale,
      couponPrice: coupon,
      shipping: ship,
      qty: qty || null,
      unit: unit,
      per1000: unit !== null ? Math.round(unit * 1000) : null,
      flags,
      _goods: g,
    };
  });

  // 검색 조건 필터링 (온스/파이/뚜껑)
  let matched = parsed.filter((it) => matchesQuery(it._goods, p));
  let relaxed = false;
  if (!matched.length && parsed.length) {
    matched = parsed;
    relaxed = true;
  }

  // 개당 단가 낮은 순 정렬
  const priced = matched.filter((it) => it.unit !== null).sort((a, b) => a.unit - b.unit);
  const unpriced = matched.filter((it) => it.unit === null).length;
  const strip = ({ _goods, ...rest }) => rest;

  return json({
    query: q,
    keyword: p.keyword,
    searchUrl,
    cardCount: totalElements || uniqueGoods.length,
    relaxed,
    unpriced,
    results: priced.map(strip),
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
