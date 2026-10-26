import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import de from "./de.json";
import en from "./en.json";

export const LANGUAGES = ["de", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

const STORAGE_KEY = "eel-ui-language";

function savedLanguage(): Language {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "en" ? "en" : "de";
  } catch {
    return "de";
  }
}

export function setLanguage(lang: Language) {
  i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // storage blocked: the choice just isn't remembered
  }
}

i18n.use(initReactI18next).init({
  resources: { de: { translation: de }, en: { translation: en } },
  lng: savedLanguage(),
  fallbackLng: "de",
  interpolation: { escapeValue: false },
});

document.documentElement.lang = i18n.language;

export default i18n;
