import { useEffect, useRef, useState } from "react";
import s from "./InstallApp.module.css";

interface InstallPrompt extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/** 운영에 설치되어 있던 홈 화면 추가 기능을 새 배포에도 유지한다. */
export default function InstallApp() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [installed, setInstalled] = useState(() => matchMedia("(display-mode: standalone)").matches || !!(navigator as Navigator & { standalone?: boolean }).standalone);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const kakao = /KAKAOTALK/i.test(navigator.userAgent);
  useEffect(() => {
    const available = (event: Event) => { event.preventDefault(); setPrompt(event as InstallPrompt); };
    const done = () => { setInstalled(true); setPrompt(null); setOpen(false); };
    window.addEventListener("beforeinstallprompt", available);
    window.addEventListener("appinstalled", done);
    return () => {
      window.removeEventListener("beforeinstallprompt", available);
      window.removeEventListener("appinstalled", done);
    };
  }, []);
  useEffect(() => { if (open) dialog.current?.showModal(); else dialog.current?.close(); }, [open]);
  if (installed) return null;
  const install = async () => {
    if (!prompt) { setOpen(true); return; }
    setBusy(true);
    try {
      await prompt.prompt();
      if ((await prompt.userChoice).outcome === "accepted") setInstalled(true);
    } catch { setOpen(true); }
    finally { setPrompt(null); setBusy(false); }
  };
  return <>
    <button type="button" className={s.install} onClick={install} disabled={busy} data-testid="install-app">앱 설치</button>
    <dialog ref={dialog} className={s.dialog} aria-labelledby="install-title" onClose={() => setOpen(false)}>
      <div className={s.head}><h2 id="install-title">한자리를 홈 화면에</h2><button type="button" className={s.close} onClick={() => setOpen(false)} aria-label="설치 안내 닫기">×</button></div>
      <p>홈 화면 아이콘으로 한자리를 바로 열 수 있어요.</p>
      {!window.isSecureContext ? <p>설치하려면 아래 주소에서 열어 주세요.<br /><a href="https://161.33.132.80/">설치 가능한 한자리 열기</a></p>
        : kakao ? <p>카카오톡 메뉴에서 <strong>다른 브라우저로 열기</strong>를 선택해 주세요. {ios ? "Safari" : "Chrome"}에서 다시 앱 설치를 눌러 주세요.</p>
        : ios ? <p>Safari의 <strong>공유 → 홈 화면에 추가</strong>를 선택해 주세요.</p>
        : <p>Chrome 또는 Edge 메뉴에서 <strong>앱 설치</strong> 또는 <strong>홈 화면에 추가</strong>를 선택해 주세요. 설치 항목이 없다면 최신 브라우저에서 열어 주세요.</p>}
      <p className={s.note}>실시간 버스 정보는 인터넷 연결이 필요해요.</p>
    </dialog>
  </>;
}
