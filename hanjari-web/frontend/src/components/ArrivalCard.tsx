import type { PredictItem } from "../types";
import { arrivalAt, mmss, stopsAwayText } from "../utils/format";
import type { ArrivalState } from "../utils/format";
import s from "./ArrivalCard.module.css";

interface Props {
  item: PredictItem;
  state: ArrivalState;
  fetchedAt: number;
  now: number;
}

export default function ArrivalCard({ item, state, fetchedAt, now }: Props) {
  // 차량/제공 시각이 바뀌면 새 ETA를 즉시 반영한다. 이전 차량의 예정 시각을 이어 쓰지 않는다.
  const left = Math.max(0, Math.ceil((arrivalAt(item, fetchedAt) - now) / 1000));
  const t = mmss(left);
  return (
    <section className={s.arrival} aria-label="남은 시간" data-testid="arrival">
      {state === "stale" && (
        <div className={s.stale} role="status" data-testid="notice-stale">
          버스 정보가 오래됐어요. 실제와 다를 수 있어요.
        </div>
      )}
      <div className={s.row}>
        <span className={s.label}>남은 시간</span>
        {state === "stale" ? (
          <span className={s.sub}>지금은 버스 위치를 확인할 수 없어요. 정류장 안내판을 확인해 주세요.</span>
        ) : state === "checking" ? (
          <span className={s.sub} role="status" data-testid="arrival-checking">새 도착 정보를 확인하고 있어요.</span>
        ) : (
          <span className={s.group}>
            <span className={s.eta}>
              {left < 60 ? <span className={s.soon}>곧 도착</span> : (
                <>
                  <span className={s.num}>{t.m}</span><span className={s.unit}>분</span>
                  <span className={s.num}>{t.s}</span><span className={s.unit}>초</span>
                </>
              )}
            </span>
            <span className={s.away}>· {stopsAwayText(item.stops_away)}</span>
          </span>
        )}
      </div>
    </section>
  );
}
