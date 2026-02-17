#!/usr/bin/env node

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const TEXT_EXTENSIONS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".json",
  ".md",
  ".css",
  ".scss",
  ".html",
  ".py",
  ".yml",
  ".yaml",
  ".toml",
  ".ini",
  ".sql",
  ".txt",
]);

const IGNORE_FILES = new Set(["scripts/check-mojibake.js"]);

const SUSPICIOUS_PATTERNS = [
  /\uFFFD/g, // replacement char
  /â€[^\s]?/g, // common mojibake for quotes/dashes
  /Â[^\s]?/g, // stray latin1 marker from bad UTF-8 decode
  /Ã[^\s]?/g, // common mojibake lead byte
  /Ä…|Ä‡|Ä™|Å‚|Å„|Ã³|Å›|Åº|Å¼|Ä„|Ä†|Ä˜|Å»|Å¹/g, // common broken PL letters
];

function getStagedFiles() {
  const raw = execSync("git diff --cached --name-only --diff-filter=ACM", {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
  if (!raw) return [];
  return raw.split(/\r?\n/).map((f) => f.trim()).filter(Boolean);
}

function isTextFile(filePath) {
  return TEXT_EXTENSIONS.has(path.extname(filePath).toLowerCase());
}

function hasMojibake(content) {
  return SUSPICIOUS_PATTERNS.some((pattern) => pattern.test(content));
}

function findFirstHitLine(content) {
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (SUSPICIOUS_PATTERNS.some((pattern) => pattern.test(line))) {
      return { lineNumber: i + 1, line };
    }
  }
  return null;
}

function main() {
  let stagedFiles;
  try {
    stagedFiles = getStagedFiles();
  } catch (error) {
    console.error("Nie udalo sie pobrac staged plikow:", error.message);
    process.exit(1);
  }

  const filesToScan = stagedFiles.filter((filePath) => !IGNORE_FILES.has(filePath) && isTextFile(filePath));
  if (filesToScan.length === 0) {
    process.exit(0);
  }

  const failures = [];
  for (const filePath of filesToScan) {
    let content;
    try {
      content = fs.readFileSync(filePath, "utf8");
    } catch (error) {
      console.error(`Nie udalo sie odczytac pliku ${filePath}:`, error.message);
      process.exit(1);
    }

    if (!hasMojibake(content)) continue;
    const hit = findFirstHitLine(content);
    failures.push({
      filePath,
      lineNumber: hit ? hit.lineNumber : null,
      line: hit ? hit.line : "",
    });
  }

  if (failures.length === 0) {
    process.exit(0);
  }

  console.error("\nWykryto potencjalne problemy z kodowaniem (mojibake):");
  for (const failure of failures) {
    if (failure.lineNumber) {
      console.error(`- ${failure.filePath}:${failure.lineNumber}`);
      console.error(`  ${failure.line}`);
    } else {
      console.error(`- ${failure.filePath}`);
    }
  }
  console.error("\nCommit zablokowany. Napraw kodowanie UTF-8 i sprobuj ponownie.");
  process.exit(1);
}

main();
