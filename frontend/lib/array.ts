/**
 * lib/array.ts — stack-safe array reductions (P1-PERF-05).
 *
 * `Math.max(...arr)` / `Math.min(...arr)` blow the call stack for arrays
 * larger than ~65k elements (simulation outputs routinely exceed this).
 * These loop-based helpers are O(N) with O(1) stack.
 */

export function maxOf(arr?: ArrayLike<number> | null): number {
  if (!arr || arr.length === 0) return 0;
  let m = -Infinity;
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i];
    if (typeof v === "number" && !isNaN(v) && v > m) m = v;
  }
  return m === -Infinity ? 0 : m;
}

export function minOf(arr?: ArrayLike<number> | null): number {
  if (!arr || arr.length === 0) return 0;
  let m = Infinity;
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i];
    if (typeof v === "number" && !isNaN(v) && v < m) m = v;
  }
  return m === Infinity ? 0 : m;
}

/** Maximum absolute value (sign preserved on the returned magnitude). */
export function maxAbs(arr?: ArrayLike<number> | null): number {
  if (!arr || arr.length === 0) return 0;
  let m = 0;
  for (let i = 0; i < arr.length; i++) {
    const raw = arr[i];
    if (typeof raw === "number" && !isNaN(raw)) {
      const v = Math.abs(raw);
      if (v > m) m = v;
    }
  }
  return m;
}
