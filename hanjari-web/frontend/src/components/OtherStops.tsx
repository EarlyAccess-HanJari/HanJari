import type { PredictItem } from "../types";
import { arrivalAt, arrivalState, etaText } from "../utils/format";
import s from "./OtherStops.module.css";

/** 같은 노선의 다른 탑승 정류장 — 한 정류장 앞뒤로 걸어가 볼지 판단용.
 *  시간은 '이 버스가 그 정류장에 도착하는 시간' 기준이라고 밝혀 둔다 */
export default function OtherStops({ items, onPick, now, fetchedAt }: { items: PredictItem[]; onPick: (i: PredictItem) => void; now: number; fetchedAt: number }) {
  if (items.length === 0) return null;
  return (
    <section className={s.wrap} aria-label="같은 노선 다른 정류장">
      <div className={s.head}>
        <h3 className={s.title}>같은 노선 다른 정류장</h3>
        <p className={s.help}>각 정류장에 먼저 오는 버스 기준</p>
      </div>
      <div className={s.list}>
        {items.map((i) => {
          const state = arrivalState(i, now, fetchedAt);
          const eta = etaText(Math.max(0, (arrivalAt(i, fetchedAt) - now) / 1000));
          return (
            <button key={`${i.route}-${i.stop}`} type="button" className={s.item} onClick={() => onPick(i)}
              data-testid={`card-${i.route}-${i.stop}`}>
              <span className={s.text}>
                <span className={s.name}>{i.stop_name}</span>
                <span className={s.sub}>{state === "upcoming" ? `이 정류장에 ${eta === "곧 도착" ? eta : `${eta} 도착`}` : "도착 정보 갱신 중"}</span>
              </span>
              <span aria-hidden="true">›</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
