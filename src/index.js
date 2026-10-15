// 배민상회 자연어 검색 Worker
// /api/search?q=...  : 질문을 검색어로 바꾸고, Cloudflare 클라우드 브라우저로 배민상회 검색 결과를 읽어
//                      개당 단가가 낮은 순으로 돌려줍니다.
// 필요한 설정: CF_API_TOKEN(Secret), CF_ACCOUNT_ID(wrangler.jsonc vars), ACCESS_KEY(선택, Secret)

const NUM = "\\d{1,3}(?:,\\d{3})+|\\d+";
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
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

// ---------------------------------------------------------------
// 1. 자연어 → 검색어/조건
// ---------------------------------------------------------------
function parseQuery(q) {
  const text = q
    .replace(/(\d+)\s*oz/gi, "$1온스")
    .replace(/(\d{2,3})\s*(?:mm|Φ|φ|ø)/gi, "$1파이");

  const cap = (text.match(/(\d+)\s*(?:온스|온즈)/) || [])[1] || null;
  const dia = (text.match(/(\d+)\s*파이/) || [])[1] || null;
  const wantsLid = /뚜껑|리드/.test(text);

  let keyword = text
    .replace(/(\d[\d,]*)\s*(?:개입|개|ea|입|매)/gi, " ") // 수량은 개당 단가로 환산하므로 검색어에서 제외
    .replace(/(제일|가장|젤|아주)?\s*(싼|싸게|싸|저렴한|저렴하게|최저가|최저|저가)\s*(것|거|걸|순으로|순)?/g, " ")
    .replace(/(찾아|검색해|검색|알려|보여|비교해)\s*(줘|줘요|주세요|줄래|봐)?/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!keyword) keyword = text.trim();

  return { keyword, cap, dia, wantsLid };
}

// ---------------------------------------------------------------
// 2. Cloudflare 클라우드 브라우저로 페이지 렌더링
// ---------------------------------------------------------------
async function renderPage(env, targetUrl) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 70000);
  try {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/browser-rendering/content`,
      {
        method: "POST",
        signal: ctrl.signal,
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          url: targetUrl,
          gotoOptions: { waitUntil: "networkidle0", timeout: 45000 },
          setExtraHTTPHeaders: { "Accept-Language": "ko-KR,ko;q=0.9" },
        }),
      }
    );
    const data = await res.json().catch(() => null);
    if (res.status === 429) {
      throw new HttpError(429, "클라우드 브라우저 사용 한도에 도달했어요. 잠시 뒤(또는 내일) 다시 시도하세요.");
    }
    if (!res.ok || !data || !data.success) {
      const detail = JSON.stringify((data && data.errors) || res.status).slice(0, 200);
      throw new HttpError(502, `Cloudflare 오류: ${detail}`);
    }
    return data.result;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------
// 3. 검색 결과 HTML → 상품 카드(텍스트)
//    상품 링크(/goods/detail/번호)를 기준으로 다음 상품 링크 전까지를 한 카드로 본다.
// ---------------------------------------------------------------
function htmlToText(html) {
  let s = html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ");
  s = s.replace(/<a\b[^>]*?href=["'][^"']*\/goods\/detail\/(\d+)[^"']*["'][^>]*>/gi, "\n@@$1@@\n");
  s = s.replace(/<[^>]+>/g, "\n");
  s = s
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
  return s;
}

function extractCards(html) {
  const text = htmlToText(html);
  const parts = text.split(/@@(\d+)@@/);
  const map = new Map();
  for (let i = 1; i < parts.length; i += 2) {
    const id = parts[i];
    const seg = parts[i + 1] || "";
    map.set(id, ((map.get(id) || "") + "\n" + seg).slice(0, 700));
  }
  const cards = [];
  for (const [id, seg] of map) {
    const lines = seg.split("\n").map((l) => l.replace(/[ \t]+/g, " ").trim()).filter(Boolean).slice(0, 14);
    if (lines.length) cards.push({ id, lines });
  }
  return { cards, text };
}

// ---------------------------------------------------------------
// 4. 카드 하나에서 가격/수량 읽기
// ---------------------------------------------------------------
function extractQty(text) {
  const c = [];
  let m;
  const mul = new RegExp(`(${NUM})\\s*(?:개입|개|입|매)\\s*[xX×*]?\\s*(${NUM})\\s*(?:줄|박스|팩|봉|세트|묶음)`, "gi");
  while ((m = mul.exec(text))) c.push(toInt(m[1]) * toInt(m[2]));
  const one = new RegExp(`(${NUM})\\s*(?:개입|개|입|매|ea|pcs)`, "gi");
  while ((m = one.exec(text))) c.push(toInt(m[1]));
  const valid = c.filter((n) => n > 0);
  return valid.length ? Math.max(...valid) : 0;
}

function pickName(lines) {
  // 가격·할인율·배송·리뷰 같은 줄은 상품명이 아님
  const skip = /^(?:[\d,.\s]+원?$|\d+%$|리뷰|쿠폰|무료|배송|개당|품절|오늘출발$)/;
  const cands = lines.slice(0, 12).filter((l) => l.length >= 6 && !skip.test(l));
  // 규격(온스/파이)이 들어 있는 줄 중 가장 긴 줄을 우선 (브랜드명은 짧아서 제외됨)
  const spec = cands.filter((l) => /온스|oz|파이/i.test(l)).sort((a, b) => b.length - a.length)[0];
  return spec || cands[0] || lines[0];
}

function parseCard(card) {
  const full = card.lines.join(" ");
  const name = pickName(card.lines);

  // 판매가: '쿠폰가/개당/배송' 앞까지의 금액 중 마지막 값 (정가 → 할인율 → 판매가 순서)
  const cut = full.search(/쿠폰가|개당|배송/);
  const head = cut > 0 ? full.slice(0, cut) : full;
  const prices = [...head.matchAll(new RegExp(`(${NUM})\\s*원`, "g"))].map((m) => toInt(m[1]));
  if (!prices.length) return null;
  const sale = prices[prices.length - 1];

  const cm = full.match(new RegExp(`쿠폰가\\s*(${NUM})\\s*원`));
  const coupon = cm ? toInt(cm[1]) : null;

  // 사이트가 보여주는 개당 단가 (쿠폰가 뒤에 나오는 것은 쿠폰 기준이라 제외)
  const couponAt = cm ? full.indexOf(cm[0]) : -1;
  let refUnit = null;
  for (const m of full.matchAll(new RegExp(`개당\\s*(${NUM})\\s*원`, "g"))) {
    if (couponAt < 0 || m.index < couponAt) {
      refUnit = toInt(m[1]);
      break;
    }
  }

  let ship = null;
  if (/무료\s*배송/.test(full)) ship = 0;
  else {
    const sm = full.match(new RegExp(`배송비\\s*(${NUM})\\s*원`));
    if (sm) ship = toInt(sm[1]);
  }

  const qtyMatch = full.match(new RegExp(`제공\\s*수량\\s*(${NUM})`));
  const qty = qtyMatch ? toInt(qtyMatch[1]) : extractQty(name);

  const flags = [];
  let unit = null;
  if (qty > 0) {
    unit = (sale + (ship || 0)) / qty;
    if (ship === null) flags.push("배송비 미확인(0원 처리)");
  } else if (refUnit) {
    unit = refUnit;
    flags.push("수량 미확인 · 사이트 표시 단가 사용");
  }
  if (/품절/.test(full)) flags.push("품절 표시");

  return {
    id: card.id,
    name,
    url: `https://mart.baemin.com/goods/detail/${card.id}`,
    salePrice: sale,
    couponPrice: coupon,
    shipping: ship,
    qty: qty || null,
    unit: unit === null ? null : Math.round(unit * 100) / 100,
    per1000: unit === null ? null : Math.round(unit * 1000),
    flags,
    _text: full,
  };
}

