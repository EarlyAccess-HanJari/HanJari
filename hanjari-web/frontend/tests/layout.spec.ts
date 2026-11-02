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
    expect(await top("result")).toBeLessThan(await top("loads"));
    expect(await top("loads")).toBeLessThan(await top("n-input"));
    expect(await top("n-input")).toBeLessThan(await top("card-sb02-31"));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.getByRole("button", { name: "30명", exact: true })).toHaveCount(1);
    await expect(page.getByTestId("dev-switcher")).toHaveCount(0);
  });
}

test("재계산 중 숫자를 숨기고 입력 위치를 유지한다", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await page.clock.runFor(1000);
  const input = page.getByTestId("n-input");
  const before = (await input.boundingBox())!.y;
  await page.getByTestId("n-plus").click();
  await page.clock.runFor(260);
  const result = page.getByTestId("result");
  await expect(result).toHaveAttribute("aria-busy", "true");
  await expect(result.getByText("다시 계산 중…")).toBeVisible();
  await expect(result.getByText(/^\d+%$/)).toBeHidden();
  expect((await input.boundingBox())!.y).toBe(before);
  await page.clock.runFor(400);
  await expect(result).toHaveAttribute("aria-busy", "false");
  await expect(result.getByText(/^\d+%$/)).toBeVisible();
  expect((await input.boundingBox())!.y).toBe(before);
});
