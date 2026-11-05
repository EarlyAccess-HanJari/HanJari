import type { PredictItem } from "../types";
import { crowdLabel } from "../utils/format";
import s from "./LoadCompare.module.css";

function Layout({ now, pred, range }: { now: string; pred: string; range?: string }) {
  return (
    <div className={s.wrap} data-testid="loads">
      <div className={s.col}><span className={s.k}>지금 · 공공데이터</span><span className={s.v}>{now}</span></div>
      <div className={s.sep} aria-hidden="true" />
      <div className={s.col}>
        <span className={s.k}>도착 때 · 한자리 예측</span>
        <span className={`${s.v} ${s.em}`}>{pred}</span>
        {range && <span className={s.range}>{range}</span>}
      </div>
    </div>
  );
}

/** 사실(공공데이터)과 예측을 출처를 밝혀 나란히. 둘을 한눈에 비교하면서 어느 쪽 값인지 헷갈리지 않게 */
export default function LoadCompare({ item, stale }: { item: PredictItem; stale: boolean }) {
  const currentValid = item.data_status === "ok" || (item.data_status === undefined && item.level !== "확률 보류");
  const now = stale || !currentValid || item.r_now == null ? "—" : `약 ${item.r_now}명`;
  const held = stale || item.level === "확률 보류" || item.load_pred == null;
  const span = item.load_10 == null || item.load_90 == null ? null : `${Math.round(item.load_10)}~${Math.round(item.load_90)}명`;
  const early = item.level === "판단하기 일러요";
  const pred = held ? "—" : early ? (span ?? "—") : `약 ${Math.round(item.load_pred!)}명 (${crowdLabel(item.load_pred!)})`;
  // 예측은 한 점이 아니라 범위라는 걸 보여 준다. 돌발 상황까지 맞힌다는 뜻이 아니므로 근거 안내와 함께 읽는다
  return <Layout now={now} pred={pred} range={!held && !early && span ? `${span} 사이` : undefined} />;
}

/** 정보가 없을 때(오류·불러오는 중)도 같은 자리를 지키는 자리표시 */
export function LoadPlaceholder() {
  return <Layout now="—" pred="—" />;
}
