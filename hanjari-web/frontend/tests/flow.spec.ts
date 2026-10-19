import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 첫 방문 → 정류장 시트에서 녹십자약국 선택
const start = async (page: Page, query = "") => {
  await page.goto("/" + query);
  await page.getByTestId("stop-sb02-32").click();
};

test("첫 방문엔 정류장 시트가 열리고 6곳이 전부 보인다", async ({ page }) => {
  await page.goto("/");
  for (const id of ["sb02-30", "sb02-31", "sb02-32", "jr03-19", "jr03-20", "jr03-23"]) {
    await expect(page.getByTestId(`stop-${id}`)).toBeVisible();
  }
});

test("정류장을 고르면 한 화면에 도착 정보·인원 입력·결과가 보인다", async ({ page }) => {
  await start(page);
  await expect(page.getByTestId("stop-name")).toHaveText("녹십자약국");
  await expect(page.getByTestId("arrival")).toContainText("서울70사6419");
  await expect(page.getByTestId("n-input")).toHaveValue("3");
  await expect(page.getByTestId("result")).toHaveAttribute("data-level", "여유 있음");
  await expect(page.getByText("버스 정보 13:11:33 기준")).toBeVisible();
});

test("인원을 바꾸면 결과가 바로 다시 계산된다", async ({ page }) => {
  await start(page);
  await expect(page.getByTestId("result")).toHaveAttribute("data-level", "여유 있음");
  await page.getByRole("button", { name: "20명" }).click();     // 목업 n30 → 녹십자약국 '어려울 수 있음'
  await expect(page.getByTestId("result")).toHaveAttribute("data-level", "어려울 수 있음");
});

test("입력 검증: 글자·빈칸·범위 밖·경계값", async ({ page }) => {
  await start(page);
  const input = page.getByTestId("n-input");
  const hint = page.getByTestId("n-hint");

  await input.fill("abc");
  await expect(hint).toContainText("숫자만");
  await expect(page.getByTestId("result")).toContainText("인원을 확인해 주세요");

  await input.fill("");
  await expect(hint).toContainText("입력해 주세요");

  await input.fill("41");
  await expect(hint).toContainText("0~40");

  await input.fill("40");
  await expect(hint).toHaveCount(0);
  await expect(page.getByTestId("n-plus")).toBeDisabled();      // 40 에서 더 못 늘림

  await input.fill("0");
  await expect(page.getByTestId("n-minus")).toBeDisabled();     // 0 에서 더 못 줄임
  await page.getByTestId("n-plus").click();
  await expect(input).toHaveValue("1");
});

test("같은 노선 다른 정류장을 누르면 그 정류장으로 바뀐다", async ({ page }) => {
  await start(page);
  await page.getByTestId("card-sb02-30").click();
  await expect(page.getByTestId("stop-name")).toHaveText("한성대입구역5번출구");
});

test("정류장 이름을 눌러 다른 노선으로 바꿀 수 있다", async ({ page }) => {
  await start(page);
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("stop-name")).toHaveText("창신역4번출구");
  await expect(page.getByTestId("card-jr03-19")).toBeVisible();
});

test("새로고침 버튼이 동작한다", async ({ page }) => {
  await start(page);
  await page.getByTestId("refresh").click();
  await expect(page.getByTestId("result")).toBeVisible();
});

test("마지막 정류장을 기억한다 (F5 후 시트 없이 바로 결과)", async ({ page }) => {
  await start(page);
  await page.reload();
  await expect(page.getByTestId("stop-sb02-32")).toHaveCount(0);
  await expect(page.getByTestId("stop-name")).toHaveText("녹십자약국");
  await expect(page.getByTestId("result")).toBeVisible();
});

// 아래는 가짜 시계로 시간을 건너뜀. 녹십자약국 목업 eta_sec = 100 (1분 40초)
test("도착 시간이 1초씩 줄어든다", async ({ page }) => {
  await page.clock.install();
  await start(page);
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("arrival")).toContainText("1분40초");
  await page.clock.runFor(5_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분3[3-5]초/);
});

test("30초마다 자동으로 다시 불러온다 (카운트다운이 새 값으로 바뀜)", async ({ page }) => {
  await page.clock.install();
  await start(page);
  await page.clock.runFor(36_000);
  // 새로고침이 없었다면 1분 0x초까지 내려갔어야 함
  await expect(page.getByTestId("arrival")).toContainText(/1분3\d초/);
});

test("남은 시간이 1분 미만이면 '곧 도착'", async ({ page }) => {
  // 화면이 안 보이는 상태로 만들어 자동 새로고침(카운트다운 되감기)을 막음
  await page.addInitScript(() => Object.defineProperty(document, "visibilityState", { get: () => "hidden" }));
  await page.clock.install();
  await start(page);
  await page.clock.runFor(39_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분0[01]초/);   // 60초 = 아직 숫자
  await page.clock.runFor(2_000);
  await expect(page.getByTestId("arrival")).toContainText("곧 도착");
});
