// Web Vitals monitoring for melosviz — reports CLS, FCP, LCP, INP, TTFB.
// Uses the web-vitals library to send metrics to the console (or a backend endpoint).

import { onCLS, onFCP, onINP, onLCP, onTTFB, type Metric } from 'web-vitals'

const METRIC_THRESHOLD: Record<string, number> = {
  CLS: 0.1,
  FCP: 1800,
  LCP: 2500,
  INP: 200,
  TTFB: 800,
}

function isGood(metric: Metric): boolean {
  const threshold = METRIC_THRESHOLD[metric.name]
  if (threshold === undefined) return true
  return metric.value <= threshold
}

function logMetric(metric: Metric): void {
  const status = isGood(metric) ? 'good' : 'needs-improvement'
  // eslint-disable-next-line no-console
  console.log(`[Web Vitals] ${metric.name}=${Math.round(metric.value)} (${status})`)
}

/**
 * Start collecting Web Vitals metrics.
 * Optionally pass a callback to send metrics to an analytics endpoint.
 */
export function startWebVitals(
  onReport: (metric: Metric) => void = logMetric
): void {
  onCLS(onReport)
  onFCP(onReport)
  onLCP(onReport)
  onINP(onReport)
  onTTFB(onReport)
}
