import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 첫 방문 → 정류장 시트에서 녹십자약국 선택
const start = async (page: Page, query = "") => {
  await page.goto("/" + query);
  await page.getByTestId("stop-sb02-32").click();
};
const chip = (page: Page, n: number) => page.getByRole("button", { name: `${n}명`, exact: true });

test("첫 방문엔 정류장 시트가 열리고 6곳이 전부 보인다", async ({ page }) => {
  await page.goto("/");
  for (const id of ["sb02-30", "sb02-31", "sb02-32", "jr03-19", "jr03-20", "jr03-23"]) {
    await expect(page.getByTestId(`stop-${id}`)).toBeVisible();
  }
});

test("정류장을 고르면 한 화면에 도착 정보·인원 입력·결과가 보인다", async ({ page }) => {
  await start(page);
  await expect(page.getByTestId("stop-name")).toHaveText("녹십자약국");
  await expect(page.getByTestId("arrival")).toContainText("이번 버스");
  await expect(page.getByTestId("arrival")).not.toContainText("서울70사6419");
  await expect(page.getByTestId("loads")).toContainText("한자리 예측");
  await expect(page.getByTestId("n-input")).toHaveValue("");        // 고른 적 없는 인원을 가정하지 않는다
  await expect(page.getByTestId("verdict")).toContainText("앞 사람 수를 고르면 알려 드려요");
  await expect(page.getByTestId("verdict")).not.toContainText(/\d+%/);
  await expect(page.getByText("버스 정보 13:11:33 기준")).toBeVisible();
});

test("인원을 바꾸면 결과가 바로 다시 계산된다", async ({ page }) => {
  await start(page);
  await page.getByTestId("n-input").fill("3");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "여유 있음");
  await chip(page, 20).click();                                   // 목업 n30 → 녹십자약국 '어려울 수 있음'
  await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "어려울 수 있음");
  await expect(page.getByTestId("verdict")).toContainText(/\d+%/);
  await expect(page.getByTestId("result")).toContainText("내 앞 20명");
});

test("+/-로 만든 인원이 칩에 있으면 그 칩이 바로 선택 표시된다", async ({ page }) => {
  await start(page);
  await expect(page.locator('[aria-pressed="true"]')).toHaveCount(0);      // 입력 전
  for (let i = 0; i < 5; i++) await page.getByTestId("n-plus").click();    // 빈칸 → 5
  await expect(page.getByTestId("n-input")).toHaveValue("5");
  await expect(chip(page, 5)).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("n-plus").click();                                // 6 → 칩에 없으니 선택 없음
  await expect(page.locator('[aria-pressed="true"]')).toHaveCount(0);
});

test("빠른 선택 20명으로 입력과 결과가 갱신된다", async ({ page }) => {
  await start(page);
  await chip(page, 20).click();
  await expect(page.getByTestId("n-input")).toHaveValue("20");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "어려울 수 있음");
});

test("입력 검증: 글자·빈칸·범위 밖·경계값", async ({ page }) => {
  await start(page);
  const input = page.getByTestId("n-input");
  const hint = page.getByTestId("n-hint");

  await input.fill("abc");
  await expect(hint).toContainText("숫자만");
  await expect(page.getByTestId("result")).toContainText("인원을 확인해 주세요");

  await input.fill("");                                                    // 빈칸은 오류가 아니라 입력 전 상태
  await expect(hint).toHaveCount(0);
  await expect(page.getByTestId("result")).toContainText("앞 사람 수를 고르면");
  await expect(page.getByTestId("n-minus")).toBeDisabled();

  await input.fill("41");
  await expect(hint).toContainText("0~40");

  await input.fill("40");
  await expect(hint).toHaveCount(0);
  await expect(page.getByTestId("n-plus")).toBeDisabled();

  await input.fill("0");
  await expect(page.getByTestId("n-minus")).toBeDisabled();
  await page.getByTestId("n-plus").click();
  await expect(input).toHaveValue("1");
});

test("다른 정류장 카드를 누르면 그 정류장으로 바뀌고 첫 화면으로 돌아온다", async ({ page }) => {
  await start(page);
  await page.getByTestId("tab-1").click();
  await page.getByTestId("card-sb02-30").click();
  await expect(page.getByTestId("tab-0")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("stop-name")).toHaveText("한성대입구역5번출구");
});

test("정류장 이름을 눌러 다른 노선으로 바꿀 수 있다", async ({ page }) => {
  await start(page);
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("stop-name")).toHaveText("창신역4번출구");
  await page.getByTestId("tab-1").click();
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
// 시계를 목업 스냅샷(13:11:33)과 먼 시각에 고정 → 받은 시각부터 셈. 실제 시각이 13:1x 일 때 결과가 바뀌지 않게
const FAR_FROM_SNAPSHOT = { time: new Date("2026-09-30T08:00:00+09:00") };
test("도착 시간이 1초씩 줄어든다", async ({ page }) => {
  await page.clock.install(FAR_FROM_SNAPSHOT);
  await start(page);
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("arrival")).toContainText("1분40초");
  await page.clock.runFor(5_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분3[3-5]초/);
});

