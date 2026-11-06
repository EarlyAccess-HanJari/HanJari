import { useEffect, useRef } from "react";
import { reasonText } from "../utils/format";
import sheet from "./StopSheet.module.css";
import s from "./AboutSheet.module.css";

// 2026-11-05 운영 모델 기록: API 재생 MAE 2.58명, 현재 승객 수 기준 4.34명. 정답도 API 인원이라 실제 탑승 성능은 아니다.
// 현장 기록(11/9~13) 결과가 나오면 여기에 함께 적는다
const ACCURACY = "지금 인원을 그대로 쓰면 평균 4.3명, 예측은 평균 2.6명 틀려요. 2026년 11월 4일 자료를 서울시 버스 정보의 인원과 비교한 값이에요. 실제 탑승과 비교한 결과는 아니에요.";

/** 서울시 정보와 예측을 나누어 설명한다. reason: 지금 확률이 보류된 경우 서버가 알려 준 이유 */
export default function AboutSheet({ reason, onClose }: { reason?: string; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);

  return (
    <div className={sheet.backdrop} onClick={onClose}>
      <div ref={ref} className={sheet.sheet} role="dialog" aria-modal="true" aria-labelledby="about-title" tabIndex={-1}
        onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.key === "Escape" && onClose()} data-testid="about-sheet">
        <div className={sheet.head}>
          <h2 id="about-title" className={sheet.title}>이 안내는 어떻게 나왔나요</h2>
          <button type="button" className={sheet.close} onClick={onClose} aria-label="닫기">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12" /><path d="M18 6L6 18" /></svg>
          </button>
        </div>
        <section className={s.item}>
          <h3 className={s.h}>서울시 제공</h3>
          <p className={s.p}>도착 시간과 지금 인원은 서울시 버스 정보예요. 인원은 실제로 세어 본 값이 아니라 교통카드 태그로 집계한 값이에요. 태그 없이 내린 사람이 남아 평소 1~3명쯤 다를 수 있어요.</p>
        </section>
        <section className={s.item}>
          <h3 className={s.h}>한자리 예측</h3>
          <p className={s.p}>도착 때 버스 안 인원과 앞 사람 수별 탈 가능성은 그동안 모은 버스 기록과 시간대, 수업 시간표로 예측한 값이에요. 도착 때 인원은 가장 그럴듯한 값이라 실제로는 더 많거나 적을 수 있어요. "10번 중 몇 번"은 그 오차까지 따져서 계산한 값이에요.</p>
          <p className={s.p}>버스 안 인원은 정류장을 출발할 때 실제 탑승 기록으로 바뀌어요. 그래서 버스가 바로 전 정류장을 출발하면 도착 때 인원이 거의 정해지고, 그 전에는 아직 더 탈 수 있어요.</p>
          <p className={s.p}>탈 수 있는지는 버스마다 탈 수 있는 인원과 이 정류장에서 평소 내리는 사람까지 따져서 계산해요. 그래서 같은 인원이어도 정류장과 버스에 따라 결과가 달라요. 탈 수 있는 인원도 버스 기록으로 추정한 값이에요.</p>
        </section>
        <section className={s.item}>
          <h3 className={s.h}>얼마나 맞나요</h3>
          <p className={s.p}>{ACCURACY}</p>
        </section>
        <section className={s.item}>
          <h3 className={s.h}>못 맞추는 경우</h3>
          <p className={s.p}>행사나 갑자기 화제가 된 곳처럼 평소와 다르게 사람이 몰리면 빗나갈 수 있어요.</p>
        </section>
        {reason && (
          <section className={s.item}>
            <h3 className={s.h}>지금 확률이 안 나오는 이유</h3>
            <p className={s.p} data-testid="about-reason">{reasonText(reason)}</p>
          </section>
        )}
      </div>
    </div>
  );
}
