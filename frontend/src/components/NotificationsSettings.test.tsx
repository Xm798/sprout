import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import NotificationsSettings from "./NotificationsSettings";

vi.mock("../api/hooks", () => ({
  useNotifications: () => ({
    data: {
      notify_enabled: false,
      notify_lead_days: 0,
      notify_time: "08:00",
      notify_timezone: "",
      notify_channels: [],
    },
    isLoading: false,
  }),
  useUpdateNotifications: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTestNotification: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ ios: true }),
  }),
}));

function wrap(ui: React.ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>
  );
}

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
});
