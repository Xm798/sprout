import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import zhCN from "./locales/zh-CN.json";

export const resources = {
  en: { translation: en },
  "zh-CN": { translation: zhCN },
} as const;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "en",
    supportedLngs: ["en", "zh-CN"],
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "sprout-lang",
      // Browsers report zh, zh-TW, zh-Hans-CN, …; we ship one Chinese locale.
      convertDetectedLanguage: (lng: string) =>
        lng.toLowerCase().startsWith("zh") ? "zh-CN" : lng,
    },
    interpolation: { escapeValue: false }, // React already escapes
  });

i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng;
});
// init's own languageChanged fired before the listener attached; set once now.
document.documentElement.lang = i18n.language;

export default i18n;
