import { test, expect } from "@playwright/test";
import fixture from "../src/mock/predict_n3.json" with { type: "json" };
import { isPredictResponse } from "../src/api/contract";

// 응답 주입 검사는 page.route를 거친다. 실제 SW 통신은 배포 스모크에서 별도로 확인한다.
test.use({ serviceWorkers: "block" });

const held = () => ({
  n_ahead: 3,
  results: fixture.results.map(i => ({ ...i, r_now: null, load_pred: null, load_10: null, load_90: null,
    p_board: null, level: "확률 보류", data_status: "passenger_unavailable",
    prediction_status: "passenger_unavailable", arrival_stale: false,
    reason: "차내 인원 정보를 확인할 수 없어요" })),
});

test("contract rejects malformed or misleading prediction values", () => {
  expect(isPredictResponse(fixture)).toBe(true);
  expect(isPredictResponse(held())).toBe(true);
  for (const change of [{ p_board: null }, { p_board: 1.2 }, { r_now: -1 }, { load_pred: NaN },
    { eta_sec: "60" }, { updated: "26:00:00" }, { load_10: 50, load_90: 10 }, { arrival_stale: true }]) {
    const bad = structuredClone(fixture);
    Object.assign(bad.results[0], change);
    expect(isPredictResponse(bad)).toBe(false);
  }
  const badHold = held();
  Object.assign(badHold.results[0], { p_board: 0.98 });
  expect(isPredictResponse(badHold)).toBe(false);
  expect(isPredictResponse({ results: [] })).toBe(false);
});

// 이 파일의 브라우저 검사는 VITE_MOCK=0으로 실행하여 실제 fetch/응답 검증을 거친다.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

test("null count holds prediction while keeping arrival", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.route("**/api/predict?*", r => r.fulfill({ json: held() }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("loads")).toContainText("현재 인원 정보를 확인할 수 없어요");
  await expect(page.getByTestId("result")).toHaveCount(0);
  await expect(page.getByTestId("loads")).not.toContainText(/\d|null|NaN/);
  await expect(page.getByTestId("arrival")).not.toContainText("버스 위치를 확인할 수 없어요");
});

test("explicit stale status suppresses arrival without parsing reason text", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  const body = held();
  for (const i of body.results) Object.assign(i, { arrival_stale: true, data_status: "source_stale", prediction_status: "source_stale", reason: "버스 정보가 오래되어 갱신을 기다리고 있어요" });
  await page.route("**/api/predict?*", r => r.fulfill({ json: body }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("notice-stale")).toBeVisible();
  await expect(page.getByTestId("arrival")).toContainText("버스 위치를 확인할 수 없어요");
});

test("invalid API payload shows error instead of 0 passengers or percentage", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  const body = structuredClone(fixture);
  Object.assign(body.results[0], { load_pred: null });
  await page.route("**/api/predict?*", r => r.fulfill({ json: body }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("notice-unknown")).toContainText("버스 정보를 확인할 수 없어요");
  await expect(page.getByTestId("result")).not.toBeVisible();
});

test("recorded first bus switch appears automatically within five seconds", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.clock.install({ time: new Date("2026-11-02T17:41:56+09:00") });
  const first = structuredClone(fixture);
  const row = first.results.find(i => i.route === "jr03" && i.stop === "23")!;
  Object.assign(row, { plate: "서울70사5508", vehicle_id: "100000014", r_now: 54,
    eta_sec: 62, stops_away: 0, updated: "17:41:33", updated_at: "2026-11-02T17:41:33+09:00",
    source_updated: "2026-11-02 17:41:08.0", arrival_at: "2026-11-02T17:42:10+09:00" });
  const second = structuredClone(first);
  Object.assign(second.results.find(i => i.route === "jr03" && i.stop === "23")!, {
    plate: "서울75사3170", vehicle_id: "100000069", r_now: 22, eta_sec: 53,
    updated: "17:42:00", updated_at: "2026-11-02T17:42:00+09:00",
    source_updated: "2026-11-02 17:41:54.0", arrival_at: "2026-11-02T17:42:47+09:00",
  });
  let response = first;
  let requests = 0;
  await page.route("**/api/predict?*", r => { requests++; return r.fulfill({ json: response }); });
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("loads")).toContainText("54명");
  response = second;
  await page.clock.runFor(5_000);
  await expect(page.getByTestId("loads")).toContainText("22명");
  await expect(page.getByTestId("loads")).not.toContainText("54명");
  expect(requests).toBeGreaterThan(1);
  await expect(page.getByTestId("vehicle")).toHaveCount(0);
  response = first; // 늦게 도착한 옛 스냅샷으로 앞차가 다시 살아나면 안 된다.
  await page.clock.runFor(5_000);
  await expect(page.getByTestId("loads")).toContainText("22명");
  await expect(page.getByTestId("loads")).not.toContainText("54명");
});

