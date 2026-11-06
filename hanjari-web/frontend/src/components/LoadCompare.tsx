import type { ReactNode } from "react";
import { ROUTES } from "../types";
import type { PredictItem } from "../types";
import { isSettled } from "../utils/format";
import s from "./LoadCompare.module.css";

const NOW_UNKNOWN = "지금 버스 안 —";
const PRED_UNKNOWN = "도착 때 버스 안 —";

function Layout({ now, pred, check }: { now: ReactNode; pred: ReactNode; check?: string }) {
  return (
    <div className={s.wrap} data-testid="loads">
      <p className={s.row}>
        <span className={s.main}>{now}</span>
        <span className={s.sub}>서울시 · 태그 기준</span>
      </p>
      <p className={s.row}>
        <span className={`${s.main} ${s.em}`}>{pred}</span>
        <span className={s.sub}>한자리 예측</span>
      </p>
      {check && <p className={s.check}>{check}</p>}
    </div>
  );
}

/** 숫자만 두면 빈자리 수로 읽히고, 범위나 숫자 둘은 어느 쪽이 답인지 헷갈린다. 지금 → 도착 때를 이어지는 문장으로 말한다.
 *  얼마나 정해졌는지는 말끝으로 구분한다. 오차는 탑승 가능성 계산에 이미 들어 있다 */
export default function LoadCompare({ item, stale }: { item: PredictItem; stale: boolean }) {
  const currentValid = item.data_status === "ok" || (item.data_status === undefined && item.level !== "확률 보류");
  const now = stale || !currentValid || item.r_now == null
    ? NOW_UNKNOWN
    : <>지금 <b>{item.r_now === 0 ? "0명" : `약 ${item.r_now}명`}</b> 타고 있어요</>;
  if (stale || item.level === "확률 보류" || item.load_pred == null) return <Layout now={now} pred={PRED_UNKNOWN} />;
  // '판단하기 일러요'는 예전 서버의 단계다. 대표 숫자를 믿기 어렵다는 뜻이라 범위로 말한다
  const predN = Math.round(item.load_pred);
  const count = item.level === "판단하기 일러요" && item.load_10 != null && item.load_90 != null
    ? `${Math.round(item.load_10)}~${Math.round(item.load_90)}명`
    : `약 ${predN}명`;
  // 지금 인원에서 도착 때 인원으로 어떻게 이어지는지 말한다
  const change = currentValid && item.r_now != null ? predN - item.r_now : null;
  const lead = change === null ? "도착 땐" : change >= 2 ? "더 타서 도착 땐" : change <= -2 ? "내려서 도착 땐" : "도착 때도";
  const settled = isSettled(item);
  // 대표 숫자만 말하는 대신 언제 확인되는지 알린다. 인원은 정류장을 출발할 때 갱신된다. 이름은 내 정류장 바로 전 정류장
  const prev = ROUTES[item.route]?.stops.find((x) => x.stop === item.stop)?.prev;
  const check = settled || !prev ? undefined : `버스가 ${prev}(1정류장 전)에서 출발하면 실제 탑승 기록으로 다시 계산해요`;
  return <Layout now={now} pred={<>{lead} <b>{count}</b>일 {settled ? "거예요" : "것 같아요"}</>} check={check} />;
}

/** 정보가 없을 때(오류·불러오는 중)도 같은 자리를 지키는 자리표시 */
export function LoadPlaceholder() {
  return <Layout now={NOW_UNKNOWN} pred={PRED_UNKNOWN} />;
}
