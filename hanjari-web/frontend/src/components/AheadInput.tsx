import { N_MAX, N_MIN } from "../types";
import s from "./AheadInput.module.css";

interface Props {
  raw: string;
  n: number | null;        // raw 가 올바를 때만 숫자
  error: string | null;
  optional?: boolean;      // 줄 길이 막대가 있으면 입력은 선택 사항. 같은 칩을 다시 누르면 선택이 풀린다
  onChange: (raw: string) => void;
}

const QUICK = [0, 3, 5, 10, 15, 20];
const QUICK_OPTIONAL = [5, 10, 15, 20, 25, 30];  // 막대와 비교하는 용도라 더 긴 줄까지

export default function AheadInput({ raw, n, error, optional = false, onChange }: Props) {
  const cur = n ?? 0;
  const set = (v: number) => onChange(String(Math.min(N_MAX, Math.max(N_MIN, v))));
  return (
    <section className={s.wrap}>
      <div className={s.row}>
        <div className={s.labelCol}>
          {/* 정류장의 전체 인파가 아니라 이 버스 줄에서 내 앞만 세야 확률이 맞다 */}
          <label htmlFor="n-ahead" className={s.label}>이 버스 줄, 내 앞 사람{optional && " (선택)"}</label>
          <div className={`${s.field} ${error ? s.fieldError : ""}`}>
            <input id="n-ahead" className={s.input} type="text" inputMode="numeric" autoComplete="off" placeholder="몇"
              style={{ width: raw ? `${raw.length}ch` : "1.4em" }}
              value={raw} onChange={(e) => onChange(e.target.value)}
              aria-invalid={!!error} aria-describedby={error ? "n-hint" : undefined} data-testid="n-input" />
            <span className={s.unit}>명</span>
          </div>
        </div>
        <div className={s.stepper}>
          <button type="button" className={s.step} onClick={() => set(cur - 1)} disabled={n === N_MIN}
            aria-label="1명 줄이기" data-testid="n-minus">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M5 12h14" /></svg>
          </button>
          <button type="button" className={s.step} onClick={() => set(cur + 1)} disabled={n === N_MAX}
            aria-label="1명 늘리기" data-testid="n-plus">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          </button>
        </div>
      </div>
      <div className={s.quick} role="group" aria-label="빠른 선택">
        {(optional ? QUICK_OPTIONAL : QUICK).map((v) => (
          <button key={v} type="button" className={`${s.chip} ${n === v ? s.chipOn : ""}`}
            aria-pressed={n === v} aria-label={`${v}명`} onClick={() => (optional && n === v ? onChange("") : set(v))}>{v}명</button>
        ))}
      </div>
      {error && <p id="n-hint" className={s.error} role="alert" data-testid="n-hint">{error}</p>}
    </section>
  );
}