function matchesQuery(item, p) {
  const t = item._text;
  if (p.cap && !new RegExp(`${p.cap}\\s*(?:온스|온즈|oz)`, "i").test(t)) return false;
  if (p.dia && !new RegExp(`${p.dia}\\s*(?:파이|mm|Φ|φ|ø)`, "i").test(t)) return false;
  if (!p.wantsLid && /뚜껑|리드/.test(item.name)) return false;
  return true;
}

// ---------------------------------------------------------------
// 5. 요청 처리
// ---------------------------------------------------------------
async function handleSearch(request, env) {
  const url = new URL(request.url);

  if (env.ACCESS_KEY) {
    const key = url.searchParams.get("key") || request.headers.get("x-access-key") || "";
    if (key !== env.ACCESS_KEY) return json({ error: "접근 키가 필요하거나 올바르지 않습니다." }, 401);
  }

  const q = (url.searchParams.get("q") || "").trim().slice(0, 100);
  if (!q) return json({ error: "검색어를 입력하세요." }, 400);
  if (!env.CF_API_TOKEN || !env.CF_ACCOUNT_ID) {
    return json({ error: "서버 설정(CF_API_TOKEN / CF_ACCOUNT_ID)이 없습니다." }, 500);
  }

  const p = parseQuery(q);
  const searchUrl = `https://mart.baemin.com/search/result?p=0&s=BASIC_A&w=${encodeURIComponent(p.keyword)}`;

  const html = await renderPage(env, searchUrl);
  const { cards, text } = extractCards(html);

  const parsed = cards.map(parseCard).filter(Boolean);
  let matched = parsed.filter((it) => matchesQuery(it, p));
  let relaxed = false;
  if (!matched.length && parsed.length) {
    matched = parsed; // 조건에 맞는 게 없으면 조건 없이 보여주고 표시
    relaxed = true;
  }

  const priced = matched.filter((it) => it.unit !== null).sort((a, b) => a.unit - b.unit);
  const unpriced = matched.filter((it) => it.unit === null).length;
  const strip = ({ _text, ...rest }) => rest;

  const body = {
    query: q,
    keyword: p.keyword,
    searchUrl,
    cardCount: cards.length,
    relaxed,
    unpriced,
    results: priced.slice(0, 30).map(strip),
  };

  if (url.searchParams.get("debug") === "1") {
    body.debug = {
      htmlLength: html.length,
      textHead: text.replace(/\n+/g, " | ").slice(0, 1500),
      cards: cards.slice(0, 5).map((c) => ({ id: c.id, text: c.lines.join(" | ").slice(0, 400) })),
    };
  }
  return json(body);
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
