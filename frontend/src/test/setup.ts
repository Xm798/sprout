import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import i18n from "@/i18n";

// jsdom lacks these APIs that Radix primitives and next-themes rely on.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

// Radix UI Select relies on pointer capture APIs not available in jsdom.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = vi.fn().mockReturnValue(false);
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = vi.fn();
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = vi.fn();
}

// Tests assert English copy; pin the language regardless of host/browser env,
// and undo any per-test language switch or storage writes.
await i18n.changeLanguage("en");
afterEach(async () => {
  await i18n.changeLanguage("en");
  localStorage.clear();
});
