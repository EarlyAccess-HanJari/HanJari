import type { ApiError, ApiResult, PredictResponse } from "../types";
import { N_MAX, N_MIN } from "../types";

import mockN0 from "../mock/predict_n0.json";
import mockN3 from "../mock/predict_n3.json";
import mockN15 from "../mock/predict_n15.json";
import mockN30 from "../mock/predict_n30.json";
import mockWide from "../mock/predict_wide.json";
import mockStale from "../mock/predict_stale.json";
import mockNight from "../mock/predict_empty_night.json";
import mockBadInput from "../mock/error_bad_input.json";

/** 요청 방식.
 *  - 명세(README·민준 WBS): GET /api/predict?n=3
 *  - 정원 연습 서버(161.33.141.135): POST /api/predict  body {"waiting_count": 3}
 *  정원이 API_명세.md 에 확정하면 하나로 정리. */
export const REQUEST_STYLE: "get" | "post" = "get";    // 한자리 백엔드(hanjari-backend/main.py)는 GET. 정원 연습 서버는 "post"
export const N_PARAM = "n";                 // GET 쿼리 이름
export const N_BODY_KEY = "waiting_count";  // POST body 키
export const API_URL = "/api/predict";
export const TIMEOUT_MS = 8000;

export const USE_MOCK = import.meta.env.VITE_MOCK === "1";

/** 개발·QA 용 시나리오 (URL ?scenario=...). 목업 모드에서만 동작. */
export type Scenario = "stale" | "wide" | "night" | "error" | "down" | "slow";
export function currentScenario(): Scenario | null {
  if (typeof window === "undefined") return null;
  const s = new URLSearchParams(window.location.search).get("scenario");
  return (["stale", "wide", "night", "error", "down", "slow"] as const).includes(s as Scenario)
    ? (s as Scenario)
    : null;
}

export function validateN(n: unknown): ApiError | null {
  if (typeof n !== "number" || !Number.isInteger(n)) {
    return { kind: "bad_input", message: "앞 대기 인원은 정수로 입력해 주세요." };
  }
  if (n < N_MIN || n > N_MAX) {
    return { kind: "bad_input", message: `앞 대기 인원은 ${N_MIN}~${N_MAX}명 사이로 입력해 주세요.` };
  }
  return null;
}

export async function fetchPredict(n: number): Promise<ApiResult> {
  const invalid = validateN(n);
  if (invalid) return { ok: false, error: invalid };
  return USE_MOCK ? fetchMock(n) : fetchReal(n);
}

// ---------- 실서버 ----------
async function fetchReal(n: number): Promise<ApiResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res =
      REQUEST_STYLE === "get"
        ? await fetch(`${API_URL}?${N_PARAM}=${n}`, { signal: ctrl.signal })
        : await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [N_BODY_KEY]: n }),
            signal: ctrl.signal,
          });

    if (res.status === 400 || res.status === 422) {
      const body = await res.json().catch(() => ({}));
      return { ok: false, error: { kind: "bad_input", message: detailOf(body) ?? "입력이 올바르지 않습니다." } };
    }
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      return { ok: false, error: { kind: "server_down", message: "서버가 잠시 응답하지 않아요. 조금 뒤 다시 시도해 주세요." } };
    }
    if (!res.ok) {
      return { ok: false, error: { kind: "unknown", message: `서버 오류 (${res.status})` } };
    }

    const data = (await res.json()) as unknown;
    if (!isPredictResponse(data)) {
      // 연결은 됐지만 명세와 다른 모양(예: 정원 연습 서버의 dummy 응답) → 받은 그대로 보여줌
      return {
        ok: false,
        error: { kind: "unknown", message: `응답 형식이 명세와 달라요. 받은 데이터: ${JSON.stringify(data).slice(0, 300)}` },
      };
    }
    return { ok: true, data };
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      return { ok: false, error: { kind: "timeout", message: "응답이 너무 느려요. 다시 시도해 주세요." } };
    }
    return { ok: false, error: { kind: "server_down", message: "서버에 연결할 수 없어요." } };
  } finally {
    clearTimeout(timer);
  }
}

function isPredictResponse(d: unknown): d is PredictResponse {
  return !!d && typeof d === "object" && Array.isArray((d as PredictResponse).results);
}

/** FastAPI 의 detail — 문자열이거나 422 배열 [{loc, msg}] */
function detailOf(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const d = (body as { detail: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((e: { loc?: unknown[]; msg?: string }) => {
        const loc = Array.isArray(e.loc) ? e.loc.filter((x) => x !== "body" && x !== "query").join(".") : "";
        return loc ? `${loc}: ${e.msg ?? ""}` : String(e.msg ?? "");
      })
      .join(", ");
  }
  return JSON.stringify(d);
}

// ---------- 목업 ----------
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function fetchMock(n: number): Promise<ApiResult> {
  const sc = currentScenario();
  await sleep(sc === "slow" ? TIMEOUT_MS + 500 : 300);

  switch (sc) {
    case "slow":
      return { ok: false, error: { kind: "timeout", message: "응답이 너무 느려요. 다시 시도해 주세요." } };
    case "down":
      return { ok: false, error: { kind: "server_down", message: "서버가 잠시 응답하지 않아요. 조금 뒤 다시 시도해 주세요." } };
    case "error":
      return { ok: false, error: { kind: "bad_input", message: mockBadInput.detail } };
    case "stale":
      return { ok: true, data: withN(mockStale, n) };
    case "wide":
      return { ok: true, data: withN(mockWide, n) };
    case "night":
      return { ok: true, data: withN(mockNight, n) };
  }

  const base = n <= 0 ? mockN0 : n <= 3 ? mockN3 : n <= 15 ? mockN15 : mockN30;
  return { ok: true, data: withN(base, n) };
}

function withN(m: unknown, n: number): PredictResponse {
  return { ...(m as PredictResponse), n_ahead: n };
}