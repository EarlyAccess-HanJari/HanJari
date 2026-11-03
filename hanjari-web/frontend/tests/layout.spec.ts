import { test, expect } from "@playwright/test";

const PHONES: [number, number][] = [
  [320, 568], [360, 560], [390, 844], [480, 800], [768, 1024], [1440, 900],
];

for (const [width, height] of PHONES) {
  test(`${width}x${height}: 로컬 UI 순서와 가로 넘침 확인`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await page.getByTestId("stop-sb02-30").click();
    await expect(page.getByTestId("loads")).toBeVisible();
    const top = async (id: string) => (await page.getByTestId(id).boundingBox())!.y;
    expect(await top("arrival")).toBeLessThan(await top("result"));
    expect(await top("result")).toBeLessThan(await top("n-input"));
    expect(await top("n-input")).toBeLessThan(await top("loads"));
    // 첫 화면은 세로 스크롤 없이 한 화면 안에 — 페이지 자체는 스크롤하지 않음
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.getByRole("button", { name: "20명", exact: true })).toHaveCount(1);
    await expect(page.getByTestId("dev-switcher")).toHaveCount(0);
    await page.getByTestId("tab-1").click();
    await expect(page.getByTestId("card-sb02-31")).toBeVisible();
  });
}

test("재계산 중 카드는 그대로 두고 흐리게만 하며 입력 위치를 유지한다", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await page.clock.runFor(1000);
  const input = page.getByTestId("n-input");
  const hero = page.getByTestId("hero");
  const before = (await input.boundingBox())!.y;
  const heroH = (await hero.boundingBox())!.height;
  await page.getByTestId("n-plus").click();
  await page.clock.runFor(260);
  await expect(hero).toHaveAttribute("aria-busy", "true");
  expect((await input.boundingBox())!.y).toBe(before);
  expect((await hero.boundingBox())!.height).toBe(heroH);
  await page.clock.runFor(400);
  await expect(hero).toHaveAttribute("aria-busy", "false");
  expect((await input.boundingBox())!.y).toBe(before);
});
