import i18n from "@/i18n";

test("initializes in English", () => {
  expect(i18n.resolvedLanguage).toBe("en");
  expect(i18n.t("nav.inbox")).toBe("Inbox");
});

test("switches to Simplified Chinese and updates <html lang>", async () => {
  await i18n.changeLanguage("zh-CN");
  expect(i18n.t("nav.inbox")).toBe("收件箱");
  expect(i18n.t("inbox.confirmingCount", { count: 3 })).toBe("正在确认 3 笔事项");
  expect(document.documentElement.lang).toBe("zh-CN");
  await i18n.changeLanguage("en");
  expect(i18n.t("inbox.confirmingCount", { count: 1 })).toBe(
    "Confirming 1 occurrence"
  );
  expect(i18n.t("inbox.confirmingCount", { count: 3 })).toBe(
    "Confirming 3 occurrences"
  );
});
