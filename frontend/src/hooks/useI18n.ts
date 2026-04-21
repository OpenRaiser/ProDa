import { useSession } from "@/store/useSession";
import { translate } from "@/lib/i18n";

export function useI18n() {
  const language = useSession((s) => s.language);
  const toggleLanguage = useSession((s) => s.toggleLanguage);
  const t = (
    key: string,
    paramsOrFallback?: Record<string, string | number> | string,
    fallback?: string
  ) => translate(language, key, paramsOrFallback, fallback);
  return { t, language, toggleLanguage };
}
