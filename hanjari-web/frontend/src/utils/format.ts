import type { PredictItem } from "../types";

export function etaText(sec: number): string {
  if (sec <= 60) return "곧 도착";
  return `약 ${Math.round(sec / 60)}분 후`;
}

export function stopsAwayText(n: number): string {
  return n === 0 ? "바로 앞 정류장" : `${n}정류장 전`;
}

/** 사람 수를 문장에 넣을 때. 0명은 어림이 아니므로 '약'을 붙이지 않는다 */
export function people(n: number): string {
  return n === 0 ? "0명" : `약 ${n}명`;
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

export type Tone = "ok" | "warn" | "bad" | "hold" | "idle";  // idle: 정상인데 입력 전. 회색 hold 는 꺼진 화면처럼 보여 따로 둔다
export interface Verdict { badge: string; tone: Tone; word: string }

/** 입력한 인원의 판정. 색은 백엔드 단계(level)를 따른다. 확률 숫자로 색을 정하면 '수업 직전이라 여유를 내지 않는 칸'처럼
 *  서버가 내린 판단과 어긋난다. 문장은 chanceText */
export function verdict(i: PredictItem): Verdict {
  if (i.level === "확률 보류" || i.p_board == null) return { badge: "예측 없음", tone: "hold", word: "" };
  if (i.level === "판단하기 일러요") return { badge: "판단하기 일러요", tone: "hold", word: "아직 판단하기 일러요" };
  const badge = "탑승 확률";
  if (i.level === "여유 있음") return { badge, tone: "ok", word: "" };
  if (i.level === "빠듯함") return { badge, tone: "warn", word: "" };
  return { badge, tone: "bad", word: "" };
}

/** 앞 인원이 정해졌을 때의 탑승 가능성.
 *  0.95 이상·0.05 이하는 분위수 모델(5~95%)이 더 나누지 못하는 구간이라 숫자를 좁혀 말하지 않는다 */
export function chanceText(p: number): { rate: string; pct: string } {
  if (p >= 0.95) return { rate: "거의 항상 타요", pct: "95% 이상" };
  if (p <= 0.05) return { rate: "거의 못 타요", pct: "5% 이하" };
  return { rate: `10번 중 ${Math.round(p * 10)}번쯤 타요`, pct: `약 ${Math.round(p * 100)}%` };
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
  if (i.reason.includes("일요일")) return { title: "오늘은 탑승 예측을 쉬어요", body: "일요일·공휴일은 예측이 맞는지 아직 확인하지 못했어요. 도착 시간은 그대로 볼 수 있어요." };
  return { title: "이 버스는 탑승 예측이 어려워요", body: "도착 시간은 그대로 볼 수 있어요." };
}

/** 서버의 보류 이유 중 개발자용 문장을 사용자 말로 바꾼다. 모르는 문장은 그대로 둔다 */
export function reasonText(reason: string): string {
  if (reason.includes("일요일")) return "일요일·공휴일은 예측이 맞는지 아직 확인하지 못했어요.";
  if (reason.includes("검증 데이터 부족")) return "이 시간대에 이만큼 떨어진 버스는 예측을 확인할 기록이 아직 부족해요.";
  if (reason.includes("전 것")) return "버스 정보가 오래됐어요. 새 정보가 들어오면 다시 계산해요.";
  return reason;
}

/** 도착 인원 범위가 이 안이면 사실상 정해진 것이다(달리는 중인 가까운 버스). 응답에 정차 여부가 없어 범위로 판단한다 */
const SETTLED_SPAN = 3;
export function isSettled(i: PredictItem): boolean {
  return i.load_10 != null && i.load_90 != null && Math.round(i.load_90) - Math.round(i.load_10) <= SETTLED_SPAN;
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
 *  empty: 아직 입력 전 / current: 같은 인원 / calculating: 새 인원의 응답을 기다리는 중 / unavailable: 새 인원의 응답을 못 받음(실패·인터넷 끊김) / invalid: 입력이 잘못됨 */
export type ProbState = "empty" | "current" | "calculating" | "unavailable" | "invalid";

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
