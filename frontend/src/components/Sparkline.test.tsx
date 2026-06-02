import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Sparkline } from "./Sparkline";

describe("Sparkline", () => {
  it("renders a dashed baseline when there is too little data", () => {
    const { container } = render(<Sparkline data={[]} />);
    expect(container.querySelector("line")).toBeTruthy();
    expect(container.querySelector("polyline")).toBeNull();
  });

  it("draws a polyline once it has at least two points", () => {
    const { container } = render(<Sparkline data={[1, 2, 3]} />);
    const poly = container.querySelector("polyline");
    expect(poly).toBeTruthy();
    // 3 points → 3 "x,y" pairs
    expect(poly?.getAttribute("points")?.trim().split(" ")).toHaveLength(3);
  });

  it("colors green when the window closes up, red when down", () => {
    const upPoly = render(<Sparkline data={[1, 5]} />).container.querySelector(
      "polyline",
    );
    expect(upPoly?.getAttribute("stroke")).toBe("#1fd49a");

    const downPoly = render(<Sparkline data={[5, 1]} />).container.querySelector(
      "polyline",
    );
    expect(downPoly?.getAttribute("stroke")).toBe("#ff5d6c");
  });
});
