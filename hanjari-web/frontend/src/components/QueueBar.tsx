import { N_MAX } from "../types";
import s from "./QueueBar.module.css";

interface Props {
  ok: number | null;    // '여유 있음'이 유지되는 앞 인원 상한
  hard: number | null;  // 탈 수 있는(빠듯함까지) 앞 인원 상한
  n: number | null;     // 내 앞 인원을 골랐으면 그 자리에 표시
}

/** 게이지의 가로축이 확률이 아니라 사람 수다. 줄을 눈으로 보고 막대와 비교하면 세지 않아도 판단할 수 있다.
 *  색만으로 구분하지 않도록 아래에 구간을 글자로도 적는다 */
export default function QueueBar({ ok, hard, n }: Props) {
  const total = N_MAX + 1;
  const okLen = ok === null ? 0 : ok + 1;
  const warnLen = hard === null ? 0 : hard - (ok ?? -1);
  const badLen = N_MAX - (hard ?? -1);
  const parts = [
    ok !== null && `여유 ${ok}명까지`,
    warnLen > 0 && `빠듯 ${hard}명까지`,
    badLen > 0 && `어려움 ${(hard ?? -1) + 1}명부터`,
  ].filter(Boolean).join(", ");
  return (
    <div className={s.wrap} data-testid="queue-bar">
      <div className={s.track}>
        {n !== null && <span className={s.marker} style={{ left: `${((n + 0.5) / total) * 100}%` }} data-testid="queue-marker" aria-hidden="true" />}
        <div className={s.bar} role="img" aria-label={`앞 사람 수별 탑승 판정. ${parts}`}>
          {okLen > 0 && <span className={`${s.seg} ${s.ok}`} style={{ flexGrow: okLen }} />}
          {warnLen > 0 && <span className={`${s.seg} ${s.warn}`} style={{ flexGrow: warnLen }} />}
          {badLen > 0 && <span className={`${s.seg} ${s.bad}`} style={{ flexGrow: badLen }} />}
        </div>
      </div>
      <p className={s.legend}>
        {ok !== null && <span><i className={s.ok} />여유 ~{ok}명</span>}
        {warnLen > 0 && <span><i className={s.warn} />빠듯 ~{hard}명</span>}
        {badLen > 0 && <span><i className={s.bad} />어려움 {(hard ?? -1) + 1}명~</span>}
      </p>
    </div>
  );
}
