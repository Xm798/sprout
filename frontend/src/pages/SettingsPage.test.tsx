import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";
import { renderWithProviders } from "../test/utils";
import { api } from "../api/client";
vi.mock("../api/client", () => {
  const config = {
    id: 1, ledger_main_file: "/l/main.bean", ledger_root: "/l",
    write_mode: "single_file", single_file_name: "sprout.bean",
    month_file_template: "transactions/{year}/{year}-{month:02d}.bean",
    default_tag: "sprout", default_currency: "USD", lookahead_days: 0,
  };
  return {
    api: {
      currencies: vi.fn().mockResolvedValue(["USD", "CNY"]),
      getConfig: vi.fn().mockResolvedValue(config),
      updateConfig: vi.fn().mockResolvedValue({ ...config, lookahead_days: 7 }),
      getNotifications: vi.fn().mockResolvedValue({
        notify_enabled: false, notify_lead_days: 0, notify_time: "08:00",
        notify_timezone: "", notify_channels: [],
      }),
    },
  };
});

afterEach(() => vi.clearAllMocks());

test("loads config and saves an edited value", async () => {
  const user = userEvent.setup();
  renderWithProviders(<SettingsPage />);

  const lookahead = await screen.findByLabelText(/lookahead days/i);
  await user.clear(lookahead);
  await user.type(lookahead, "7");
  // Click the settings form's submit button (first "Save" in DOM; a second one belongs to NotificationsSettings).
  await user.click(screen.getAllByRole("button", { name: /save/i })[0]);

  await waitFor(() => expect(api.updateConfig).toHaveBeenCalledTimes(1));
  const arg = (api.updateConfig as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg.lookahead_days).toBe(7);
});
