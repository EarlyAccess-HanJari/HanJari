import s from "./Notice.module.css";

export type NoticeKind = "night" | "no_stop" | "server_down" | "timeout" | "bad_input" | "unknown";

const TEXT: Record<NoticeKind, { title: string; body: string }> = {
  night:       { title: "지금은 버스가 다니지 않아요", body: "새벽 시간이라 도착 정보가 없어요. 운행이 시작되면 이 화면에서 바로 보여드릴게요." },
  no_stop:     { title: "이 정류장 버스 정보가 없어요", body: "잠시 뒤 다시 확인해 주세요." },
  server_down: { title: "서버에 연결할 수 없어요",     body: "잠시 뒤 다시 시도해 주세요. 그동안은 정류장 안내판의 도착 정보를 확인해 주세요." },
  timeout:     { title: "응답이 너무 느려요",         body: "네트워크 상태를 확인하고 다시 시도해 주세요." },
  bad_input:   { title: "입력을 확인해 주세요",       body: "" },
  unknown:     { title: "문제가 생겼어요",            body: "" },
};

interface Props {
  kind: NoticeKind;
  detail?: string;
  onRetry?: () => void;
  retrying?: boolean;
}

export default function Notice({ kind, detail, onRetry, retrying = false }: Props) {
  const t = TEXT[kind];
  return (
    <section className={s.box} role="status" data-testid={`notice-${kind}`}>
      {kind === "night" ? (
        <svg className={s.icon} viewBox="0 0 24 24" fill="none" stroke="#34414F" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
        </svg>
      ) : (
        <svg className={s.icon} viewBox="0 0 24 24" fill="none" stroke="#8E1F17" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 3l18 18" /><path d="M8.5 16.5a5 5 0 0 1 7 0" /><path d="M5 12.5a10 10 0 0 1 4-2.3" /><path d="M14.5 10.3a10 10 0 0 1 4.5 2.2" /><path d="M12 20h.01" />
        </svg>
      )}
      <h2 className={s.title}>{t.title}</h2>
      {t.body && <p className={s.body}>{t.body}</p>}
      {detail && <p className={s.detail}>{detail}</p>}
      {onRetry && (
        <button type="button" className={s.btn} onClick={onRetry} disabled={retrying}>
          {retrying ? "다시 연결하는 중…" : "다시 시도"}
        </button>
      )}
    </section>
  );
}
