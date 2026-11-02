import type { PredictItem } from "../types";
import { etaText } from "../utils/format";
import LevelBadge from "./LevelBadge";
import s from "./OtherStops.module.css";

/** 같은 노선의 다른 탑승 정류장 — 한 정류장 앞뒤로 걸어가 볼지 판단용.
 *  시간은 '이 버스가 그 정류장에 도착하는 시간' 기준이라고 밝혀 둔다 */
export default function OtherStops({ items, onPick }: { items: PredictItem[]; onPick: (i: PredictItem) => void }) {
  if (items.length === 0) return null;
  return (
    <section className={s.wrap} aria-label="같은 노선 다른 정류장">
      <div className={s.head}>
        <h3 className={s.title}>같은 노선 다른 정류장</h3>
        <p className={s.help}>각 정류장에 이 버스가 도착하는 시간</p>
      </div>
      <div className={s.list}>
        {items.map((i) => {
          const eta = etaText(i.eta_sec);
          return (
            <button key={`${i.route}-${i.stop}`} type="button" className={s.item} onClick={() => onPick(i)}
              data-testid={`card-${i.route}-${i.stop}`}>
              <span className={s.text}>
                <span className={s.name}>{i.stop_name}</span>
                <span className={s.sub}>이 정류장에 {eta === "곧 도착" ? eta : `${eta} 도착`}</span>
              </span>
              <LevelBadge level={i.level} />
            </button>
          );
        })}
      </div>
    </section>
  );
}
