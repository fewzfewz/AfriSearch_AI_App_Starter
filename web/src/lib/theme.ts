import { useEffect } from "react";
import { useStoredState } from "./hooks";

export type Theme = "light" | "dark" | "system";

function apply(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** The light/dark preference; "system" follows the device. */
export function useTheme() {
  const [theme, setTheme] = useStoredState<Theme>("afrisearch.theme", "system");
  useEffect(() => {
    apply(theme);
    if (theme !== "system") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);
  return [theme, setTheme] as const;
}
