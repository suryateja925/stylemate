import { describe, expect, it } from "vitest";
import { humanize } from "./format";

describe("humanize", () => {
  it("turns API enum labels into readable text", () => {
    expect(humanize("smart_casual")).toBe("Smart Casual");
  });
});
