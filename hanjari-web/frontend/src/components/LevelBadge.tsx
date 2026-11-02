import type { Level } from "../types";
import lv from "./levels.module.css";
import s from "./LevelBadge.module.css";

export const LEVEL_CLASS: Record<Level, string> = {
  "여유 있음": lv.ok,
  "빠듯함": lv.tight,
  "어려울 수 있음": lv.hard,
  "판단하기 일러요": lv.early,
  "확률 보류": lv.hold,
};

/** 배지에 보이는 이름. 백엔드 단계(level)는 그대로 두고 표시만 바꾼다 — data-level 은 원래 값 */
const SHORT: Record<Level, string> = {
  "여유 있음": "가능성 높음",
  "빠듯함": "가능성 보통",
  "어려울 수 있음": "가능성 낮음",
  "판단하기 일러요": "판단하기 일러요",
  "확률 보류": "확률 보류",
};

export default function LevelBadge({ level }: { level: Level }) {
  return (
    <span className={`${s.badge} ${LEVEL_CLASS[level]}`} data-level={level}>
      {SHORT[level]}
    </span>
  );
}