test("버스가 멀면 30초마다 자동으로 다시 불러온다 (카운트다운이 새 값으로 바뀜)", async ({ page }) => {
  await page.clock.install(FAR_FROM_SNAPSHOT);
  await page.goto("/");
  await page.getByTestId("stop-sb02-30").click();  // 목업 eta_sec = 451 (7분 31초), 9정류장 전
  await page.clock.runFor(36_000);
  // 새로고침이 없었다면 6분 5x초까지 내려갔어야 함
  await expect(page.getByTestId("arrival")).toContainText(/7분2\d초/);
});

test("남은 시간이 1분 미만이면 '곧 도착'", async ({ page }) => {
  // 화면이 안 보이는 상태로 만들어 자동 새로고침(카운트다운 되감기)을 막음
  await page.addInitScript(() => Object.defineProperty(document, "visibilityState", { get: () => "hidden" }));
  await page.clock.install(FAR_FROM_SNAPSHOT);
  await start(page);
  await page.clock.runFor(39_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분0[01]초/);   // 60초 = 아직 숫자
  await page.clock.runFor(2_000);
  await expect(page.getByTestId("arrival")).toContainText("곧 도착");
});

// 카운트다운 출렁임: eta_sec 는 스냅샷(updated 13:11:33) 시각 값 → 받은 시각이 아니라 스냅샷 시각부터 센다
test("같은 스냅샷을 다시 받아도 카운트다운이 되감기지 않는다", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-30T13:11:43+09:00") });  // 스냅샷 10초 뒤
  await start(page);
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("arrival")).toContainText(/1분(2[89]|30)초/);  // 100 − 10 − 1
  await page.clock.runFor(32_000);                                           // 30초 자동 새로고침을 지나도
  await expect(page.getByTestId("arrival")).toContainText("곧 도착");         // 예전엔 1분3x초로 되감김
});

test("다음 버스: 있으면 몇 분 뒤인지 보여주고, 없으면 숨긴다", async ({ page }) => {
  await start(page);
  await page.getByTestId("n-input").fill("3");                   // 녹십자약국: 목업 n3 의 eta2_sec 716
  await expect(page.getByTestId("arrival").getByTestId("next-bus")).toContainText("다음 버스");
  await expect(page.getByTestId("next-bus")).toContainText("약 12분 후");
  await expect(page.locator("body")).not.toContainText("못 타면");   // 놓친 뒤의 버스와 같다고 단정하지 않는다
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-sb02-30").click();                // 필드가 없는 응답
  await expect(page.getByTestId("stop-name")).toHaveText("한성대입구역5번출구");
  await expect(page.getByTestId("next-bus")).toHaveCount(0);
});

test("입력이 잘못되면 이전 인원으로 계산한 판정을 보이지 않는다", async ({ page }) => {
  await start(page);
  await expect(page.getByTestId("verdict")).toBeVisible();
  await page.getByTestId("n-input").fill("41");
  await expect(page.getByTestId("n-hint")).toContainText("0~40");
  await expect(page.getByTestId("verdict")).toHaveCount(0);
  await page.getByTestId("n-input").fill("3");
  await expect(page.getByTestId("verdict")).toBeVisible();
});

test("도착 때 인원은 타고 있는 사람 수로만 말하고 뜻이 안 잡히는 혼잡도 말은 쓰지 않는다", async ({ page }) => {
  await start(page);
  await page.getByTestId("n-input").fill("3");
  await expect(page.getByTestId("verdict")).toContainText(/\d+%/);
  const loads = page.getByTestId("loads");
  await expect(loads).toContainText("약 45명일");
  await expect(loads).not.toContainText(/혼잡|보통|여유/);
});

test("첫 화면 아래 같은 노선 다른 정류장 2곳이 보이고, 누르면 그 정류장으로 바뀐다", async ({ page }) => {
  await start(page);
  await expect(page.getByTestId("other-sb02-30")).toBeVisible();
  await expect(page.getByTestId("other-sb02-31")).toBeVisible();
  await expect(page.getByTestId("other-sb02-32")).toHaveCount(0);                 // 내 정류장은 빠짐
  await expect(page.getByTestId("other-sb02-30")).toContainText(/약 \d+분 후|곧 도착/);
  await expect(page.getByTestId("other-sb02-30")).not.toContainText(/\d+%|확률/);
  await page.getByTestId("other-sb02-30").click();
  await expect(page.getByTestId("stop-name")).toHaveText("한성대입구역5번출구");
  await expect(page.getByTestId("other-sb02-32")).toBeVisible();
});

test("정류장 고르기에는 ARS 번호를 표시하지 않는다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("stop-sb02-30")).toHaveText("한성대입구역5번출구");
});
