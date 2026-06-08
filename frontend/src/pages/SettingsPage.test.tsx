import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";
import { renderWithProviders } from "../test/utils";
import { api } from "../api/client";
vi.mock("../api/client", () => ({
  api: {
    getConfig: vi.fn().mockResolvedValue({
      id: 1, ledger_main_file: "/l/main.bean", ledger_root: "/l",
      write_mode: "single_file", single_file_name: "sprout.bean",
      month_file_template: "transactions/{year}/{year}-{month:02d}.bean",
      default_tag: "sprout", lookahead_days: 0,
    }),
    updateConfig: vi.fn().mockResolvedValue({
      id: 1, ledger_main_file: "/l/main.bean", ledger_root: "/l",
      write_mode: "single_file", single_file_name: "sprout.bean",
      month_file_template: "transactions/{year}/{year}-{month:02d}.bean",
      default_tag: "sprout", lookahead_days: 7,
    }),
  },
}));

afterEach(() => vi.clearAllMocks());

test("loads config and saves an edited value", async () => {
  const user = userEvent.setup();
  renderWithProviders(<SettingsPage />);

  const lookahead = await screen.findByLabelText(/lookahead days/i);
  await user.clear(lookahead);
  await user.type(lookahead, "7");
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(api.updateConfig).toHaveBeenCalledTimes(1));
  const arg = (api.updateConfig as ReturnType<typeof vi.fn>).mock.calls[0][0];
  expect(arg.lookahead_days).toBe(7);
});
