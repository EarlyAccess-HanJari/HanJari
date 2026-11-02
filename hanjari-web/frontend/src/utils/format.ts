import type { PredictItem } from "../types";

export function etaText(sec: number): string {
  if (sec <= 60) return "곧 도착";
  return `약 ${Math.round(sec / 60)}분 후`;
}

export function stopsAwayText(n: number): string {
  return n === 0 ? "바로 앞 정류장" : `${n}정류장 전`;
}

/** 0~99. 모델이 1.0 을 줘도 '100%' 는 확신처럼 읽혀서 99 에서 멈춤 */
export function pct(p: number): number {
  return Math.min(99, Math.round(p * 100));
}

export function mmss(sec: number): { m: number; s: string } {
  return { m: Math.floor(sec / 60), s: String(sec % 60).padStart(2, "0") };
}

const DAY_SEC = 86_400;
const KST_OFFSET_SEC = 9 * 3600;
const MAX_SNAP_AGE_SEC = 180;

/** 도착 예정 시각(ms). 서버의 제공 시각 + ETA를 사용하여 수집·수신 지연을 더하지 않는다.
 *  날짜 없는 구버전/목업 응답만 HH:MM:SS 또는 수신 시각으로 계산한다. */
export function arrivalAt(i: PredictItem, fetchedAt: number): number {
  if (i.arrival_at) return Date.parse(i.arrival_at);
  if (i.updated_at) {
    const snap = Date.parse(i.updated_at);
    const source = sourceAt(i);
    if (Number.isFinite(snap)) return (source ?? snap) + i.eta_sec * 1000;
  }
  const [h, m, sec] = i.updated.split(":").map(Number);
  const snapSod = h * 3600 + m * 60 + sec;
  const nowSod = Math.floor(fetchedAt / 1000 + KST_OFFSET_SEC) % DAY_SEC;
  const age = (nowSod - snapSod + DAY_SEC) % DAY_SEC;  // 자정 넘김 포함
  const base = Number.isFinite(age) && age <= MAX_SNAP_AGE_SEC ? fetchedAt - age * 1000 : fetchedAt;
  return base + i.eta_sec * 1000;
}

/** 문자열 입력 → 숫자 or 오류 메시지 */
export function parseN(raw: string, min: number, max: number): { n: number } | { error: string } {
  const t = raw.trim();
  if (t === "") return { error: "앞에 몇 명 있는지 입력해 주세요." };
  if (!/^\d+$/.test(t)) return { error: "숫자만 입력해 주세요." };
  const n = Number(t);
  if (n < min || n > max) return { error: `${min}~${max}명 사이로 입력해 주세요.` };
  return { n };
}

/** 백엔드 reason("P 0.97 ≥ 기준 0.80")은 개발자용이라, 화면에는 필드로 쉬운 문장을 만든다.
 *  확률 보류의 reason("평일 아님…", "N분 전 것…")은 그대로 읽혀서 그대로 쓴다. */
export function whyText(i: PredictItem): string {
  if (i.level === "확률 보류") return i.reason;
  if (i.load_pred == null || i.load_10 == null || i.load_90 == null || i.r_now == null) return "인원 정보를 확인하고 있어요.";
  if (i.level === "판단하기 일러요") {
    return `버스가 ${stopsAwayText(i.stops_away)}이라 도착 때 인원이 ${Math.round(i.load_10)}~${Math.round(i.load_90)}명으로 아직 폭이 넓어요.`;
  }
  const load = Math.round(i.load_pred);
  return i.stops_away === 0
    ? `지금 ${i.r_now}명 탄 버스가 곧 도착해요. 내리고 타는 사람을 반영하면 약 ${load}명이에요.`
    : `지금 ${i.r_now}명 탄 버스가 ${i.stops_away}정류장을 더 지나면 약 ${load}명이 될 것 같아요.`;
}

/** serve.py 가 스냅샷이 오래됐을 때 붙이는 reason("…N분 전 것…", "정보가 N초 전 것")으로 판별 */
export function isStale(i: PredictItem): boolean {
  return i.arrival_stale === true || (i.level === "확률 보류" && i.reason.includes("전 것"));
}

function sourceAt(i: PredictItem): number | null {
  if (!i.source_updated) return null;
  const raw = i.source_updated.replace(" ", "T");
  const stamp = Date.parse(/(Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}+09:00`);
  return Number.isFinite(stamp) ? stamp : null;
}

export type ArrivalState = "upcoming" | "checking" | "stale";

export function isOlderSnapshot(next: PredictItem, previous: PredictItem): boolean {
  const source = sourceAt(next), before = sourceAt(previous);
  return Boolean(next.updated_at && previous.updated_at && Date.parse(next.updated_at) < Date.parse(previous.updated_at))
    || (source !== null && before !== null && source < before);
}

/** 응답 후에도 시간이 흐른다. 같은 응답을 다시 받아도 유효 시간을 연장하지 않는다. */
export function arrivalState(i: PredictItem, now: number, fetchedAt: number): ArrivalState {
  const stamps = [i.updated_at ? Date.parse(i.updated_at) : null, sourceAt(i)];
  if (isStale(i) || stamps.some(t => t !== null && (now - t > MAX_SNAP_AGE_SEC * 1000 || t - now > 5000))) return "stale";
  if (i.arrival_status === "passed" || i.arrival_status === "checking" || now >= arrivalAt(i, fetchedAt)) return "checking";
  return "upcoming";
}
