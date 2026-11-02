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
    expect(await top("arrival")).toBeLessThan(await top("loads"));
    expect(await top("loads")).toBeLessThan(await top("card-sb02-31"));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.getByTestId("n-input")).toHaveCount(0);
    await expect(page.getByTestId("dev-switcher")).toHaveCount(0);
  });
}

test("새로고침 중 현재 인원 카드 위치를 유지한다", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  const loads = page.getByTestId("loads");
  await expect(loads).toBeVisible();
  const before = (await loads.boundingBox())!.y;
  await page.getByTestId("refresh").click();
  await expect(page.getByTestId("refresh")).toBeEnabled();
  expect((await loads.boundingBox())!.y).toBe(before);
});
