import { describe, expect, it } from "vitest";
import { aggregateBars, ma } from "./bars";
import type { Bar } from "../types/market";

const sample: Bar[] = [
  { date: "2026-01-05", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10, amount: 100 },
  { date: "2026-01-06", open: 1.5, high: 2.5, low: 1, close: 2, volume: 20, amount: 200 },
  { date: "2026-01-12", open: 2, high: 3, low: 1.5, close: 2.5, volume: 30, amount: 300 },
];

describe("aggregateBars", () => {
  it("returns daily unchanged", () => {
    expect(aggregateBars(sample, "日K")).toHaveLength(3);
  });
  it("aggregates week", () => {
    const w = aggregateBars(sample, "周K");
    expect(w.length).toBeLessThan(3);
    expect(w[0].volume).toBe(30);
  });
});

describe("ma", () => {
  it("pads nulls then averages", () => {
    expect(ma([1, 2, 3, 4], 3)).toEqual([null, null, 2, 3]);
  });
});
