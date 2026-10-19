/** 창 하나(노랑)만 빈 버스 = '한 자리'. public/favicon.svg 와 같은 그림 */
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <rect width="100" height="100" rx="24" fill="#1D4F91" />
      <rect x="12" y="26" width="76" height="44" rx="13" fill="#FFFFFF" />
      <rect x="21" y="35" width="16" height="17" rx="4" fill="#B9CCE8" />
      <rect x="42" y="35" width="16" height="17" rx="4" fill="#B9CCE8" />
      <rect x="63" y="35" width="16" height="17" rx="4" fill="#FFC23D" />
      <circle cx="31" cy="71" r="8" fill="#0E2A52" stroke="#1D4F91" strokeWidth="4" />
      <circle cx="69" cy="71" r="8" fill="#0E2A52" stroke="#1D4F91" strokeWidth="4" />
    </svg>
  );
}
