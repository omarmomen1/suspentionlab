export default function requestAnimationFrame(cb) {
  if (typeof window !== "undefined" && window.requestAnimationFrame) {
    return window.requestAnimationFrame(cb);
  }
  return setTimeout(cb, 16);
}
