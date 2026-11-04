import type { PredictItem } from "../types";
import { isStale, pct, verdict, whyText } from "../utils/format";
import type { ArrivalState } from "../utils/format";
import s from "./ResultCard.module.css";

interface Props {
  item: PredictItem;
  invalid: boolean;  // 입력이 잘못됐으면 결과 대신 안내
  arrivalState: ArrivalState;
}

/** 히어로 카드 안의 게이지 + 한 줄 가이드. 색은 바깥 히어로 카드(--lv-*)가 준다 */
export default function ResultCard({ item, invalid, arrivalState }: Props) {
  if (invalid) {
    return (
      <div className={s.card} aria-live="polite" data-testid="result">
        <p className={s.guide}>인원을 확인해 주세요</p>
        <p className={s.why}>올바른 인원을 넣으면 바로 다시 계산해요.</p>
      </div>
    );
  }

  if (arrivalState !== "upcoming") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="확률 보류">
        <p className={s.guide}>버스 정보 갱신 중</p>
        <p className={s.why}>{arrivalState === "stale" && isStale(item)
          ? item.reason : "최신 도착 정보가 들어오면 자동으로 다시 표시해요."}</p>
      </div>
    );
  }

  // F-04: 보류·판단 이른 단계에선 확률·예상 인원을 숨긴다
  const showP = item.level !== "확률 보류" && item.level !== "판단하기 일러요" && item.p_board != null && Number.isFinite(item.p_board);
  const p = item.p_board == null ? null : pct(item.p_board);
  return (
    <div className={s.card} aria-live="polite" data-testid="result" data-level={item.level}>
      {showP && (
        <div className={s.track} aria-hidden="true"><div className={s.fill} style={{ width: `${p}%` }} /></div>
      )}
      <p className={s.guide}>{verdict(item).guide}</p>
      {!showP && <p className={s.why}>{whyText(item)}</p>}
    </div>
  );
}
