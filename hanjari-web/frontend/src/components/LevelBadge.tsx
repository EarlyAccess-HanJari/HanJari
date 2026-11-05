import type { PredictItem } from "../types";
import type { ArrivalState, ProbState, Tone } from "../utils/format";
import { pct, verdict } from "../utils/format";
import lv from "./levels.module.css";
import s from "./LevelBadge.module.css";

export const TONE_CLASS: Record<Tone, string> = { ok: lv.ok, warn: lv.warn, bad: lv.bad, hold: lv.hold };

/** 히어로 카드와 같은 문구·색(verdict) — 백엔드 단계(level)는 data-level 에 원래 값으로 남김.
 *  도착 정보가 낡았거나 지금 입력한 인원의 확률이 아니면 받은 확률을 보이지 않는다 */
export default function LevelBadge({ item, state, prob }: { item: PredictItem; state: ArrivalState; prob: ProbState }) {
  const calculating = state === "upcoming" && prob === "calculating";
  const shown = state !== "upcoming" || prob !== "current" ? { ...item, level: "확률 보류" as const } : item;
  const v = verdict(shown);
  const showP = shown.level !== "확률 보류" && shown.level !== "판단하기 일러요" && shown.p_board != null;
  return (
    <span className={`${s.badge} ${TONE_CLASS[v.tone]}`} data-level={shown.level}>
      {calculating ? "계산 중" : v.badge}{showP ? ` ${pct(shown.p_board!)}%` : ""}
    </span>
  );
}
