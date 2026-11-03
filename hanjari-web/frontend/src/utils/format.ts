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
const MAX_SNAP_AGE_SEC = 180;  // 이보다 오래됐거나 미래로 보이면(폰 시계 어긋남·목업) 받은 시각 기준으로 셈

/** 버스가 도착할 시각(ms).
 *  eta_sec 는 스냅샷 시각(updated, KST "HH:MM:SS")의 남은 시간이라, 받은 시각이 아니라 스냅샷 시각에 더한다.
 *  받은 시각에 더하면 스냅샷 나이(최대 약 27초)만큼 새로고침마다 숫자가 출렁인다. */
export function arrivalAt(i: PredictItem, fetchedAt: number): number {
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
  if (i.level === "판단하기 일러요") {
    return `버스가 ${stopsAwayText(i.stops_away)}이라 도착 때 인원이 ${Math.round(i.load_10)}~${Math.round(i.load_90)}명으로 아직 폭이 넓어요.`;
  }
  const load = Math.round(i.load_pred);
  return i.stops_away === 0
    ? `지금 ${i.r_now}명 탄 버스가 곧 도착해요. 내리고 타는 사람을 반영하면 약 ${load}명이에요.`
    : `지금 ${i.r_now}명 탄 버스가 ${i.stops_away}정류장을 더 지나면 약 ${load}명이 될 것 같아요.`;
}

export type Tone = "ok" | "warn" | "bad" | "hold";
export interface Verdict { badge: string; guide: string; tone: Tone; crowd: string }

/** 한눈에 보는 판정. 색·뱃지·문구를 확률(p_board) 기준 한 곳에서 정해 서로 어긋나지 않게 한다.
 *  80% 이상 초록 / 50~79% 주황 / 50% 미만 빨강(뱃지 문구는 80·60·40% 경계). 보류·판단 이른 단계는 회색.
 *  '빠듯함'은 확률이 높아도 백엔드가 수업 시간·거리 때문에 내리는 단계라 '탑승 가능'으로 낮추고 시간 빠듯함을 안내 */
export function verdict(i: PredictItem): Verdict {
  if (i.level === "확률 보류")
    return { badge: "확률 보류", tone: "hold", crowd: "", guide: "확률은 잠시 보류했어요. 위의 도착 정보만 참고해 주세요." };
  if (i.level === "판단하기 일러요")
    return { badge: "판단하기 일러요", tone: "hold", crowd: "", guide: "버스가 가까워지면 다시 확인해 주세요." };
  const p = i.p_board;
  if (p >= 0.8)
    return i.level === "빠듯함"
      ? { badge: "탑승 유력", tone: "ok", crowd: "여유", guide: "탈 수 있지만 수업 시간엔 빠듯할 수 있어요." }
      : { badge: "탑승 유력", tone: "ok", crowd: "여유", guide: "줄을 서면 안정적으로 탑승할 수 있어요." };
  if (p >= 0.6)
    return { badge: "혼잡 주의", tone: "warn", crowd: "혼잡", guide: "앞줄에 서면 탈 수 있지만, 차내가 다소 혼잡해요." };
  if (p >= 0.5)
    return { badge: "탑승 아슬아슬", tone: "warn", crowd: "혼잡", guide: "탑승이 불확실해요. 다음 버스 도착 시간도 확인해보세요." };
  if (p >= 0.4)
    return { badge: "탑승 아슬아슬", tone: "bad", crowd: "매우 혼잡", guide: "탑승이 불확실해요. 다음 버스 도착 시간도 확인해보세요." };
  return { badge: "다음 차 권장", tone: "bad", crowd: "매우 혼잡", guide: "만차 가능성이 높아요. 다음 차 탑승을 권장해요." };
}

/** serve.py 가 스냅샷이 오래됐을 때 붙이는 reason("…N분 전 것…", "정보가 N초 전 것")으로 판별 */
export function isStale(i: PredictItem): boolean {
  return i.level === "확률 보류" && i.reason.includes("전 것");
}
