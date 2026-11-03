import type { PredictItem } from "../types";
import type { Tone } from "../utils/format";
import { verdict } from "../utils/format";
import lv from "./levels.module.css";
import s from "./LevelBadge.module.css";

export const TONE_CLASS: Record<Tone, string> = { ok: lv.ok, warn: lv.warn, bad: lv.bad, hold: lv.hold };

/** 히어로 카드와 같은 문구·색(verdict) — 백엔드 단계(level)는 data-level 에 원래 값으로 남김 */
export default function LevelBadge({ item }: { item: PredictItem }) {
  const v = verdict(item);
  return (
    <span className={`${s.badge} ${TONE_CLASS[v.tone]}`} data-level={item.level}>
      {v.badge}
    </span>
  );
}
