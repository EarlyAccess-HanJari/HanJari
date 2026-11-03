import type { PredictItem } from "../types";
import { pct, verdict, whyText } from "../utils/format";
import s from "./ResultCard.module.css";

interface Props {
  item: PredictItem;
  invalid: boolean;  // 입력이 잘못됐으면 결과 대신 안내
}

/** 히어로 카드 안의 게이지 + 한 줄 가이드. 색은 바깥 히어로 카드(--lv-*)가 준다 */
export default function ResultCard({ item, invalid }: Props) {
  if (invalid) {
    return (
      <div className={s.card} aria-live="polite" data-testid="result">
        <p className={s.guide}>인원을 확인해 주세요</p>
        <p className={s.why}>올바른 인원을 넣으면 바로 다시 계산해요.</p>
      </div>
    );
  }

  // F-04: 보류·판단 이른 단계에선 확률·예상 인원을 숨긴다
  const showP = item.level !== "확률 보류" && item.level !== "판단하기 일러요";
  const p = pct(item.p_board);
  return (
    <div className={s.card} aria-live="polite" data-testid="result">
      {showP && (
        <div className={s.track} aria-hidden="true"><div className={s.fill} style={{ width: `${p}%` }} /></div>
      )}
      <p className={s.guide}>{verdict(item).guide}</p>
      {!showP && <p className={s.why}>{whyText(item)}</p>}
    </div>
  );
}
