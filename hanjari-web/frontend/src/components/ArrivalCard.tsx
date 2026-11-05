import type { PredictItem } from "../types";
import { arrivalAt, mmss, stopsAwayText } from "../utils/format";
import type { ArrivalState } from "../utils/format";
import s from "./ArrivalCard.module.css";

interface Props {
  item: PredictItem;
  state: ArrivalState;
  fetchedAt: number;  // 응답을 받은 시각(ms)
  now: number;
}

const SOON_SEC = 60;  // 남은 시간이 이보다 적으면(1분 미만) '곧 도착'

/** 공공데이터가 알려 주는 사실만 담는다. 탈 수 있는지(예측)는 ResultCard 가 말한다 */
export default function ArrivalCard({ item, state, fetchedAt, now }: Props) {
  // 차량/제공 시각이 바뀌면 새 ETA를 즉시 반영한다. 이전 차량의 예정 시각을 이어 쓰지 않는다.
  const left = Math.max(0, Math.ceil((arrivalAt(item, fetchedAt) - now) / 1000));
  const t = mmss(left);
  const stale = state === "stale";
  return (
    <section className={s.arrival} aria-label="남은 시간" data-testid="arrival">
      <div className={s.top}>
        <span className={s.label}>이번 버스 <span className={s.source}>공공데이터</span></span>
        {!stale && <span className={s.away}>{stopsAwayText(item.stops_away)}</span>}
      </div>
      {/* 오래된 정보(수집 중단·새벽)면 몇 시간 전 버스를 카운트다운하게 되므로 도착 시간 대신 안내만 */}
      <div className={s.timeRow}>
        {stale ? (
          <span className={s.sub} role="status" data-testid="notice-stale">지금은 버스 위치를 확인할 수 없어요.</span>
        ) : state === "checking" ? (
          <span className={s.sub} role="status" data-testid="arrival-checking">새 도착 정보를 확인하고 있어요.</span>
        ) : (
          <span className={s.eta}>
            {left < SOON_SEC ? (
              <span className={s.soon}>곧 도착</span>
            ) : (
              <>
                <span className={s.num}>{t.m}</span><span className={s.unit}>분</span>
                <span className={s.num}>{t.s}</span><span className={s.unit}>초</span>
              </>
            )}
          </span>
        )}
      </div>
    </section>
  );
}
