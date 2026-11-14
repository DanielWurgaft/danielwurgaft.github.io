// Tiny Game of 24. Puzzles are all known-solvable.
const PUZZLES = [
  [1, 2, 3, 4], [4, 7, 8, 8], [3, 3, 8, 8], [1, 5, 5, 5], [2, 3, 5, 12],
  [1, 3, 4, 6], [6, 6, 6, 6], [2, 2, 2, 9], [1, 4, 5, 6], [3, 4, 5, 6],
  [1, 1, 5, 8], [2, 4, 10, 10], [5, 5, 9, 9], [1, 6, 11, 13], [3, 7, 7, 9],
];
const CHEERS = ["24! nicely done.", "yep, that's 24 ✦", "a rational solver.", "correct — want another?"];

const $ = (id) => document.getElementById(id);
let nums;

function newPuzzle() {
  nums = PUZZLES[Math.floor(Math.random() * PUZZLES.length)];
  $("nums").textContent = nums.join(" ");
  $("expr").value = "";
  $("verdict").textContent = "";
}

function check(expr) {
  if (!/^[\d\s+\-*/().]+$/.test(expr)) return "only numbers, + − × ÷ and parentheses, please.";
  const used = (expr.match(/\d+/g) || []).map(Number).sort((a, b) => a - b);
  if (used.join() !== [...nums].sort((a, b) => a - b).join()) return `use each of ${nums.join(", ")} exactly once.`;
  const value = Function(`"use strict"; return (${expr});`)();
  if (Math.abs(value - 24) < 1e-9) return CHEERS[Math.floor(Math.random() * CHEERS.length)];
  return `that's ${+value.toFixed(3)}, not 24.`;
}

$("g24").addEventListener("submit", (e) => {
  e.preventDefault();
  try { $("verdict").textContent = check($("expr").value); }
  catch { $("verdict").textContent = "hmm, that doesn't parse."; }
});
$("reroll").addEventListener("click", newPuzzle);
newPuzzle();
