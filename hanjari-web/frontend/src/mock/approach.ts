import type { Level, PredictItem } from "../types";

export interface ApproachStep {
  label: string;
  stops_away: number;
  eta: number;
  eta2: number;
  r_now: number;
  lo: number;
  mid: number;
  hi: number;
}

// 체험판 시뮬레이션. 동묘앞역으로 오는 한 버스를 따라가며 문구가 어떻게 바뀌는지 본다. 모델 출력이 아니다.
// 3번은 저장된 샘플(2026-09-30)의 값, 7번의 +36명은 10/26~11/4 기록에 있던 직전 정류장 몰림이고, 나머지는 설명을 위해 지은 값이다.
export const APPROACH_STEPS: ApproachStep[] = [
  { label: "3정류장 전", stops_away: 3, eta: 540, eta2: 840, r_now: 6, lo: 11, mid: 20, hi: 31 },
  { label: "2정류장 전", stops_away: 2, eta: 440, eta2: 740, r_now: 10, lo: 13, mid: 21, hi: 29 },
  { label: "1정류장 전: 동대문역에 아직 안 옴", stops_away: 1, eta: 345, eta2: 644, r_now: 15, lo: 14.4, mid: 21.5, hi: 27.6 },
  // 인원은 정류장을 출발할 때 갱신된다. 앞 정류장에 서 있는 동안은 지금 인원이 그대로고 타는 사람이 아직 안 잡힌다
  { label: "바로 앞: 동대문역에 서 있음", stops_away: 0, eta: 150, eta2: 450, r_now: 15, lo: 15, mid: 20, hi: 29 },
  { label: "바로 앞: 동대문역을 떠나 달리는 중", stops_away: 0, eta: 90, eta2: 390, r_now: 23, lo: 23, mid: 23, hi: 24 },
  { label: "곧 도착", stops_away: 0, eta: 40, eta2: 340, r_now: 23, lo: 23, mid: 23, hi: 23 },
  { label: "다른 경우: 동대문역에서 36명 몰림", stops_away: 0, eta: 90, eta2: 390, r_now: 51, lo: 50, mid: 51, hi: 52 },
];

// 저장된 동묘앞역 곡선(앞 26명 88%, 30명 60%, 34명 33%)에 맞춘 문턱. 도착 인원 + 앞 사람 수가 이 값 안이면 탄다
const LIMIT = 53;

function normalCdf(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989423 * Math.exp((-z * z) / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return z > 0 ? 1 - p : p;
}

export function approachItem(base: PredictItem, s: ApproachStep, n: number): PredictItem {
  const sd = Math.max((s.hi - s.lo) / 2.56, 0.8);
  const p = Math.min(0.975, Math.max(0.025, normalCdf((LIMIT - n - s.mid) / sd)));
  const ok = s.stops_away === 0 ? 0.94 : s.stops_away <= 2 ? 0.87 : 0.89;  // 수업 직전 칸의 '여유' 기준
  const level: Level = p >= ok ? "여유 있음" : p <= 0.3 ? "어려울 수 있음" : "빠듯함";
  return { ...base, stops_away: s.stops_away, eta_sec: s.eta, eta2_sec: s.eta2, r_now: s.r_now,
    load_pred: s.mid, load_10: s.lo, load_90: s.hi, p_board: Number(p.toFixed(3)), level };
}
