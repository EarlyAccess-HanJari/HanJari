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

export default function LevelBadge({ level }: { level: Level }) {
  return (
    <span className={`${s.badge} ${LEVEL_CLASS[level]}`} data-level={level}>
      {level}
    </span>
  );
}
