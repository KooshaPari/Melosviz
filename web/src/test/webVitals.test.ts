import { describe, it, expect, vi } from 'vitest'
import { startWebVitals } from '../webVitals'

describe('startWebVitals', () => {
  it('does not throw when started', () => {
    expect(() => startWebVitals(vi.fn())).not.toThrow()
  })
})
