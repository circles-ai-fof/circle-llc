"use client";

import { useI18n } from "@/i18n/useI18n";

/**
 * M8.1 — Toggle EN/ES en cualquier punto del sidebar/header.
 * Persiste a localStorage via setLocale; emite custom event para que
 * todos los useI18n() consumers re-renderan.
 */
export default function LocaleToggle() {
  const { locale, changeLocale } = useI18n();

  return (
    <div style={{ display: "flex", gap: 2, alignItems: "center", padding: 2, background: "#0B0F1A", border: "1px solid #1e293b", borderRadius: 6 }}>
      <button
        onClick={() => changeLocale("es")}
        style={{
          padding: "3px 8px",
          background: locale === "es" ? "#00D4FF" : "transparent",
          color: locale === "es" ? "#0B0F1A" : "#94a3b8",
          border: "none",
          borderRadius: 4,
          fontSize: 10,
          fontWeight: 700,
          cursor: "pointer",
          fontFamily: "monospace",
        }}
        title="Español"
      >
        ES
      </button>
      <button
        onClick={() => changeLocale("en")}
        style={{
          padding: "3px 8px",
          background: locale === "en" ? "#00D4FF" : "transparent",
          color: locale === "en" ? "#0B0F1A" : "#94a3b8",
          border: "none",
          borderRadius: 4,
          fontSize: 10,
          fontWeight: 700,
          cursor: "pointer",
          fontFamily: "monospace",
        }}
        title="English"
      >
        EN
      </button>
    </div>
  );
}
