import { test, expect } from "@playwright/test";
import fixture from "../src/mock/predict_n3.json" with { type: "json" };
import { isPredictResponse } from "../src/api/contract";

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
  await expect(page.getByTestId("result")).toHaveAttribute("data-level", "확률 보류");
  await expect(page.getByTestId("result")).toContainText("차내 인원 정보를 확인할 수 없어요");
  await expect(page.getByTestId("result")).not.toContainText(/\d+%/);
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

test("first bus change is visible and a new vehicle gets its own countdown", async ({ page }) => {
  test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");
  await page.clock.install({ time: new Date("2026-11-02T17:40:40+09:00") });
  const first = held();
  const row = first.results.find(i => i.route === "jr03" && i.stop === "23")!;
  Object.assign(row, { plate: "서울70사5508", vehicle_id: "100000014", eta_sec: 96, stops_away: 1,
    updated: "17:40:39", updated_at: "2026-11-02T17:40:39+09:00" });
  const second = structuredClone(first);
  Object.assign(second.results.find(i => i.route === "jr03" && i.stop === "23")!, {
    plate: "서울75사3170", vehicle_id: "100000069", eta_sec: 108,
  });
  let response = first;
  await page.route("**/api/predict?*", r => r.fulfill({ json: response }));
  await page.goto("/");
  await page.getByTestId("stop-jr03-23").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("vehicle")).toContainText("서울70사5508");
  await expect(page.getByTestId("vehicle-changed")).not.toBeVisible();
  response = second;
  await page.getByTestId("refresh").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("vehicle")).toContainText("서울75사3170");
  await expect(page.getByTestId("vehicle-changed")).toContainText("서울70사5508 → 서울75사3170");
  // 12초 차이여도 다른 차량이면 이전 도착 시간을 이어 쓰지 않는다.
  await expect(page.getByTestId("arrival")).toContainText(/1분4[45]초/);
  await page.getByTestId("refresh").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("vehicle-changed")).toContainText("서울70사5508 → 서울75사3170");
  await page.getByTestId("card-jr03-20").click();
  await expect(page.getByTestId("vehicle-changed")).not.toBeVisible();
});
