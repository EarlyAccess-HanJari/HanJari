import type { PredictItem } from "../types";
import { verdict } from "../utils/format";
import s from "./LoadCompare.module.css";

const BusIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="3" width="16" height="15" rx="3" /><path d="M4 11h16" /><path d="M7 21v-3M17 21v-3" /><path d="M8 15h.01M16 15h.01" />
  </svg>
);
const PeopleIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="9" cy="8" r="3.2" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" /><path d="M16 5.2a3.2 3.2 0 0 1 0 5.6M18 14.4c1.9.8 3 2.7 3 5.6" />
  </svg>
);

/** 지금 차 안 인원과 도착 때 예상 인원 — 정보 위계를 낮춘 2열 미니 그리드 */
export default function LoadCompare({ item, stale }: { item: PredictItem; stale: boolean }) {
  const now = stale ? "—" : `${item.r_now}명`;
  const crowd = verdict(item).crowd;
  const pred =
    stale || item.level === "확률 보류" ? "—"
    : item.level === "판단하기 일러요" ? `${Math.round(item.load_10)}~${Math.round(item.load_90)}명`
    : `약 ${Math.round(item.load_pred)}명${crowd ? ` (${crowd})` : ""}`;
  return (
    <div className={s.wrap} data-testid="loads">
      <div className={`${s.col} ${s.left}`}><BusIcon /><span className={s.k}>현재 차내</span><span className={s.v}>{now}</span></div>
      <div className={s.sep} aria-hidden="true" />
      <div className={`${s.col} ${s.right}`}><PeopleIcon /><span className={s.k}>도착 시 예상</span><span className={s.v}>{pred}</span></div>
    </div>
  );
}

/** 정보가 없을 때(오류·불러오는 중)도 같은 자리를 지키는 자리표시 */
export function LoadPlaceholder() {
  return (
    <div className={s.wrap} data-testid="loads">
      <div className={`${s.col} ${s.left}`}><BusIcon /><span className={s.k}>현재 차내</span><span className={s.v}>—</span></div>
      <div className={s.sep} aria-hidden="true" />
      <div className={`${s.col} ${s.right}`}><PeopleIcon /><span className={s.k}>도착 시 예상</span><span className={s.v}>—</span></div>
    </div>
  );
}
