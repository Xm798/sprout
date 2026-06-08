import { screen } from "@testing-library/react";
import App from "./App";
import { renderWithProviders } from "./test/utils";

test("renders nav and the inbox on the default route", () => {
  renderWithProviders(<App />, "/");
  expect(screen.getByRole("link", { name: /schedules/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /inbox/i })).toBeInTheDocument();
});
