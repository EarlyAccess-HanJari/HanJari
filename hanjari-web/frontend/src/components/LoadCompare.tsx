import type { PredictItem } from "../types";
import s from "./LoadCompare.module.css";

/** 지금 차 안 인원과 도착 때 예상 인원을 나란히 — 둘을 한눈에 비교하게 */
export default function LoadCompare({ item, stale }: { item: PredictItem; stale: boolean }) {
  const now = stale ? "—" : `${item.r_now}명`;
  const pred =
    stale || item.level === "확률 보류" ? "—"
    : item.level === "판단하기 일러요" ? `${Math.round(item.load_10)}~${Math.round(item.load_90)}명`
    : `약 ${Math.round(item.load_pred)}명`;
  return (
    <div className={s.wrap} data-testid="loads">
      <div className={s.col}><span className={s.k}>현재 차내 인원</span><span className={s.v}>{now}</span></div>
      <div className={s.sep} aria-hidden="true" />
      <div className={s.col}><span className={s.k}>도착 시 차내 인원</span><span className={`${s.v} ${s.em}`}>{pred}</span></div>
    </div>
  );
}
