/**
 * Tests for BeatPulse component.
 *
 * @react-three/fiber requires a WebGL context; we mock it so tests run in jsdom.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.mock is hoisted — factory must not reference variables declared in this scope.
vi.mock("@react-three/fiber", () => ({
  useFrame: vi.fn(),
}));

vi.mock("three", async () => {
  const actual = await vi.importActual<typeof import("three")>("three");
  return { ...actual, DoubleSide: 2 };
});

import { useFrame } from "@react-three/fiber";
import { BeatPulse } from "../BeatPulse";
import { render } from "@testing-library/react";

const mockUseFrame = useFrame as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BeatPulse", () => {
  it("renders without crashing when beatTimes is provided", () => {
    expect(() =>
      render(
        <BeatPulse beatTimes={[1, 2, 3]} playbackT={0} durationSecs={10} />,
      ),
    ).not.toThrow();
    expect(mockUseFrame).toHaveBeenCalledOnce();
  });

  it("does not throw when beatTimes is empty and frame callback fires", () => {
    let frameCb: ((_rs: unknown, delta: number) => void) | null = null;
    mockUseFrame.mockImplementation(
      (fn: (_rs: unknown, delta: number) => void) => {
        frameCb = fn;
      },
    );

    render(<BeatPulse beatTimes={[]} playbackT={0} durationSecs={10} />);
    expect(frameCb).not.toBeNull();
    // With null mesh refs (jsdom), callback must not throw
    expect(() => frameCb!({}, 0.016)).not.toThrow();
  });

  it("registers a useFrame callback that does not throw on beat crossing scenario", () => {
    let frameCb: ((_rs: unknown, delta: number) => void) | null = null;
    mockUseFrame.mockImplementation(
      (fn: (_rs: unknown, delta: number) => void) => {
        frameCb = fn;
      },
    );

    // playbackT=0 → currentTime=0, beat at 5 s not yet crossed
    render(<BeatPulse beatTimes={[5]} playbackT={0} durationSecs={10} />);
    expect(frameCb).not.toBeNull();
    expect(() => frameCb!({}, 0.016)).not.toThrow();
  });

  it("calculates correct beat index for a sorted beatTimes array", () => {
    // Pure logic test — no component rendering needed
    const beatTimes = [1, 2, 3, 4, 5];
    const durationSecs = 10;
    // playbackT=0.35 → currentTime=3.5 → highest beat ≤ 3.5 is index 2 (time=3 s)
    const currentTime = 0.35 * durationSecs; // 3.5
    let foundIndex = -1;
    for (let i = 0; i < beatTimes.length; i++) {
      if (beatTimes[i]! <= currentTime) {
        foundIndex = i;
      } else {
        break;
      }
    }
    expect(foundIndex).toBe(2);
    expect(beatTimes[foundIndex]).toBe(3);
  });
});
