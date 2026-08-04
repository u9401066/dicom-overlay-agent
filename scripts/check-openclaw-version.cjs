"use strict";

function parseCalendarVersion(value) {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(String(value ?? "").trim());
  if (!match) {
    throw new Error(`invalid OpenClaw version: ${value}`);
  }
  return match.slice(1, 4).map(Number);
}

function isAtLeast(version, minimum) {
  const current = parseCalendarVersion(version);
  const floor = parseCalendarVersion(minimum);
  for (let index = 0; index < current.length; index += 1) {
    if (current[index] !== floor[index]) {
      return current[index] > floor[index];
    }
  }
  return true;
}

const [version, minimum] = process.argv.slice(2);
try {
  if (!isAtLeast(version, minimum)) {
    console.error(
      `[ERROR] OpenClaw ${version} is older than safe minimum ${minimum}.`,
    );
    process.exitCode = 1;
  }
} catch (error) {
  console.error(`[ERROR] ${error.message}`);
  process.exitCode = 2;
}

module.exports = { isAtLeast, parseCalendarVersion };
