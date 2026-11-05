import { N_MAX } from "../types";
import type { Level, PredictItem } from "../types";

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

/** '판단하기 일러요' 단계의 이유. 백엔드 reason("P 0.97 ≥ 기준 0.80")은 개발자용이라 필드로 쉬운 문장을 만든다 */
export function whyText(i: PredictItem): string {
  if (i.load_10 == null || i.load_90 == null) return "인원 정보를 확인하고 있어요.";
  return `버스가 ${stopsAwayText(i.stops_away)}이라 도착 때 인원이 ${Math.round(i.load_10)}~${Math.round(i.load_90)}명으로 아직 폭이 넓어요.`;
}

export type Tone = "ok" | "warn" | "bad" | "hold";
export interface Verdict { badge: string; tone: Tone; word: string; guide: string }

/** 한눈에 보는 판정. 색과 문구는 백엔드 단계(level)를 따른다. 확률 숫자로 색을 정하면 '수업 직전이라 여유를 내지 않는 칸'처럼
 *  서버가 내린 판단과 어긋난다. 확률은 근거로 함께 보여 준다. 혼잡도는 crowdLabel */
export function verdict(i: PredictItem): Verdict {
  if (i.level === "확률 보류" || i.p_board == null) return { badge: "확률 보류", tone: "hold", word: "", guide: "" };
  if (i.level === "판단하기 일러요") return { badge: "판단하기 일러요", tone: "hold", word: "아직 판단하기 일러요", guide: "" };
  const badge = "탑승 확률";
  if (i.level === "여유 있음") return { badge, tone: "ok", word: "여유 있어요", guide: "" };
  if (i.level === "빠듯함") return { badge, tone: "warn", word: "빠듯해요", guide: i.p_board >= 0.8 ? "장담은 어려워요" : "못 탈 수도 있어요" };
  return { badge, tone: "bad", word: "타기 어려워요", guide: "" };
}

export interface QueueInfo { ok: number | null; hard: number | null; p: number[] }

/** 서버가 보낸 줄 길이 정보. 구버전 서버이거나 보류면 null */
export function queueOf(i: PredictItem | null): QueueInfo | null {
  if (!i?.p_by_n || i.level === "확률 보류") return null;
  return { ok: i.n_ok ?? null, hard: i.n_hard ?? null, p: i.p_by_n };
}

/** 앞 인원 n 에 맞춘 값. 서버를 다시 부르지 않고 확률과 단계만 바꾼다 */
export function withQueue(i: PredictItem, n: number): PredictItem {
  const q = queueOf(i);
  if (!q) return i;
  const level: Level = q.ok !== null && n <= q.ok ? "여유 있음" : q.hard !== null && n <= q.hard ? "빠듯함" : "어려울 수 있음";
  return { ...i, level, p_board: q.p[n] };
}

/** 인원을 고르기 전의 결론. 수치는 예측이라 '약'을 붙인다 */
export function queueSummary(q: QueueInfo): { tone: Tone; headline: string; sub: string } {
  const limit = q.hard !== null && q.hard < N_MAX ? `약 ${q.hard}명이 넘으면 타기 어려워요` : "";
  if (q.ok !== null) return { tone: "ok", headline: `앞 약 ${q.ok}명까지는 여유 있어요`, sub: limit };
  if (q.hard !== null) return { tone: "warn", headline: `앞 약 ${q.hard}명까지는 탈 수 있지만 빠듯해요`, sub: "" };
  return { tone: "bad", headline: "이번 버스는 타기 어려워요", sub: "" };
}

/** 확률이 없는 이유를 사용자 상황으로 묶는다. 서버가 준 상태만 쓰고 화면이 추측하지 않는다.
 *  일요일·공휴일은 아직 전용 코드가 없어 reason 문장으로 구분한다(isStale 과 같은 방식) */
export function holdMessage(i: PredictItem, state: ArrivalState): { title: string; body: string } {
  if (state === "stale") return { title: "버스 정보가 늦어지고 있어요", body: "새 정보가 들어오면 자동으로 보여 드릴게요. 급하면 정류장 안내판을 확인해 주세요." };
  if (state === "checking") {
    return i.arrival_status === "passed"
      ? { title: "이번 버스가 막 지나간 것 같아요", body: "" }  // 위 칸에 새 도착 정보를 확인 중이라고 이미 나온다
      : { title: "버스가 곧 오거나 막 지나갔어요", body: "" };
  }
  if (i.reason.includes("일요일")) return { title: "오늘은 탑승 예측을 쉬어요", body: "일요일·공휴일은 아직 검증 전이에요. 도착 시간은 그대로 볼 수 있어요." };
  return { title: "이 버스는 탑승 예측이 어려워요", body: "도착 시간은 그대로 볼 수 있어요." };
}

/** 도착 시 탑승 인원 기준 혼잡도. 응답에 차종별 정원이 없어 모든 버스에 같은 구간을 쓴다 */
export function crowdLabel(load: number): string {
  if (load <= 15) return "여유";
  if (load <= 30) return "보통";
  if (load <= 45) return "혼잡";
  return "매우 혼잡";
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

/** 화면에 받아 둔 확률이 지금 입력한 인원으로 계산된 것인지. 도착 시간·차내 인원은 인원과 무관하므로 확률에만 쓴다.
 *  current: 같은 인원 / calculating: 새 인원의 응답을 기다리는 중 / unavailable: 새 인원의 응답을 못 받음(실패·인터넷 끊김) / invalid: 입력이 잘못됨 */
export type ProbState = "current" | "calculating" | "unavailable" | "invalid";

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

/** 정류장 목록 한 줄의 도착 문구. 시간이 지나면 '곧 도착'이 남지 않도록 상태를 먼저 본다 */
export function arrivalText(i: PredictItem, now: number, fetchedAt: number): string {
  const state = arrivalState(i, now, fetchedAt);
  if (state === "stale") return "정보 없음";
  if (state === "checking") return "도착 확인 중";
  return etaText(Math.max(0, (arrivalAt(i, fetchedAt) - now) / 1000));
}
