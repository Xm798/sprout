import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import NotificationsSettings from "./NotificationsSettings";

const MASKED = "••••";

const baseData = {
  notify_enabled: false,
  notify_lead_days: 0,
  notify_time: "08:00",
  notify_timezone: "",
  notify_channels: [] as { id?: string; name: string; url: string; enabled: boolean }[],
};

// Mutable config lets individual tests override hook behavior.
let mockNotificationsData = { ...baseData };
const mockUpdateFn = vi.fn();

vi.mock("../api/hooks", () => ({
  useNotifications: () => ({ data: mockNotificationsData, isLoading: false }),
  useUpdateNotifications: () => ({ mutateAsync: mockUpdateFn, isPending: false }),
  useTestNotification: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ ios: true }),
  }),
}));

function wrap(ui: React.ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockNotificationsData = { ...baseData, notify_channels: [] };
  mockUpdateFn.mockResolvedValue(baseData);
});

describe("NotificationsSettings", () => {
  it("renders and can add a channel row", async () => {
    render(wrap(<NotificationsSettings />));
    expect(screen.getByText(/notification/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /add channel/i }));
    await waitFor(() =>
      expect(
        screen.getAllByPlaceholderText(/apprise url|url/i).length
      ).toBeGreaterThan(0)
    );
  });

  // F7: per-row Test button must be disabled when the row has no name (or no url)
  it("disables the per-row Test button when the channel name is empty", async () => {
    render(wrap(<NotificationsSettings />));
    await userEvent.click(screen.getByRole("button", { name: /add channel/i }));
    // The new row has empty name and empty url — its Test button must be disabled.
    await waitFor(() => {
      const testBtns = screen.getAllByRole("button", { name: /^test$/i });
      expect(testBtns[0]).toBeDisabled();
    });
  });

  // F9: after a successful save, URL inputs show the masked value from the server
  it("re-seeds URL inputs with the masked value after save", async () => {
    // Seed the form with a channel that already has a URL.
    mockNotificationsData = {
      ...baseData,
      notify_channels: [{ id: "abc", name: "ios", url: "bark://h/secret", enabled: true }],
    };
    // The save response returns the masked version.
    const maskedResponse = {
      ...baseData,
      notify_channels: [{ id: "abc", name: "ios", url: MASKED, enabled: true }],
    };
    mockUpdateFn.mockResolvedValueOnce(maskedResponse);

    render(wrap(<NotificationsSettings />));

    // Initially shows the plaintext URL (as seeded).
    await waitFor(() => {
      expect(screen.getByDisplayValue("bark://h/secret")).toBeInTheDocument();
    });

    // Click Save.
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    // After save, the URL input should show the mask, not the original plaintext.
    await waitFor(() => {
      expect(screen.getByDisplayValue(MASKED)).toBeInTheDocument();
      expect(screen.queryByDisplayValue("bark://h/secret")).not.toBeInTheDocument();
    });
  });
});
