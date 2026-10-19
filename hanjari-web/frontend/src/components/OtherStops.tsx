import type { PredictItem } from "../types";
import { etaText, stopsAwayText } from "../utils/format";
import LevelBadge from "./LevelBadge";
import s from "./OtherStops.module.css";

/** 같은 노선의 다른 탑승 정류장 — 한 정류장 앞뒤로 걸어가 볼지 판단용 */
export default function OtherStops({ items, onPick }: { items: PredictItem[]; onPick: (i: PredictItem) => void }) {
  if (items.length === 0) return null;
  return (
    <section className={s.wrap} aria-label="같은 노선 다른 정류장">
      <h3 className={s.title}>같은 노선 다른 정류장</h3>
      {items.map((i) => (
        <button key={`${i.route}-${i.stop}`} type="button" className={s.item} onClick={() => onPick(i)}
          data-testid={`card-${i.route}-${i.stop}`}>
          <span className={s.text}>
            <span className={s.name}>{i.stop_name}</span>
            <span className={s.sub}>{stopsAwayText(i.stops_away)} · {etaText(i.eta_sec)}</span>
          </span>
          <LevelBadge level={i.level} />
        </button>
      ))}
    </section>
  );
}
