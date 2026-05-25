import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

describe("frontend test harness", () => {
  it("renders a basic component and queries the DOM", () => {
    render(<div data-testid="probe">hello yuno</div>);
    expect(screen.getByTestId("probe")).toHaveTextContent("hello yuno");
  });

  it("jest-dom matchers are wired", () => {
    render(<button disabled>click me</button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
