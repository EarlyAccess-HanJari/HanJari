import { test, expect } from "@playwright/test";
import { arrivalAt } from "../src/utils/format";
import sample from "../src/mock/predict_n3.json" with { type: "json" };
import type { PredictItem } from "../src/types";

const item = sample.results[2] as PredictItem;
const timestamp = (clock: string) => Date.parse(`2026-09-30T${clock}+09:00`);

test("같은 스냅샷의 도착 예정 시각은 수신 시각과 무관하게 일정하다", () => {
  const expected = timestamp("13:13:13");
  expect(arrivalAt(item, timestamp("13:11:43"))).toBe(expected);
  expect(arrivalAt(item, timestamp("13:12:13"))).toBe(expected);
});

test("스냅샷 나이 180초까지 보정하고 181초부터 수신 시각으로 계산한다", () => {
  expect(arrivalAt(item, timestamp("13:14:33"))).toBe(timestamp("13:13:13"));
  const received = timestamp("13:14:34");
  expect(arrivalAt(item, received)).toBe(received + item.eta_sec * 1000);
});

test("미래 또는 잘못된 스냅샷 시각은 수신 시각으로 계산한다", () => {
  const received = timestamp("13:11:23");
  expect(arrivalAt(item, received)).toBe(received + item.eta_sec * 1000);
  expect(arrivalAt({ ...item, updated: "invalid" }, received)).toBe(received + item.eta_sec * 1000);
});

test("자정을 넘긴 KST 스냅샷도 정상 계산한다", () => {
  const received = timestamp("00:00:10");
  expect(arrivalAt({ ...item, updated: "23:59:50", eta_sec: 100 }, received)).toBe(received + 80_000);
});

test("같은 버스의 작은 도착 예정 변동은 유지한다", async ({ page }) => {
  // 오래된 목업은 수신 시각 기준이므로, 재조회 간격만큼의 예정 시각 변동을 재현한다.
  await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await page.clock.runFor(1000);
  await page.clock.runFor(10_000);
  await page.getByTestId("refresh").click();
  await page.clock.runFor(1000);
  await expect(page.getByTestId("arrival")).toContainText(/1분2[78]초/);
});

test("15초를 넘는 예정 시각 변동은 점프 없이 천천히 따라간다", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await page.clock.runFor(1000);
  await page.clock.runFor(20_000);
  await page.getByTestId("refresh").click();
  await page.clock.runFor(1000);
  // 서버는 100초(1분40초)라 하지만 화면은 뒤로 늘지 않고 약 1분20초 근처에서 느리게 흐른다
  await expect(page.getByTestId("arrival")).toContainText(/1분(19|20)초/);
  await page.clock.runFor(10_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분1\d초/);  // 10초 동안 5초만 줄어듦(느리게 보정 중), 점프·역주행 없음
});

test("서버가 arrival_at 을 주면 그 시각을 그대로 쓴다", () => {
  const at = "2026-09-30T13:13:00+09:00";
  expect(arrivalAt({ ...item, arrival_at: at }, timestamp("13:11:43"))).toBe(Date.parse(at));
});
