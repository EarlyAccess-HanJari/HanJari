import s from "./HeroSkeleton.module.css";

/** 첫 조회 전 자리 표시 — 도착·결과 카드와 같은 높이라 응답이 와도 화면이 밀리지 않음 */
export default function HeroSkeleton() {
  return (
    <div className={s.wrap} aria-busy="true" data-testid="skeleton">
      <span className={s.sr}>버스 정보를 불러오는 중…</span>
      <div className={s.arrival} aria-hidden="true">
        <span className={`${s.bar} ${s.w30}`} />
        <span className={`${s.bar} ${s.big}`} />
        <span className={`${s.bar} ${s.w60}`} />
      </div>
      <div className={s.result} aria-hidden="true">
        <span className={`${s.bar} ${s.head}`} />
        <span className={`${s.bar} ${s.track}`} />
        <span className={`${s.bar} ${s.w80}`} />
        <span className={`${s.bar} ${s.w50}`} />
      </div>
    </div>
  );
}
