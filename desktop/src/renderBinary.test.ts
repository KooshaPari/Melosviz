import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import {
  findRepoRoot,
  melosvizRenderBinaryName,
  melosvizRenderCandidatePaths,
  melosvizRenderMp4Argv,
  resolveMelosvizRenderBinary,
  truncateStderr,
} from "./renderBinary";

describe("renderBinary", () => {
  test("melosvizRenderBinaryName uses .exe on win32", () => {
    const expected =
      process.platform === "win32" ? "melosviz-render.exe" : "melosviz-render";
    expect(melosvizRenderBinaryName()).toBe(expected);
  });

  test("melosvizRenderCandidatePaths includes workspace and crate targets", () => {
    const paths = melosvizRenderCandidatePaths("/repo", "win32");
    expect(paths).toContain(path.join("/repo", "target", "release", "melosviz-render.exe"));
    expect(paths).toContain(path.join("/repo", "target", "debug", "melosviz-render.exe"));
    expect(paths).toContain(
      path.join("/repo", "crates", "melosviz-render-wgpu", "target", "release", "melosviz-render.exe"),
    );
    expect(paths).toContain(
      path.join("/repo", "crates", "melosviz-render-wgpu", "target", "debug", "melosviz-render.exe"),
    );
  });

  test("findRepoRoot walks up to Cargo.toml", () => {
    const root = findRepoRoot(path.join(import.meta.dir, "..", ".."));
    expect(root).not.toBeNull();
    expect(fs.existsSync(path.join(root!, "Cargo.toml"))).toBe(true);
  });

  test("melosvizRenderMp4Argv includes render-mp4 subcommand", () => {
    expect(
      melosvizRenderMp4Argv("/bin/render", "/tmp/spec.json", "/tmp/out.mp4")
    ).toEqual([
      "/bin/render",
      "render-mp4",
      "--spec",
      "/tmp/spec.json",
      "--output",
      "/tmp/out.mp4",
    ]);
  });

  test("truncateStderr caps long output", () => {
    const long = "x".repeat(5000);
    expect(truncateStderr(long).length).toBeLessThanOrEqual(501);
    expect(truncateStderr("short")).toBe("short");
  });
});

describe("resolveMelosvizRenderBinary", () => {
  let tmpDir: string;
  let prevEnv: string | undefined;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "melosviz-render-"));
    prevEnv = process.env.MELOSVIZ_RENDER_BIN;
    delete process.env.MELOSVIZ_RENDER_BIN;
  });

  afterEach(() => {
    if (prevEnv === undefined) delete process.env.MELOSVIZ_RENDER_BIN;
    else process.env.MELOSVIZ_RENDER_BIN = prevEnv;
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  test("prefers MELOSVIZ_RENDER_BIN when set", () => {
    const bin = path.join(tmpDir, melosvizRenderBinaryName());
    fs.writeFileSync(bin, "");
    process.env.MELOSVIZ_RENDER_BIN = bin;
    expect(resolveMelosvizRenderBinary({ searchFrom: tmpDir })).toBe(bin);
  });

  test("finds binary in fake repo target/release", () => {
    const repo = path.join(tmpDir, "repo");
    const releaseDir = path.join(repo, "target", "release");
    fs.mkdirSync(releaseDir, { recursive: true });
    const bin = path.join(releaseDir, melosvizRenderBinaryName());
    fs.writeFileSync(bin, "");
    fs.writeFileSync(path.join(repo, "Cargo.toml"), "[workspace]\n");

    const nested = path.join(repo, "desktop", "src");
    fs.mkdirSync(nested, { recursive: true });
    expect(resolveMelosvizRenderBinary({ searchFrom: nested })).toBe(bin);
  });

  test("finds binary in crate target/debug via cwd", () => {
    const repo = path.join(tmpDir, "repo-crate");
    const debugDir = path.join(
      repo,
      "crates",
      "melosviz-render-wgpu",
      "target",
      "debug",
    );
    fs.mkdirSync(debugDir, { recursive: true });
    const bin = path.join(debugDir, melosvizRenderBinaryName());
    fs.writeFileSync(bin, "");
    fs.writeFileSync(path.join(repo, "Cargo.toml"), "[workspace]\n");

    expect(
      resolveMelosvizRenderBinary({
        searchFrom: path.join(repo, "desktop", "src"),
        cwd: repo,
      }),
    ).toBe(bin);
  });

  test("finds bundled binary next to searchFrom parent", () => {
    const appDir = path.join(tmpDir, "app");
    const srcDir = path.join(appDir, "src");
    fs.mkdirSync(srcDir, { recursive: true });
    const bin = path.join(appDir, melosvizRenderBinaryName());
    fs.writeFileSync(bin, "");

    expect(
      resolveMelosvizRenderBinary({ searchFrom: srcDir, bundledDirs: [appDir] })
    ).toBe(bin);
  });

  test("returns null when nothing matches", () => {
    expect(
      resolveMelosvizRenderBinary({
        searchFrom: tmpDir,
        bundledDirs: [tmpDir],
      })
    ).toBeNull();
  });
});
