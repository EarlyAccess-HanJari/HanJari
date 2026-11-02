import { LEVELS, N_MAX, N_MIN, ROUTES } from "../types";
import type { PredictResponse, RouteCode } from "../types";

const count = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n >= 0;
const integer = (n: unknown): n is number => count(n) && Number.isInteger(n);

/** 잘못된 응답을 빈 버스·0%로 렌더링하지 않는다. 이전 응답의 보류 숫자는 읽되 화면에서 숨긴다. */
export function isPredictResponse(d: unknown): d is PredictResponse {
  if (!d || typeof d !== "object") return false;
  const data = d as Record<string, unknown>;
  if (!integer(data.n_ahead) || data.n_ahead < N_MIN || data.n_ahead > N_MAX || !Array.isArray(data.results)) return false;
  const seen = new Set<string>();
  return data.results.every((value: unknown) => {
    if (!value || typeof value !== "object") return false;
    const i = value as Record<string, unknown>;
    const route = i.route as RouteCode;
    if (!Object.hasOwn(ROUTES, route) || !ROUTES[route].stops.some(s => s.stop === i.stop)) return false;
    const key = `${route}:${i.stop}`;
    if (seen.has(key)) return false;
    seen.add(key);
    if (!LEVELS.some(l => l === i.level) || !["stop_name", "plate", "reason"].every(k => typeof i[k] === "string")) return false;
    if (typeof i.updated !== "string" || !/^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(i.updated)) return false;
    if (!integer(i.eta_sec) || !integer(i.stops_away)) return false;
    if (i.r_now !== null && !integer(i.r_now)) return false;
    for (const k of ["load_pred", "load_10", "load_90", "p_board"]) {
      if (i[k] !== null && !count(i[k])) return false;
    }
    if (typeof i.p_board === "number" && i.p_board > 1) return false;
    if (i.level !== "확률 보류" && [i.r_now, i.load_pred, i.load_10, i.load_90, i.p_board].some(n => n === null)) return false;
    if (typeof i.load_10 === "number" && typeof i.load_90 === "number" && i.load_10 > i.load_90) return false;
    if (i.updated_at !== undefined && (typeof i.updated_at !== "string" || !/(Z|[+-]\d{2}:\d{2})$/.test(i.updated_at) || !Number.isFinite(Date.parse(i.updated_at)))) return false;
    if (i.arrival_at !== undefined && (typeof i.arrival_at !== "string" || !/(Z|[+-]\d{2}:\d{2})$/.test(i.arrival_at) || !Number.isFinite(Date.parse(i.arrival_at)))) return false;
    if (i.arrival_status !== undefined && !["upcoming", "checking", "passed"].includes(String(i.arrival_status))) return false;
    if ((i.arrival_status === "checking" || i.arrival_status === "passed") && i.level !== "확률 보류") return false;
    if (i.arrival_stale !== undefined && typeof i.arrival_stale !== "boolean") return false;
    if (i.source_updated !== undefined && i.source_updated !== null && typeof i.source_updated !== "string") return false;
    if (i.vehicle_id !== undefined && typeof i.vehicle_id !== "string") return false;
    if (i.arrival_stale === true && i.level !== "확률 보류") return false;
    if (i.prediction_status !== undefined) {
      if (typeof i.prediction_status !== "string") return false;
      if (i.level === "확률 보류") {
        if (i.prediction_status === "ok" || [i.load_pred, i.load_10, i.load_90, i.p_board].some(n => n !== null)) return false;
      } else if (i.prediction_status !== "ok" || i.data_status !== "ok") return false;
    }
    return true;
  });
}