test("source time anchors ETA and expired same response never revives the old bus", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.clock.install({ time: new Date("2026-11-02T17:40:40+09:00") });
  const body = structuredClone(fixture);
  Object.assign(body.results.find(i => i.route === "jr03" && i.stop === "23")!, {
    r_now: 53, eta_sec: 96, stops_away: 1, updated: "17:40:39", updated_at: "2026-11-02T17:40:39+09:00",
    source_updated: "2026-11-02 17:40:14.0", arrival_at: "2026-11-02T17:41:50+09:00",
  });
  await page.route("**/api/predict?*", r => r.fulfill({ json: body }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분0[6-9]초/);
  await expect(page.getByText("버스 정보 17:40:14 기준")).toBeVisible();
  await page.clock.runFor(70_000);
  await expect(page.getByTestId("arrival-checking")).toBeVisible();
  await expect(page.getByTestId("arrival")).not.toContainText("곧 도착");
  await expect(page.getByTestId("loads")).not.toContainText("53명");
  await expect(page.getByTestId("result")).toHaveCount(0);
  await page.clock.runFor(10_000); // 같은 스냅샷을 다시 받아도 만료 상태 유지
  await expect(page.getByTestId("arrival-checking")).toBeVisible();
});

test("temporarily missing stop resumes automatically when the next bus appears", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.clock.install({ time: new Date("2026-11-02T17:42:00+09:00") });
  const full = held();
  let response = { ...full, results: full.results.filter(i => i.route !== "jr03" || i.stop !== "23") };
  await page.route("**/api/predict?*", r => r.fulfill({ json: response }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("notice-no_stop")).toBeVisible();
  response = full;
  await page.clock.runFor(5_000);
  await expect(page.getByTestId("arrival")).toBeVisible();
  await expect(page.getByTestId("notice-no_stop")).toHaveCount(0);
});

test("response ages on screen even when the tab stops refreshing", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.clock.install({ time: new Date("2026-11-02T17:40:40+09:00") });
  await page.addInitScript(() => Object.defineProperty(document, "visibilityState", { get: () => "hidden" }));
  const body = structuredClone(fixture);
  Object.assign(body.results.find(i => i.route === "jr03" && i.stop === "23")!, {
    eta_sec: 600, stops_away: 5, updated: "17:40:39", updated_at: "2026-11-02T17:40:39+09:00",
    source_updated: "2026-11-02 17:40:14.0", arrival_at: "2026-11-02T17:50:14+09:00",
  });
  await page.route("**/api/predict?*", r => r.fulfill({ json: body }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("notice-stale")).toHaveCount(0);
  await page.clock.runFor(155_000);
  await expect(page.getByTestId("notice-stale")).toBeVisible();
  await expect(page.getByTestId("result")).toHaveCount(0);
});

test("a new vehicle and a corrected ETA take effect without fifteen-second smoothing", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.clock.install({ time: new Date("2026-11-02T17:40:40+09:00") });
  const body = held();
  const row = body.results.find(i => i.route === "jr03" && i.stop === "23")!;
  Object.assign(row, { plate: "서울70사5508", vehicle_id: "100000014", eta_sec: 96, stops_away: 1,
    updated: "17:40:39", updated_at: "2026-11-02T17:40:39+09:00" });
  await page.route("**/api/predict?*", r => r.fulfill({ json: body }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await page.clock.runFor(1_000);
  Object.assign(row, { plate: "서울75사3170", vehicle_id: "100000069", eta_sec: 108 });
  await page.getByTestId("refresh").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분4[45]초/);
});

test("fresh estimated count remains visible while boarding prediction is held", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  const body = held();
  for (const item of body.results) Object.assign(item, { r_now: 22, data_status: "ok",
    prediction_status: "field_validation_pending", reason: "탑승 예측을 점검하고 있어요" });
  await page.route("**/api/predict?*", r => r.fulfill({ json: body }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("loads")).toContainText("약 22명");
  await expect(page.getByTestId("loads")).toContainText("추정");
  await expect(page.getByTestId("result")).toHaveCount(0);
});

test("empty upstream outage is not called end of service and recovers automatically", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.clock.install({ time: new Date("2026-11-02T17:42:00+09:00") });
  let response: unknown = { n_ahead: 3, results: [], service: { mode: "latest", release: "test", data_status: "degraded",
    routes: { jr03: { status: "missing", collected_at: null, age_sec: null } } } };
  await page.route("**/api/predict?*", r => r.fulfill({ json: response }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("notice-data_delayed")).toBeVisible();
  await expect(page.getByTestId("notice-night")).toHaveCount(0);
  response = held();
  await page.clock.runFor(30_000);
  await expect(page.getByTestId("arrival")).toBeVisible();
});

test("installed app entry and install guidance survive the release", async ({ page }) => {
  await page.route("**/api/predict?*", r => r.fulfill({ json: held() }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  await page.getByTestId("install-app").click();
  await expect(page.getByRole("dialog", { name: "한자리를 홈 화면에" })).toBeVisible();
  await page.getByRole("button", { name: "설치 안내 닫기" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("connection restoration immediately refreshes the installed app", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  let requests = 0;
  await page.route("**/api/predict?*", r => { requests++; return r.fulfill({ json: held() }); });
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("arrival")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByTestId("notice-offline")).toBeVisible();
  const before = requests;
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByTestId("arrival")).toBeVisible();
  await expect.poll(() => requests).toBeGreaterThan(before);
});
