import type { Level, PredictItem } from "../types";
import { pct, whyText } from "../utils/format";
import { LEVEL_CLASS } from "./LevelBadge";
import lv from "./levels.module.css";
import s from "./ResultCard.module.css";

const GUIDE: Record<Level, string> = {
  "여유 있음": "이번 버스 기다리셔도 좋아요.",
  "빠듯함": "탈 수도 있지만 장담하긴 어려워요.",
  "어려울 수 있음": "이번 버스는 타기 어려울 수 있어요. 다음 버스나 다른 방법도 생각해 보세요.",
  "판단하기 일러요": "버스가 가까워지면 다시 확인해 주세요.",
  "확률 보류": "확률은 잠시 보류했어요. 위의 도착 정보만 참고해 주세요.",
};

interface Props {
  item: PredictItem;
  invalid: boolean;  // 입력이 잘못됐으면 결과 대신 안내
  busy: boolean;     // 새 인원으로 다시 불러오는 중
}

export default function ResultCard({ item, invalid, busy }: Props) {
  if (invalid) {
    return (
      <section className={`${s.card} ${lv.hold}`} aria-live="polite" data-testid="result">
        <div className={s.head}><HoldIcon /><h2 className={s.title}>인원을 확인해 주세요</h2></div>
        <p className={s.why}>올바른 인원을 넣으면 바로 다시 계산해요.</p>
      </section>
    );
  }

  // F-04: 보류·판단 이른 단계에선 확률·예상 인원을 숨긴다
  const showP = item.level !== "확률 보류" && item.level !== "판단하기 일러요";
  const p = pct(item.p_board);
  return (
    <section className={`${s.card} ${LEVEL_CLASS[item.level]}`} aria-live="polite" aria-busy={busy}
      data-testid="result" data-level={item.level}>
      <div className={s.head}>
        <LevelIcon level={item.level} />
        <h2 className={s.title}>{item.level}</h2>
        {showP && (
          <div className={s.p}>
            <div className={s.pLabel}>탈 확률</div>
            <div><span className={s.pNum}>{p}</span><span className={s.pUnit}>%</span></div>
          </div>
        )}
      </div>
      {showP && (
        <div className={s.track} aria-hidden="true"><div className={s.fill} style={{ width: `${p}%` }} /></div>
      )}
      <p className={s.guide}>{GUIDE[item.level]}</p>
      {showP && (
        <div className={s.load}>
          <span>도착 때 예상 인원</span>
          <span><b>약 {Math.round(item.load_pred)}명</b> ({Math.round(item.load_10)}~{Math.round(item.load_90)}명)</span>
        </div>
      )}
      <p className={s.why}>{whyText(item)}</p>
    </section>
  );
}

const ICON = {
  width: 28, height: 28, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true,
};

function LevelIcon({ level }: { level: Level }) {
  switch (level) {
    case "여유 있음":
      return <svg {...ICON}><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9.5" /></svg>;
    case "빠듯함":
      return <svg {...ICON}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
    case "어려울 수 있음":
      return <svg {...ICON}><path d="M12 3.5L2.5 20h19z" /><path d="M12 10v4.5" /><path d="M12 17.3v.2" /></svg>;
    case "판단하기 일러요":
      return <svg {...ICON}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.4" /><path d="M12 16.8v.2" /></svg>;
    case "확률 보류":
      return <HoldIcon />;
  }
}

function HoldIcon() {
  return <svg {...ICON}><circle cx="12" cy="12" r="9" /><path d="M10 9v6" /><path d="M14 9v6" /></svg>;
}
