import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import de from "./de.json";

// The UI is German only. Texts stay in de.json so they live in one place.
i18n.use(initReactI18next).init({
  resources: { de: { translation: de } },
  lng: "de",
  fallbackLng: "de",
  interpolation: { escapeValue: false },
});

export default i18n;
