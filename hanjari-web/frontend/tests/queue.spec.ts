import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import curve from "../src/mock/predict_curve.json" with { type: "json" };
import fixture from "../src/mock/predict_n3.json" with { type: "json" };
import { isPredictResponse } from "../src/api/contract";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

const open = async (page: Page, scenario: string, stop = "stop-sb02-32") => {
  await page.goto(`/?scenario=${scenario}`);
  await page.getByTestId(stop).click();
};
const chip = (page: Page, n: number) => page.getByRole("button", { name: `${n}명`, exact: true });

test("응답 계약: 줄 길이 필드가 잘못되면 거절하고, 없어도 받는다", () => {
  expect(isPredictResponse(curve)).toBe(true);
  expect(isPredictResponse(fixture)).toBe(true);
  for (const change of [{ p_by_n: [0.5] }, { n_ok: 41 }, { n_ok: 30, n_hard: 10 }, { p_by_n: Array(41).fill(1.2) }]) {
    const bad = structuredClone(curve);
    Object.assign(bad.results[0], change);
    expect(isPredictResponse(bad)).toBe(false);
  }
});

test.describe("줄 길이 막대", () => {
  test.skip(process.env.VITE_MOCK === "0", "목업 시나리오 전용");

  test("입력 없이 몇 명까지 탈 수 있는지 먼저 보여 주고, 고른 적 없는 인원을 가정하지 않는다", async ({ page }) => {
    await open(page, "curve");
    await expect(page.getByTestId("verdict")).toContainText("앞 약 8명까지는 여유 있어요");
    await expect(page.getByTestId("verdict")).toContainText("약 17명이 넘으면 타기 어려워요");
    await expect(page.getByTestId("verdict")).not.toContainText(/\d+%/);
    await expect(page.getByTestId("queue-bar")).toContainText("여유 ~8명");
    await expect(page.getByTestId("queue-bar")).toContainText("빠듯 ~17명");
    await expect(page.getByTestId("queue-bar")).toContainText("어려움 18명~");
    await expect(page.getByTestId("queue-marker")).toHaveCount(0);
    await expect(page.getByTestId("n-input")).toHaveValue("");
    await expect(page.getByTestId("n-hint")).toHaveCount(0);
    await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "ok");
  });

  test("인원을 고르면 기다림 없이 바뀌고, 같은 칩을 다시 누르면 풀린다", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
    await open(page, "curve");
    await page.clock.runFor(1_000);
    await expect(page.getByTestId("queue-bar")).toBeVisible();
    await page.clock.pauseAt(new Date("2026-09-30T08:00:30+09:00"));
    await page.clock.runFor(400);
    await chip(page, 10).click();
    // 시계를 돌리지 않았으니 요청을 기다릴 수 없다. 바로 바뀌어야 한다
    await expect(page.getByTestId("verdict")).toContainText("앞 10명이라면 빠듯해요");
    await expect(page.getByTestId("verdict")).toContainText(/예측 탑승 확률 \d+%/);
    await expect(page.getByTestId("queue-marker")).toBeVisible();
    await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "warn");
    await chip(page, 25).click();
    await expect(page.getByTestId("verdict")).toContainText("앞 25명이라면 타기 어려워요");
    await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "bad");
    await expect(page.getByTestId("next-bus")).toContainText("못 타면 다음 버스");
    await chip(page, 25).click();
    await expect(page.getByTestId("verdict")).toContainText("앞 약 8명까지는 여유 있어요");
    await expect(page.getByTestId("queue-marker")).toHaveCount(0);
  });

  test("직접 입력도 바로 반영되고, 잘못된 입력은 판정을 숨긴다", async ({ page }) => {
    await open(page, "curve");
    await expect(page.getByTestId("queue-bar")).toBeVisible();
    await page.getByTestId("n-input").fill("3");
    await expect(page.getByTestId("verdict")).toContainText("앞 3명이라면 여유 있어요");
    await page.getByTestId("n-input").fill("41");
    await expect(page.getByTestId("n-hint")).toContainText("0~40");
    await expect(page.getByTestId("verdict")).toHaveCount(0);
    await page.getByTestId("n-input").fill("");
    await expect(page.getByTestId("n-hint")).toHaveCount(0);
    await expect(page.getByTestId("verdict")).toContainText("앞 약 8명까지");
  });

  test("정류장을 바꾸면 그 정류장의 구간으로 바뀐다", async ({ page }) => {
    await open(page, "curve");
    await expect(page.getByTestId("verdict")).toContainText("앞 약 8명까지");
    await page.getByTestId("other-sb02-30").click();
    await expect(page.getByTestId("verdict")).toContainText("앞 약 25명까지");
    await expect(page.getByTestId("other-sb02-32")).not.toContainText(/\d+%|확률/);
  });

  test("앞·뒤 정류장 탭의 내 정류장 줄은 인원을 골랐을 때만 확률을 보여 준다", async ({ page }) => {
    await open(page, "curve");
    await expect(page.getByTestId("queue-bar")).toBeVisible();
    await page.getByTestId("tab-1").click();
    await expect(page.getByTestId("card-sb02-32")).not.toContainText(/\d+%/);
    await page.getByTestId("tab-0").click();
    await chip(page, 10).click();
    await page.getByTestId("tab-1").click();
    await expect(page.getByTestId("card-sb02-32")).toContainText(/탑승 확률 \d+%/);
  });

  for (const [width, height] of [[320, 568], [360, 640], [360, 780], [390, 844], [412, 915]] as [number, number][]) {
    test(`${width}x${height}: 인원을 고르거나 풀어도 입력칸이 움직이지 않고 넘치지 않는다`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await open(page, "curve");
      await expect(page.getByTestId("queue-bar")).toBeVisible();
      const y = async () => (await page.getByTestId("n-minus").boundingBox())!.y;
      const before = await y();
      await chip(page, 10).click();
      await expect(page.getByTestId("queue-marker")).toBeVisible();
      expect(Math.abs(await y() - before)).toBeLessThanOrEqual(1);
      await chip(page, 30).click();
      await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "bad");
      expect(Math.abs(await y() - before)).toBeLessThanOrEqual(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(height);
    });
  }
});

