"use client";

import { useEffect, useState } from "react";
import { type Locale, getLocale, setLocale, t as translate, type DictKey } from "./dict";

/**
 * Hook React para acceder a i18n con re-render cuando cambia el locale.
 * Listen a un custom event "circle.locale.changed" para que cambios desde
 * cualquier parte del árbol disparen re-renders en todos los consumers.
 */
export function useI18n() {
  const [locale, setLocaleState] = useState<Locale>(getLocale());

  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<{ locale: Locale }>;
      setLocaleState(ce.detail.locale);
    };
    window.addEventListener("circle.locale.changed", handler as EventListener);
    return () => window.removeEventListener("circle.locale.changed", handler as EventListener);
  }, []);

  const changeLocale = (loc: Locale) => {
    setLocale(loc);
    window.dispatchEvent(new CustomEvent("circle.locale.changed", { detail: { locale: loc } }));
  };

  const t = (key: DictKey): string => translate(key, locale);

  return { locale, changeLocale, t };
}
