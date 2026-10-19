// pm/jeongwon 브랜치의 pm/mock/*.json 을 src/mock/ 으로 복사 (내 폴더 밖은 건드리지 않음)
import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = resolve(root, "src/mock");
mkdirSync(out, { recursive: true });

execSync("git fetch origin pm/jeongwon", { cwd: root, stdio: "inherit" });

const files = ["predict_n0","predict_n3","predict_n15","predict_n30",
  "predict_wide","predict_stale","predict_empty_night","error_bad_input"];

for (const f of files) {
  const dst = resolve(out, `${f}.json`);
  try {
    const json = execSync(`git show origin/pm/jeongwon:pm/mock/${f}.json`, { cwd: root, stdio: ["ignore","pipe","ignore"] });
    writeFileSync(dst, json);
    console.log(`ok   ${f}.json`);
  } catch {
    if (existsSync(dst)) rmSync(dst);
    console.log(`skip ${f}.json (아직 없음)`);
  }
}