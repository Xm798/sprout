import { render, screen } from "@testing-library/react";

import { DatePicker } from "@/components/ui/date-picker";
import i18n from "@/i18n";

test("formats the selected date with the active app language", async () => {
  const { rerender } = render(
    <DatePicker value="2026-01-15" onChange={() => {}} />
  );
  expect(screen.getByRole("button")).toHaveTextContent("January 15th, 2026");

  await i18n.changeLanguage("zh-CN");
  rerender(<DatePicker value="2026-01-15" onChange={() => {}} />);
  expect(screen.getByRole("button")).toHaveTextContent("2026年1月15日");
});

test("shows a translated placeholder when unset", async () => {
  await i18n.changeLanguage("zh-CN");
  render(<DatePicker value="" onChange={() => {}} />);
  expect(screen.getByRole("button")).toHaveTextContent("选择日期");
});
