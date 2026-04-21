#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const manifest = JSON.parse(fs.readFileSync(path.join(repoRoot, "release-manifest.json"), "utf8"));

function parseArgs(argv) {
  const args = {
    profile: "base",
    appHome: process.env.SCIBUDY_HOME || process.env.RESEARCH_MCP_HOME || path.join(os.homedir(), ".research-mcp"),
    python: null,
    fromPath: null,
    upgrade: false,
    installCodex: true,
    noPrompt: false,
    doctorOnly: false,
    printPlan: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--profile") args.profile = argv[++i];
    else if (arg === "--app-home") args.appHome = argv[++i];
    else if (arg === "--python") args.python = argv[++i];
    else if (arg === "--from-path") args.fromPath = argv[++i];
    else if (arg === "--upgrade") args.upgrade = true;
    else if (arg === "--no-prompt") args.noPrompt = true;
    else if (arg === "--doctor-only") args.doctorOnly = true;
    else if (arg === "--print-plan") args.printPlan = true;
    else if (arg === "--no-install-codex") args.installCodex = false;
    else if (arg === "--help" || arg === "-h") args.help = true;
  }
  return args;
}

function findPython(explicitPython) {
  const candidates = explicitPython ? [explicitPython] : ["python3", "python"];
  for (const candidate of candidates) {
    const result = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (result.status === 0) {
      const versionText = (result.stdout || result.stderr || "").trim();
      const match = versionText.match(/Python\s+(\d+)\.(\d+)\.(\d+)/i);
      if (!match) continue;
      const major = Number(match[1]);
      const minor = Number(match[2]);
      if (major > 3 || (major === 3 && minor >= 10)) {
        return { command: candidate, version: versionText };
      }
    }
  }
  throw new Error("Python 3.10+ is required but no python executable was found");
}

function printHelp() {
  console.log(`Scibudy installer

Usage:
  npx scibudy-install --profile base

Common options:
  --profile base|analysis|gpu-local|full
  --app-home /custom/path
  --python /path/to/python3
  --from-path /path/to/local/source/checkout
  --upgrade
  --no-prompt
  --doctor-only
  --print-plan
  --no-install-codex

Profiles:
  base       install CLI, MCP runtime, UI assets, and optional Codex config
  analysis   same as base, oriented toward full-text analysis workflows
  gpu-local  install the dedicated local model environment for Linux + NVIDIA
  full       base + gpu-local

Prerequisites:
  - Node.js 18+ to run this installer
  - Python 3.10+ for the runtime
  - Codex optional, but recommended if you want MCP integration
  - conda + NVIDIA GPU only if you want the full local model profile
`);
}

function ensureNodeVersion() {
  const major = Number(process.versions.node.split(".")[0] || 0);
  if (major < 18) {
    throw new Error(`Node.js 18+ is required. Detected ${process.versions.node}.`);
  }
}

function isLinux() {
  return process.platform === "linux";
}

function hasNvidia() {
  const result = spawnSync("nvidia-smi", ["--query-gpu=name", "--format=csv,noheader"], {
    stdio: "ignore",
  });
  return result.status === 0;
}

function hasCodex() {
  const result = spawnSync("codex", ["--version"], { stdio: "ignore" });
  return result.status === 0;
}

function normalizeProfile(args) {
  validateAppHome(args.appHome);
  if (args.profile === "gpu-local" && (!isLinux() || !hasNvidia())) {
    throw new Error("The gpu-local profile currently requires Linux with an NVIDIA GPU. Use --profile base or --profile analysis on this machine.");
  }
  if (args.profile === "full" && (!isLinux() || !hasNvidia())) {
    console.log("Full profile requested on a machine without the supported Linux+NVIDIA local-model path. Continuing with the non-GPU parts of the install.");
  }
}

function validateAppHome(appHome) {
  const resolved = path.resolve(appHome);
  const root = path.parse(resolved).root;
  const dangerous = new Set([
    root,
    path.resolve(root, "etc"),
    path.resolve(root, "usr"),
    path.resolve(root, "bin"),
    path.resolve(root, "sbin"),
    path.resolve(root, "var"),
    path.resolve(root, "opt"),
    path.dirname(os.homedir()),
  ]);
  if (dangerous.has(resolved)) {
    throw new Error(`Refusing dangerous --app-home path: ${resolved}`);
  }
}

function printPreflight(args, pythonInfo) {
  console.log("Scibudy installer preflight");
  console.log(`- profile: ${args.profile}`);
  console.log(`- app home: ${args.appHome}`);
  console.log(`- python: ${pythonInfo.command} (${pythonInfo.version})`);
  console.log(`- platform: ${process.platform}`);
  console.log(`- nvidia gpu detected: ${hasNvidia() ? "yes" : "no"}`);
  console.log(`- codex detected: ${hasCodex() ? "yes" : "no"}`);
  console.log(`- install Codex config: ${args.installCodex ? "yes" : "no"}`);
  console.log(`- prompt for secrets: ${args.noPrompt ? "no" : "yes"}`);
  console.log(`- install source: ${args.fromPath ? path.resolve(args.fromPath) : `${manifest.python.package_name}@${manifest.python.version}`}`);
  console.log("");
}

