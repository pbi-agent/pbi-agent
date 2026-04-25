import { afterEach, expect } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup } from "@testing-library/react";
import { resetSessionStore } from "./store";

expect.extend(matchers);

class ResizeObserverMock implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver ??= ResizeObserverMock;

afterEach(() => {
  cleanup();
  resetSessionStore();
});
