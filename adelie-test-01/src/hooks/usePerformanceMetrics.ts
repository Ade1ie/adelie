import { useEffect } from 'react';

/**
 * Custom hook that captures core web performance metrics using the native
 * PerformanceObserver API and forwards them to an internal monitoring endpoint.
 *
 * The hook runs once on component mount and sends data via `fetch` with the
 * `keepalive` flag so that metrics are still transmitted when the page is
 * unloading.
 */
export function usePerformanceMetrics(): void {
  useEffect(() => {
    if (typeof PerformanceObserver === 'undefined') {
      // Browser does not support PerformanceObserver – nothing to do.
      return;
    }

    const sendMetric = (name: string, value: number) => {
      const payload = {
        name,
        value,
        pathname: window.location.pathname,
        timestamp: Date.now(),
      };
      // Use keepalive to allow the request to be sent during page unload.
      fetch('/api/performance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(() => {
        // Silently ignore network errors – metrics are best‑effort.
      });
    };

    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        switch (entry.entryType) {
          case 'paint':
            // "first-paint" and "first-contentful-paint" are reported here.
            sendMetric(entry.name, entry.startTime);
            break;
          case 'largest-contentful-paint':
            sendMetric('LCP', entry.startTime);
            break;
          case 'first-input':
            // FID is the delay between the first input event and its processing.
            // @ts-ignore – first-input entries have processingStart.
            const fid = (entry as any).processingStart - entry.startTime;
            sendMetric('FID', fid);
            break;
          case 'layout-shift':
            // CLS – only count layout shifts without recent user input.
            // @ts-ignore – layout-shift entries have hadRecentInput.
            if (!(entry as any).hadRecentInput) {
              // @ts-ignore – layout-shift entries have value.
              sendMetric('CLS', (entry as any).value);
            }
            break;
          default:
            break;
        }
      }
    });

    // Observe the relevant entry types. "buffered" ensures we also get
    // metrics that were recorded before the observer was attached.
    observer.observe({ type: 'paint', buffered: true });
    observer.observe({ type: 'largest-contentful-paint', buffered: true });
    observer.observe({ type: 'first-input', buffered: true });
    observer.observe({ type: 'layout-shift', buffered: true });

    // Cleanup on unmount.
    return () => observer.disconnect();
  }, []);
}