function printInstallPlan(args, pythonInfo) {
  const runtimeVenv = path.join(args.appHome, "runtime", ".venv");
  const runtimePython = process.platform === "win32"
    ? path.join(runtimeVenv, "Scripts", "python.exe")
    : path.join(runtimeVenv, "bin", "python");
  console.log("Scibudy install plan");
  console.log(`- profile: ${args.profile}`);
  console.log(`- app home: ${args.appHome}`);
  console.log(`- runtime venv: ${runtimeVenv}`);
  console.log(`- runtime python: ${runtimePython}`);
  console.log(`- installer python: ${pythonInfo.command} (${pythonInfo.version})`);
  console.log(`- install source: ${args.fromPath ? path.resolve(args.fromPath) : `${manifest.python.package_name}@${manifest.python.version}`}`);
  console.log(`- will create/update runtime venv: yes`);
  console.log(`- will install Codex config: ${args.installCodex ? "yes" : "no"}`);
  console.log(`- will prompt for secrets: ${args.noPrompt ? "no" : "yes"}`);
}

function printDoctorOnly(args, pythonInfo) {
  console.log("Scibudy installer readiness");
  console.log(`- node: ${process.version}`);
  console.log(`- python: ${pythonInfo.command} (${pythonInfo.version})`);
  console.log(`- platform: ${process.platform}`);
  console.log(`- app home: ${args.appHome}`);
  console.log(`- app home safety: ok`);
  console.log(`- nvidia gpu detected: ${hasNvidia() ? "yes" : "no"}`);
  console.log(`- codex detected: ${hasCodex() ? "yes" : "no"}`);
  console.log("- doctor-only: no files were written");
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    env: { ...process.env, ...(options.env || {}) },
    cwd: options.cwd || process.cwd(),
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}`);
  }
}

function syncUiAssets(appHome) {
  const sourceDist = path.join(repoRoot, "web", "dist");
  if (!fs.existsSync(path.join(sourceDist, "index.html"))) {
    return false;
  }
  const targetDist = path.join(appHome, "ui", "dist");
  fs.mkdirSync(path.dirname(targetDist), { recursive: true });
  fs.rmSync(targetDist, { recursive: true, force: true });
  fs.cpSync(sourceDist, targetDist, { recursive: true });
  return true;
}

function main() {
  ensureNodeVersion();
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    return;
  }
  normalizeProfile(args);
  const python = findPython(args.python);
  printPreflight(args, python);
  if (args.doctorOnly) {
    printDoctorOnly(args, python);
    return;
  }
  if (args.printPlan) {
    printInstallPlan(args, python);
    return;
  }
  const runtimeVenv = path.join(args.appHome, "runtime", ".venv");
  const runtimePython = process.platform === "win32"
    ? path.join(runtimeVenv, "Scripts", "python.exe")
    : path.join(runtimeVenv, "bin", "python");

  fs.mkdirSync(path.dirname(runtimeVenv), { recursive: true });
  if (!fs.existsSync(runtimePython)) {
    console.log("Creating runtime virtual environment...");
    run(python.command, ["-m", "venv", runtimeVenv], { env: { RESEARCH_MCP_HOME: args.appHome } });
  }

  console.log("Upgrading pip in the runtime environment...");
  run(runtimePython, ["-m", "pip", "install", "--upgrade", "pip"]);
  const requirement = args.fromPath
    ? path.resolve(args.fromPath)
    : `${manifest.python.package_name}==${manifest.python.version}`;
  const pipArgs = ["-m", "pip", "install"];
  if (args.upgrade) pipArgs.push("--upgrade");
  pipArgs.push(requirement);
  console.log(`Installing runtime package: ${requirement}`);
  run(runtimePython, pipArgs);
  console.log("Syncing UI assets...");
  syncUiAssets(args.appHome);

  const cliModuleArgs = [
    "-m",
    "research_mcp.cli",
    "bootstrap",
    "--profile",
    args.profile,
    "--format",
    "table",
  ];
  if (args.installCodex) cliModuleArgs.push("--install-codex");
  else cliModuleArgs.push("--no-install-codex");
  if (args.noPrompt) cliModuleArgs.push("--no-prompt");

  console.log("Running Scibudy bootstrap...");
  run(runtimePython, cliModuleArgs, {
    env: {
      RESEARCH_MCP_HOME: args.appHome,
      SCIBUDY_HOME: args.appHome,
    },
  });
  console.log("");
  console.log("Scibudy installer finished.");
  console.log("Next steps:");
  console.log("- Run `scibudy doctor`");
  console.log("- Run `scibudy search \"your topic\"`");
  console.log("- Run `scibudy ui --open`");
  console.log("- Run `codex mcp get research` if you enabled Codex integration");
}

main();
