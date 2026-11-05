import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 목업은 요청마다 주소의 ?scenario 를 읽는다. 첫 응답을 받은 뒤 주소만 바꿔 '다음 요청'의 상황을 만든다
const scenario = (page: Page, name: string) =>
  page.evaluate((n) => history.replaceState(null, "", n ? `/?scenario=${n}` : "/"), name);
const chip = (page: Page, n: number) => page.getByRole("button", { name: `${n}명`, exact: true });
const TIME = /\d+분\d+초/;
const PERCENT = /\d+%/;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

// 녹십자약국, 앞 3명. 첫 응답을 받은 뒤 시계를 멈춰 응답 전 화면을 그대로 볼 수 있게 한다
const start = async (page: Page) => {
  await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("verdict")).toContainText(PERCENT);
  await page.clock.pauseAt(new Date("2026-09-30T08:00:30+09:00"));
  await page.clock.runFor(400);  // 시계가 건너뛰며 시작된 자동 새로고침을 마저 끝낸다
};

test.describe("지금 입력한 인원과 다른 확률을 보이지 않는다", () => {
  test("인원을 바꾸면 응답 전까지 확률 대신 계산 중으로 안내한다", async ({ page }) => {
    await start(page);
    await chip(page, 20).click();
    const hero = page.getByTestId("hero");
    await expect(page.getByTestId("verdict")).toHaveText("계산 중");
    await expect(page.getByTestId("result")).toContainText("20명 기준으로 다시 계산하고 있어요");
    await expect(page.getByTestId("result")).not.toContainText(PERCENT);
    await expect(hero).toHaveAttribute("data-tone", "hold");
    await expect(page.getByTestId("other-sb02-30")).toContainText("계산 중");
    await expect(page.getByTestId("other-sb02-30")).not.toContainText(PERCENT);
    // 도착 시간과 차내 인원은 인원과 무관해서 그대로 보인다
    await expect(page.getByTestId("arrival")).toContainText(TIME);
    await expect(page.getByTestId("loads")).toContainText(/\d+명/);

    await page.clock.runFor(700);
    await expect(hero).toHaveAttribute("data-level", "어려울 수 있음");
    await expect(page.getByTestId("verdict")).toContainText(PERCENT);
    await expect(page.getByTestId("other-sb02-30")).toContainText(/탑승 확률 \d+%|확률 보류|판단하기 일러요/);
  });

  test("인원을 바꾼 요청이 실패하면 확률을 못 받았다고 안내하고 다시 시도할 수 있다", async ({ page }) => {
    await start(page);
    await scenario(page, "down");
    await chip(page, 20).click();
    await page.clock.runFor(700);
    await expect(page.getByTestId("verdict")).toHaveText("확률 보류");
    await expect(page.getByTestId("result")).toContainText("20명 기준 확률을 못 받았어요");
    await expect(page.getByTestId("result")).not.toContainText(PERCENT);
    await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "hold");
    await expect(page.getByTestId("other-sb02-30")).not.toContainText(PERCENT);
    await expect(page.getByTestId("arrival")).toContainText(TIME);
    await expect(page.getByText("연결이 불안정해요")).toBeVisible();

    await scenario(page, "");
    await page.getByTestId("result-retry").click();
    await expect(page.getByTestId("verdict")).toHaveText("계산 중");
    await page.clock.runFor(700);
    await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "어려울 수 있음");
    await expect(page.getByTestId("verdict")).toContainText(PERCENT);
  });

  test("실패한 뒤 서버가 살아나면 버튼 없이 60초 안에 새 인원의 확률로 돌아온다", async ({ page }) => {
    await start(page);
    await scenario(page, "down");
    await chip(page, 20).click();
    await page.clock.runFor(700);
    await expect(page.getByTestId("result")).toContainText("20명 기준 확률을 못 받았어요");
    await scenario(page, "");
    await page.clock.runFor(61_000);
    await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "어려울 수 있음");
  });

  test("인원이 그대로인 새로고침이 실패하면 확률은 두고 상태 줄로만 알린다", async ({ page }) => {
    await start(page);
    await scenario(page, "down");
    await page.getByTestId("refresh").click();
    await page.clock.runFor(700);
    await expect(page.getByTestId("verdict")).toContainText(PERCENT);
    await expect(page.getByText("연결이 불안정해요")).toBeVisible();
    await expect(page.getByTestId("result-retry")).toHaveCount(0);
  });

  test("입력이 잘못되면 다른 정류장 뱃지에도 이전 확률이 남지 않는다", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("stop-sb02-32").click();
    await expect(page.getByTestId("other-sb02-30")).toContainText(PERCENT);
    await page.getByTestId("n-input").fill("41");
    await expect(page.getByTestId("other-sb02-30")).toContainText("확률 보류");
    await expect(page.getByTestId("other-sb02-30")).not.toContainText(PERCENT);
    await page.getByTestId("tab-1").click();
    await expect(page.getByTestId("card-sb02-31")).not.toContainText(PERCENT);
    await page.getByTestId("tab-0").click();
    await page.getByTestId("n-input").fill("3");
    await expect(page.getByTestId("other-sb02-30")).toContainText(PERCENT);
  });

  // 누르던 버튼이 손 밑에서 밀리지 않게
  for (const [width, height] of [[320, 568], [360, 640], [360, 780], [375, 812], [412, 915]] as [number, number][]) {
    test(`${width}x${height}: 계산 중·실패에도 대기 인원 버튼 위치가 같다`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await start(page);
      const y = async () => (await page.getByTestId("n-minus").boundingBox())!.y;
      const normal = await y();
      await scenario(page, "down");
      await chip(page, 20).click();
      await expect(page.getByTestId("verdict")).toHaveText("계산 중");
      expect(Math.abs(await y() - normal)).toBeLessThanOrEqual(1);
      await page.clock.runFor(700);
      await expect(page.getByTestId("result")).toContainText("확률을 못 받았어요");
      expect(Math.abs(await y() - normal)).toBeLessThanOrEqual(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
});

test.describe("응답이 오래 걸릴 때", () => {
  test("3초가 넘으면 기다리는 중임을 알리고 도착 시간과 입력은 계속 쓸 수 있다", async ({ page }) => {
    await start(page);
    await scenario(page, "slow");
    await chip(page, 20).click();
    await page.clock.runFor(1_000);
    await expect(page.getByTestId("result")).toContainText("20명 기준으로 다시 계산");
    await expect(page.getByTestId("result")).not.toContainText("오래 걸리고");
    await page.clock.runFor(3_600);
    await expect(page.getByTestId("result")).toContainText("오래 걸리고");
    await expect(page.getByText("응답이 늦어지고 있어요")).toBeVisible();
    await expect(page.getByTestId("result")).not.toContainText(PERCENT);
    await expect(page.getByTestId("arrival")).toContainText(TIME);
    await expect(page.getByTestId("n-input")).toBeEditable();
  });

  test("끝내 응답이 없으면 확률을 못 받았다고 바꿔 안내한다", async ({ page }) => {
    await start(page);
    await scenario(page, "slow");
    await chip(page, 20).click();
    await page.clock.runFor(9_500);
    await expect(page.getByTestId("result")).toContainText("20명 기준 확률을 못 받았어요");
    await expect(page.getByTestId("result")).not.toContainText("오래 걸리고");
  });

  test("첫 불러오기가 길면 안내하고, 끝내 안 오면 사용자 탓을 하지 않는다", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
    await page.goto("/?scenario=slow");
    await page.getByTestId("stop-sb02-32").click();
    await expect(page.getByTestId("hero-skeleton")).toBeVisible();
    await expect(page.getByTestId("slow-note")).toHaveCount(0);
    await page.clock.runFor(4_500);
    await expect(page.getByTestId("slow-note")).toBeVisible();
    await page.clock.runFor(6_000);
    const notice = page.getByTestId("notice-timeout");
    await expect(notice).toContainText("응답이 늦어지고 있어요");
    await expect(notice).not.toContainText("네트워크");
  });

  for (const [width, height] of [[320, 568], [360, 640], [412, 915]] as [number, number][]) {
    test(`${width}x${height}: 오래 걸린다는 안내가 나와도 대기 인원 버튼 위치가 같다`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await start(page);
      const y = async () => (await page.getByTestId("n-minus").boundingBox())!.y;
      const normal = await y();
      await scenario(page, "slow");
      await chip(page, 20).click();
      await page.clock.runFor(4_600);
      await expect(page.getByTestId("result")).toContainText("오래 걸리고");
      expect(Math.abs(await y() - normal)).toBeLessThanOrEqual(1);
    });
  }
});