test.describe("확률이 없는 상황 안내", () => {
  test.skip(process.env.VITE_MOCK === "0", "목업 시나리오 전용");

  test("버스가 막 지나가면 고장처럼 말하지 않고 다음 버스를 먼저 보여 준다", async ({ page }) => {
    await open(page, "passed");
    await expect(page.getByTestId("verdict")).toContainText("이번 버스가 막 지나간 것 같아요");
    await expect(page.getByTestId("next-bus")).toHaveText("다음 버스 약 12분 후");
    await expect(page.locator("body")).not.toContainText("버스 정보 갱신 중");
  });

  test("일요일·공휴일은 쉬는 날이라고 알려 준다", async ({ page }) => {
    await open(page, "holiday");
    await expect(page.getByTestId("verdict")).toContainText("오늘은 탑승 예측을 쉬어요");
    await expect(page.getByTestId("arrival")).toContainText(/\d+분\d+초|곧 도착/);
    await expect(page.getByTestId("result")).not.toContainText(/\d+%/);
  });

  test("이 버스만 예측이 어려우면 개발 문장 대신 쉬운 말로, 이유는 근거 안내에", async ({ page }) => {
    await open(page, "held");
    await expect(page.getByTestId("verdict")).toContainText("이 버스는 탑승 예측이 어려워요");
    await expect(page.getByTestId("result")).not.toContainText("판단 기준");
    await page.getByTestId("about").click();
    await expect(page.getByTestId("about-reason")).toContainText("판단 기준");
  });

  test("정보가 오래되면 경고를 겹치지 않고 한 번만 말한다", async ({ page }) => {
    await open(page, "stale");
    await expect(page.getByTestId("verdict")).toContainText("버스 정보가 늦어지고 있어요");
    await expect(page.getByTestId("next-bus")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("오래됐어요");
  });

  for (const [width, height] of [[320, 568], [360, 640], [390, 844]] as [number, number][]) {
    test(`${width}x${height}: 상황이 달라도 대기 인원 버튼 위치가 같다`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const ys: Record<string, number> = {};
      for (const scenario of ["", "passed", "holiday", "held", "stale", "checking"]) {
        await page.goto(`/?scenario=${scenario}`);
        await page.evaluate(() => localStorage.setItem("hanjari.sel", JSON.stringify({ route: "sb02", stop: "32" })));
        await page.reload();
        await expect(page.getByTestId("n-minus")).toBeVisible();
        await expect(page.getByTestId("hero-skeleton")).toHaveCount(0);
        ys[scenario || "normal"] = (await page.getByTestId("n-minus").boundingBox())!.y;
      }
      expect(Math.max(...Object.values(ys)) - Math.min(...Object.values(ys))).toBeLessThanOrEqual(1);
    });
  }
});

test.describe("근거 안내", () => {
  test.skip(process.env.VITE_MOCK === "0", "목업 시나리오 전용");

  test("공공데이터와 예측을 나누어 설명하고 닫을 수 있다", async ({ page }) => {
    await open(page, "");
    await expect(page.getByTestId("loads")).toContainText("지금 · 공공데이터");
    await expect(page.getByTestId("loads")).toContainText("도착 때 · 한자리 예측");
    await page.getByTestId("about").click();
    const sheet = page.getByTestId("about-sheet");
    await expect(sheet).toContainText("서울시 버스 정보");
    await expect(sheet).toContainText("실제 탑승과 비교한 결과는 아니에요");
    await expect(sheet).toContainText("빗나갈 수 있어요");
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
  });
});
