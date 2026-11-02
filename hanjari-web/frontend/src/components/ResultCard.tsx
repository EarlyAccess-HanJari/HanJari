import type { Level, PredictItem } from "../types";
import { pct, whyText } from "../utils/format";
import { LEVEL_CLASS } from "./LevelBadge";
import lv from "./levels.module.css";
import s from "./ResultCard.module.css";

const GUIDE: Record<Level, string> = {
  "여유 있음": "이번 버스 기다리셔도 좋아요.",
  "빠듯함": "탈 수도 있지만 장담하긴 어려워요.",
  "어려울 수 있음": "이번 버스는 타기 힘들어요.",
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
        <div className={s.head}><span className={s.title}><span className={s.dot} />인원을 확인해 주세요</span></div>
        <p className={s.why}>올바른 인원을 넣으면 바로 다시 계산해요.</p>
      </section>
    );
  }

  // F-04: 보류·판단 이른 단계에선 확률·예상 인원을 숨긴다
  const showP = item.level !== "확률 보류" && item.level !== "판단하기 일러요" && item.p_board != null && Number.isFinite(item.p_board);
  const p = item.p_board == null ? null : pct(item.p_board);
  return (
    <section className={`${s.card} ${LEVEL_CLASS[item.level]}`} aria-live="polite" aria-busy={busy}
      data-testid="result" data-level={item.level}>
      {/* 다시 계산하는 동안 확률 자리에만 표시 — 줄이 늘지 않아 아래 입력칸이 밀리지 않게 */}
      {busy && showP && <span className={s.recalc}>다시 계산 중…</span>}
      {/* 확률이 있으면 '탑승 가능성 98%' 한 줄로. 단계는 색(점·배경·진행바)으로만 구분 */}
      <div className={s.head}>
        <span className={s.title}>
          <span className={s.dot} />
          {showP ? <>탑승 가능성 <span style={busy ? { visibility: "hidden" } : undefined}>{p}%</span></> : item.level}
        </span>
      </div>
      {showP && (
        <div className={s.track} aria-hidden="true"><div className={s.fill} style={{ width: `${p}%` }} /></div>
      )}
      <p className={s.guide}>{GUIDE[item.level]}</p>
      {!showP && <p className={s.why}>{whyText(item)}</p>}
    </section>
  );
}
