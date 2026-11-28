export default function Loading() {
  return (
    // WCAG 4.1.3: status messages must be exposed to assistive technology
    <div className="flex items-center justify-center min-h-screen p-4" role="status" aria-live="polite">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-signal"></div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}
