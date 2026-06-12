import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "@/App";
import i18n from "@/i18n";
import { renderWithProviders } from "@/test/utils";

afterEach(async () => {
  await i18n.changeLanguage("en");
  localStorage.clear();
});

test("switches UI language and persists the choice", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />, "/");

  await user.click(screen.getByRole("button", { name: /switch language/i }));
  await user.click(await screen.findByRole("menuitem", { name: "简体中文" }));

  expect(
    await screen.findByRole("link", { name: "收件箱" })
  ).toBeInTheDocument();
  expect(localStorage.getItem("sprout-lang")).toBe("zh-CN");

  // The toggle's aria-label is itself translated now.
  await user.click(screen.getByRole("button", { name: "切换语言" }));
  await user.click(await screen.findByRole("menuitem", { name: "English" }));
  expect(
    await screen.findByRole("link", { name: "Inbox" })
  ).toBeInTheDocument();
});
