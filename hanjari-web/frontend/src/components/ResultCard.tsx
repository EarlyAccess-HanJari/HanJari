import type { ReactNode } from "react";
import type { PredictItem } from "../types";
import { chanceText, holdMessage, verdict, whyText } from "../utils/format";
import type { ArrivalState, ProbState, Tone } from "../utils/format";
import s from "./ResultCard.module.css";

interface Props {
  item: PredictItem;
  prob: ProbState;
  n: number | null;  // 지금 입력한 인원. 입력 전이면 null
  slow: boolean;     // 응답이 평소보다 오래 걸리는 중
  online: boolean;
  arrivalState: ArrivalState;
  onRetry: () => void;
}

// 색만으로 구분하지 않도록 단계마다 아이콘 모양도 다르다
const ICON: Record<Tone, ReactNode> = {
  ok: <><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.7 2.7L16 9.8" /></>,
  warn: <><path d="M12 4L3 19.5h18z" /><path d="M12 10v4.5" /><path d="M12 17.2h.01" /></>,
  bad: <><circle cx="12" cy="12" r="9" /><path d="M9 9l6 6" /><path d="M15 9l-6 6" /></>,
  hold: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.2" /><path d="M12 7.8h.01" /></>,
  idle: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.2" /><path d="M12 7.8h.01" /></>,
};

function Headline({ tone, text, action }: { tone: Tone; text: string; action?: ReactNode }) {
  return (
    <div className={s.row}>
      <p className={s.guide}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
          aria-hidden="true" data-testid="verdict-icon" data-tone={tone}>{ICON[tone]}</svg>
        <span>{text}</span>
      </p>
      {action}
    </div>
  );
}

/** 윗줄의 도착 때 인원에서 이어지는 문장. 여기에 내 앞 사람을 더해 결론으로 넘어간다 */
function Basis({ item, n }: { item: PredictItem; n: number | null }) {
  if (item.load_pred == null) return null;
  const load = Math.round(item.load_pred);
  return <p className={s.basis} data-testid="basis">{n === null ? "여기에 내 앞 사람이 타면…" : `약 ${load}명에 내 앞 ${n}명이 타면 약 ${load + n}명`}</p>;
}

/** 탈 수 있는지만 말한다. 앱은 줄을 모르므로 입력 전에는 말하지 않고, 입력 후에는 그 조건의 추정값이라고 밝힌다.
 *  색은 바깥 히어로 카드(--lv-*)가 준다 */
export default function ResultCard({ item, prob, n, slow, online, arrivalState, onRetry }: Props) {
  if (prob === "invalid") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result">
        <p className={s.guide}>인원을 확인해 주세요</p>
        <p className={s.why}>올바른 인원을 넣으면 바로 다시 계산해요.</p>
      </div>
    );
  }

  // 확률이 없어도 고장이 아니다. 믿어도 되는 것과 할 수 있는 일을 먼저 말한다
  if (arrivalState !== "upcoming" || item.level === "확률 보류") {
    const m = holdMessage(item, arrivalState);
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="확률 보류">
        <div data-testid="verdict">
          <Headline tone="hold" text={m.title} />
          {m.body && <p className={s.why}>{m.body}</p>}
        </div>
      </div>
    );
  }

  if (prob === "empty") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="입력 전">
        <div data-testid="verdict">
          <Basis item={item} n={null} />
          <Headline tone="idle" text="앞 사람 수를 고르면 알려 드려요" />
          <p className={s.why}>이 버스 탈 사람만 세면 돼요.</p>
        </div>
      </div>
    );
  }

  // 새 인원의 응답을 못 받았으면 이전 인원의 확률 대신 무엇이 비었는지 말한다. 도착 시간은 위에 그대로 보인다
  if (prob === "unavailable") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="확률 보류">
        <div data-testid="verdict">
          <Headline tone="hold" text={`${n}명 기준 확률을 못 받았어요`}
            action={online && <button type="button" className={s.retry} onClick={onRetry} data-testid="result-retry">다시 시도</button>} />
          <p className={s.why}>{online
            ? "도착 시간은 마지막으로 받은 정보예요. 연결되면 자동으로 다시 계산해요."
            : "인터넷이 연결되면 다시 계산해요. 도착 시간은 마지막으로 받은 정보예요."}</p>
        </div>
      </div>
    );
  }

  if (prob === "calculating") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="확률 보류">
        <div data-testid="verdict">
          <Basis item={item} n={n} />
          <Headline tone="hold" text={`${n}명 기준으로 다시 계산하고 있어요`} />
          {slow && <p className={s.why}>평소보다 오래 걸리고 있어요. 도착 시간은 그대로 볼 수 있어요.</p>}
        </div>
      </div>
    );
  }

  const v = verdict(item);
  const chance = item.level !== "판단하기 일러요" && item.p_board != null ? chanceText(item.p_board) : null;
  return (
    <div className={s.card} aria-live="polite" data-testid="result" data-level={item.level}>
      <div data-testid="verdict">
        {chance && <Basis item={item} n={n} />}
        <Headline tone={v.tone} text={chance ? `그러면 ${chance.rate}` : v.word} />
        <p className={s.why}>{chance ? `예상 ${chance.pct}` : whyText(item)}</p>
      </div>
    </div>
  );
}
