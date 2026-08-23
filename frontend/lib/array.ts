/**
 * lib/array.ts — stack-safe array reductions (P1-PERF-05).
 *
 * `Math.max(...arr)` / `Math.min(...arr)` blow the call stack for arrays
 * larger than ~65k elements (simulation outputs routinely exceed this).
 * These loop-based helpers are O(N) with O(1) stack.
 */

export function maxOf(arr: ArrayLike<number>): number {
  let m = -Infinity;
  for (let i = 0; i < arr.length; i++) if (arr[i] > m) m = arr[i];
  return m;
}

export function minOf(arr: ArrayLike<number>): number {
  let m = Infinity;
  for (let i = 0; i < arr.length; i++) if (arr[i] < m) m = arr[i];
  return m;
}

/** Maximum absolute value (sign preserved on the returned magnitude). */
export function maxAbs(arr: ArrayLike<number>): number {
  let m = 0;
  for (let i = 0; i < arr.length; i++) {
    const v = Math.abs(arr[i]);
    if (v > m) m = v;
  }
  return m;
}
