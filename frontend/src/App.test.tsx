import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function mockHealth(body: object) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: () => Promise.resolve(body) }));
}

describe("App", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows connected when the database is up", async () => {
    mockHealth({ status: "ok", database: "up" });
    render(<App />);
    expect(await screen.findByText("Backend status: connected")).toBeInTheDocument();
  });

  it("shows when the database is down", async () => {
    mockHealth({ status: "ok", database: "down" });
    render(<App />);
    expect(await screen.findByText("Backend status: database down")).toBeInTheDocument();
  });

  it("shows unreachable when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);
    expect(await screen.findByText("Backend status: unreachable")).toBeInTheDocument();
  });
});
