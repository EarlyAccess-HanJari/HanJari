import StatusIcon from "./StatusIcon";
import s from "./Notice.module.css";

export type NoticeKind = "offline" | "night" | "no_stop" | "data_delayed" | "server_down" | "timeout" | "bad_input" | "unknown";

export const TEXT: Record<NoticeKind, { title: string; body: string }> = {
  offline:     { title: "인터넷 연결을 확인해 주세요", body: "실시간 버스 정보는 인터넷 연결이 필요해요. 연결되면 최신 정보를 다시 불러올게요." },
  night:       { title: "지금은 버스가 다니지 않아요", body: "운행 시간이 아니라 도착 정보가 없어요. 운행이 시작되면 이 화면에서 바로 보여드릴게요." },
  no_stop:     { title: "이 정류장 버스 정보가 없어요", body: "지금 이 정류장으로 오는 버스 정보가 들어오지 않았어요. 들어오면 자동으로 보여드릴게요." },
  data_delayed: { title: "버스 정보 갱신이 늦어지고 있어요", body: "새 정보가 들어오면 자동으로 보여드릴게요. 지금은 정류장 안내판을 확인해 주세요." },
  server_down: { title: "서버에 연결할 수 없어요",     body: "잠시 뒤 다시 시도해 주세요. 그동안은 정류장 안내판의 도착 정보를 확인해 주세요." },
  timeout:     { title: "응답이 늦어지고 있어요",     body: "잠시 뒤 다시 시도해 주세요. 그동안은 정류장 안내판의 도착 정보를 확인해 주세요." },
  bad_input:   { title: "입력을 확인해 주세요",       body: "" },
  unknown:     { title: "버스 정보를 확인할 수 없어요", body: "잠시 뒤 다시 시도해 주세요. 그동안은 정류장 안내판의 도착 정보를 확인해 주세요." },
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
      <StatusIcon kind={kind} size={36} />
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
