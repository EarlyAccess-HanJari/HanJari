import type { PredictItem } from "../types";
import { isStale, pct, verdict, whyText } from "../utils/format";
import type { ArrivalState, ProbState } from "../utils/format";
import s from "./ResultCard.module.css";

interface Props {
  item: PredictItem;
  prob: ProbState;
  n: number | null;  // 지금 입력한 인원
  slow: boolean;     // 응답이 평소보다 오래 걸리는 중
  online: boolean;
  arrivalState: ArrivalState;
  onRetry: () => void;
}

/** 히어로 카드 안의 게이지 + 한 줄 가이드. 색은 바깥 히어로 카드(--lv-*)가 준다 */
export default function ResultCard({ item, prob, n, slow, online, arrivalState, onRetry }: Props) {
  if (prob === "invalid") {
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

  // 새 인원의 응답을 못 받았으면 이전 인원의 확률 대신 무엇이 비었는지 말한다. 도착 시간은 위에 그대로 보인다
  if (prob === "unavailable") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="확률 보류">
        <div className={s.row}>
          <p className={s.guide}>{n}명 기준 확률을 못 받았어요</p>
          {online && <button type="button" className={s.retry} onClick={onRetry} data-testid="result-retry">다시 시도</button>}
        </div>
        <p className={s.why}>{online
          ? "도착 시간은 마지막으로 받은 정보예요. 연결되면 자동으로 다시 계산해요."
          : "인터넷이 연결되면 다시 계산해요. 도착 시간은 마지막으로 받은 정보예요."}</p>
      </div>
    );
  }

  const calculating = prob === "calculating";
  // F-04: 보류·판단 이른 단계에선 확률·예상 인원을 숨긴다
  const showP = !calculating && item.level !== "확률 보류" && item.level !== "판단하기 일러요" && item.p_board != null && Number.isFinite(item.p_board);
  const p = item.p_board == null ? null : pct(item.p_board);
  const why = whyText(item);
  return (
    <div className={s.card} aria-live="polite" data-testid="result" data-level={calculating ? "확률 보류" : item.level}>
      {/* 계산 중에도 게이지 자리를 비워 두어 결과가 오면 글자가 밀리지 않고 게이지만 차오른다 */}
      {(showP || calculating) && (
        <div className={s.track} aria-hidden="true"><div className={s.fill} style={{ width: showP ? `${p}%` : "0%" }} /></div>
      )}
      <p className={s.guide}>{calculating ? `${n}명 기준으로 다시 계산하고 있어요.` : verdict(item).guide}</p>
      {!showP && !calculating && why && <p className={s.why}>{why}</p>}
      {calculating && slow && <p className={s.why}>평소보다 오래 걸리고 있어요. 도착 시간은 그대로 볼 수 있어요.</p>}
    </div>
  );
}
