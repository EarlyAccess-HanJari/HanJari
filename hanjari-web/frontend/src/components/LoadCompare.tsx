import type { PredictItem } from "../types";
import s from "./LoadCompare.module.css";

/** 카드 집계에 기반한 현재 인원. 탑승 가능 인원/미래 인원과 구분한다. */
export default function LoadCompare({ item, stale }: { item: PredictItem; stale: boolean }) {
  const currentValid = item.data_status === "ok" || (item.data_status === undefined && item.level !== "확률 보류");
  const now = stale || !currentValid || item.r_now == null ? "—" : `약 ${item.r_now}명`;
  return (
    <div className={s.wrap} data-testid="loads">
      <div className={s.col}><span className={s.k}>현재 차내 인원 · 추정</span><span className={s.v}>{now}</span></div>
      <p className={s.note}>{stale ? "새 버스 정보를 기다리고 있어요." : !currentValid || item.r_now == null
        ? "현재 인원 정보를 확인할 수 없어요."
        : "카드 승하차 집계로 추정한 인원이에요. 하차 미태그 등으로 실제와 다를 수 있어요."}</p>
    </div>
  );
}
