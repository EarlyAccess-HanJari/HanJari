import type { ReactNode } from "react";
import type { PredictItem } from "../types";
import { etaText, holdMessage, pct, queueOf, queueSummary, verdict, whyText } from "../utils/format";
import type { ArrivalState, ProbState, Tone } from "../utils/format";
import QueueBar from "./QueueBar";
import s from "./ResultCard.module.css";

interface Props {
  item: PredictItem;
  prob: ProbState;
  n: number | null;  // 지금 입력한 인원. 서버가 줄 길이 정보를 주면 비워 둘 수 있다
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

/** 자리를 항상 잡아 둔다. 다음 버스가 생기고 없어져도 아래 내용이 밀리지 않게 */
function NextBus({ text, strong = false }: { text: string | null; strong?: boolean }) {
  return <p className={`${s.next} ${strong ? s.nextStrong : ""}`}>{text && <span data-testid="next-bus">{text}</span>}</p>;
}

/** 히어로 카드의 결론: 탈 수 있는지 → 근거 → 못 타면 어떻게 할지. 색은 바깥 히어로 카드(--lv-*)가 준다 */
export default function ResultCard({ item, prob, n, slow, online, arrivalState, onRetry }: Props) {
  if (prob === "invalid") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result">
        <p className={s.guide}>인원을 확인해 주세요</p>
        <p className={s.why}>올바른 인원을 넣으면 바로 다시 계산해요.</p>
      </div>
    );
  }

  const next = arrivalState !== "stale" && item.eta2_sec != null ? etaText(item.eta2_sec) : null;

  // 확률이 없어도 고장이 아니다. 믿어도 되는 것과 할 수 있는 일을 먼저 말한다
  if (arrivalState !== "upcoming" || item.level === "확률 보류") {
    const m = holdMessage(item, arrivalState);
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="확률 보류">
        <div data-testid="verdict">
          <Headline tone="hold" text={m.title} />
          {m.body && <p className={s.why}>{m.body}</p>}
        </div>
        <NextBus text={next && `다음 버스 ${next}`} strong />
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
        <NextBus text={next && `다음 버스 ${next}`} />
      </div>
    );
  }

  if (prob === "calculating") {
    return (
      <div className={s.card} aria-live="polite" data-testid="result" data-level="확률 보류">
        <div data-testid="verdict">
          <Headline tone="hold" text={`${n}명 기준으로 다시 계산하고 있어요`} />
          {slow && <p className={s.why}>평소보다 오래 걸리고 있어요. 도착 시간은 그대로 볼 수 있어요.</p>}
        </div>
        {/* 게이지 자리를 비워 두어 결과가 오면 글자가 밀리지 않고 게이지만 차오른다 */}
        <div className={s.track} aria-hidden="true"><div className={s.fill} style={{ width: "0%" }} /></div>
        <NextBus text={next && `못 타면 다음 버스 ${next}`} />
      </div>
    );
  }

  const queue = queueOf(item);
  const v = verdict(item);
  const early = item.level === "판단하기 일러요";
  const summary = queue && n === null ? queueSummary(queue) : null;
  const tone = summary?.tone ?? v.tone;
  const headline = summary?.headline ?? (early ? v.word : `앞 ${n}명이라면 ${v.word}`);
  const showP = !summary && !early && item.p_board != null && Number.isFinite(item.p_board);
  const p = item.p_board == null ? 0 : pct(item.p_board);

  return (
    <div className={s.card} aria-live="polite" data-testid="result" data-level={item.level}>
      <div data-testid="verdict">
        <Headline tone={tone} text={headline} />
        {summary?.sub && <p className={s.why}>{summary.sub}</p>}
        {showP && <p className={s.why}>예측 탑승 확률 {p}%{v.guide && ` · ${v.guide}`}</p>}
        {early && <p className={s.why}>{whyText(item)}</p>}
      </div>
      {queue
        ? <QueueBar ok={queue.ok} hard={queue.hard} n={n} />
        : showP && <div className={s.track} aria-hidden="true"><div className={s.fill} style={{ width: `${p}%` }} /></div>}
      <NextBus text={next && `못 타면 다음 버스 ${next}`} strong={tone === "bad" || tone === "warn"} />
    </div>
  );
}
