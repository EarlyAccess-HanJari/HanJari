import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 시나리오를 연달아 돌릴 때 '마지막 정류장 기억' 때문에 시트를 건너뛰지 않도록
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

const run = async (page: Page, scenario: string) => {
  await page.goto(`/?scenario=${scenario}`);
  await page.getByTestId("stop-sb02-32").click();               // 녹십자약국, 앞 3명(기본값)
};

test("stale: '확률 보류' → 오래됨 안내 + 확률·도착 시간 숨김", async ({ page }) => {
  await run(page, "stale");
  await expect(page.getByTestId("notice-stale")).toBeVisible();
  const result = page.getByTestId("result");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "확률 보류");
  await expect(result).not.toContainText(/\d+%/);
  await expect(page.getByTestId("loads")).not.toContainText(/\d/);
  await expect(result).toContainText("95분 전");                 // 보류 이유 노출
  // 오래된 정보면 도착 시간·정류장 수 대신 안내만 (몇 시간 전 버스를 카운트다운하지 않게)
  await expect(page.getByTestId("arrival")).toContainText("버스 위치를 확인할 수 없어요");
  await expect(page.getByTestId("arrival")).not.toContainText("바로 앞 정류장");
});

test("wide: '판단하기 일러요' → 확률 대신 예상 범위 안내", async ({ page }) => {
  await run(page, "wide");
  const result = page.getByTestId("result");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "판단하기 일러요");
  await expect(result).not.toContainText(/\d+%/);
  await expect(result).toContainText("16~46명");
  await expect(page.getByTestId("loads")).toContainText("16~46명");
});

test("night: 결과 없음 → 운행 시간 아님", async ({ page }) => {
  await run(page, "night");
  await expect(page.getByTestId("notice-night")).toContainText("다니지 않아요");
});

test("error: 서버가 입력 오류를 돌려주면 detail 을 보여준다", async ({ page }) => {
  await run(page, "error");
  await expect(page.getByTestId("notice-bad_input")).toContainText("0~40 정수");
});

test("down: 백엔드 꺼짐(502) → 안내 + 다시 시도 버튼", async ({ page }) => {
  await run(page, "down");
  const n = page.getByTestId("notice-server_down");
  await expect(n).toContainText("서버에 연결할 수 없어요");
  await expect(n.getByRole("button", { name: "다시 시도" })).toBeVisible();
});

test("down 뒤 서버가 살아나면 버튼 없이 60초 안에 저절로 돌아온다", async ({ page }) => {
  await page.clock.install();
  await run(page, "down");
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("notice-server_down")).toBeVisible();
  // 서버 복구 흉내: 목업은 요청마다 주소의 ?scenario 를 읽음
  await page.evaluate(() => history.replaceState(null, "", "/"));
  await page.clock.runFor(61_000);
  await expect(page.getByTestId("result")).toBeVisible();
});

test("slow: 느린 응답 → 타임아웃 안내", async ({ page }) => {
  test.setTimeout(30_000);
  await run(page, "slow");
  await expect(page.getByTestId("notice-timeout")).toBeVisible({ timeout: 15_000 });
});

test("상태 색(신호등)이 서로 다르고 뱃지·카드가 같은 색을 쓴다", async ({ page }) => {
  const colors = new Map<string, string>();
  const hero = page.getByTestId("hero");
  const read = async () => {
    const tone = (await hero.getAttribute("data-tone"))!;
    const bg = await page.getByTestId("verdict").evaluate((e) => getComputedStyle(e).color);   // 뱃지 글자색이 상태 색
    if (colors.has(tone)) expect(colors.get(tone)).toBe(bg);
    colors.set(tone, bg);
  };
  await run(page, "");
  await hero.waitFor();
  for (const n of ["3", "20", "30"]) {
    await page.getByTestId("n-input").fill(n);
    await page.waitForTimeout(700);
    await read();
  }
  await run(page, "stale");
  await hero.waitFor();
  await expect(hero).toHaveAttribute("data-tone", "hold");
  expect(new Set(colors.values()).size).toBe(colors.size);     // 상태 수 == 색 수
  expect(colors.size).toBeGreaterThanOrEqual(2);
});

test("loading: 첫 불러오기는 실제 카드와 같은 틀의 스켈레톤", async ({ page }) => {
  test.setTimeout(30_000);
  await page.goto("/?scenario=slow");
  await page.getByTestId("stop-sb02-32").click();
  await expect(page.getByTestId("hero-skeleton")).toBeVisible();
  await expect(page.getByTestId("tab-0")).toBeVisible();          // 탭 자리도 처음부터 잡혀 있어 데이터가 와도 안 출렁임
});

test("오류: 카드 틀은 그대로 두고 안내만 — 대기 인원 입력은 계속 쓸 수 있다", async ({ page }) => {
  await run(page, "down");
  await expect(page.getByTestId("hero-error")).toBeVisible();
  await expect(page.getByTestId("notice-server_down").getByRole("button", { name: "다시 시도" })).toBeVisible();
  await expect(page.getByTestId("n-input")).toBeVisible();
  await expect(page.getByTestId("loads")).toContainText("—");
  await page.getByTestId("tab-1").click();                        // 두 번째 화면도 정류장 순서는 보여 준다
  await expect(page.getByTestId("timeline").locator("button")).toHaveCount(3);
  await expect(page.getByTestId("timeline")).toContainText("도착 정보 없음");
});

test("확률이 바뀌면 카드 위쪽 색(그라데이션)이 초록에서 빨강으로 바뀐다", async ({ page }) => {
  await run(page, "");
  const hero = page.getByTestId("hero");
  await hero.waitFor();
  const tint = () => hero.evaluate((e) => getComputedStyle(e).getPropertyValue("--tint").trim());
  await expect(hero).toHaveAttribute("data-tone", "ok");
  const green = await tint();
  await page.getByRole("button", { name: "20명", exact: true }).click();
  await expect(hero).toHaveAttribute("data-tone", "bad");
  await page.waitForTimeout(900);                                 // 색이 스르르 바뀌는 시간(0.5초)
  const red = await tint();
  expect(red).not.toBe(green);
});
