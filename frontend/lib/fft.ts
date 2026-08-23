/**
 * lib/fft.ts — Iterative radix-2 Cooley–Tukey FFT (P0-PERF-01).
 *
 * Replaces the O(N²) nested-loop DFT that ran on the UI thread
 * (12.5M–200M float ops → browser freeze). This implementation is
 * O(N log N): a 20,000-sample transform drops from ~200M ops to ~2.9M.
 *
 * Arbitrary input lengths are handled by zero-padding to the next power
 * of two (spectral leakage impact is negligible after Hann windowing).
 */

/** Next power of two ≥ n. */
export function nextPow2(n: number): number {
  let p = 1;
  while (p < n) p <<= 1;
  return p;
}

/**
 * In-place iterative radix-2 FFT on re/im arrays (length must be a power of 2).
 */
export function fftInPlace(re: Float64Array, im: Float64Array): void {
  const n = re.length;
  if (n <= 1 || (n & (n - 1)) !== 0) {
    throw new Error(`fftInPlace requires a power-of-two length, got ${n}`);
  }

  // Bit-reversal permutation
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      const tr = re[i]; re[i] = re[j]; re[j] = tr;
      const ti = im[i]; im[i] = im[j]; im[j] = ti;
    }
  }

  // Butterflies
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len;
    const wRe = Math.cos(ang), wIm = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let curRe = 1, curIm = 0;
      const half = len >> 1;
      for (let k = 0; k < half; k++) {
        const uRe = re[i + k], uIm = im[i + k];
        const vRe = re[i + k + half] * curRe - im[i + k + half] * curIm;
        const vIm = re[i + k + half] * curIm + im[i + k + half] * curRe;
        re[i + k] = uRe + vRe;
        im[i + k] = uIm + vIm;
        re[i + k + half] = uRe - vRe;
        im[i + k + half] = uIm - vIm;
        const nextRe = curRe * wRe - curIm * wIm;
        curIm = curRe * wIm + curIm * wRe;
        curRe = nextRe;
      }
    }
  }
}

export interface PsdResult {
  freqs: number[];
  psd: number[];
}

/**
 * One-sided power spectral density with Hann window — drop-in replacement
 * for the previous O(N²) DFT loops. Output shape matches: {freqs, psd}
 * where psd is in (unit²/Hz) and freqs spans [0, fs/2].
 */
export function computePsd(signal: number[] | Float64Array, fs: number): PsdResult {
  const n0 = signal.length;
  if (n0 < 64) return { freqs: [], psd: [] };

  const N = nextPow2(n0);
  const re = new Float64Array(N);
  const im = new Float64Array(N);

  // Hann window over the ORIGINAL length (zero-pad the rest)
  for (let i = 0; i < n0; i++) {
    re[i] = signal[i] * 0.5 * (1 - Math.cos(2 * Math.PI * i / (n0 - 1)));
  }

  fftInPlace(re, im);

  const half = N >> 1;
  const freqs: number[] = new Array(half + 1);
  const psd: number[] = new Array(half + 1);
  for (let k = 0; k <= half; k++) {
    freqs[k] = k * fs / N;
    psd[k] = (re[k] * re[k] + im[k] * im[k]) / (N * fs);
  }
  return { freqs, psd };
}
