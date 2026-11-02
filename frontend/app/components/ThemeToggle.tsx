"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const storageKey = "campus-theme";

export default function ThemeToggle() {
    const [dark, setDark] = useState(false);
    useEffect(() => {
        const sync = () => setDark(document.documentElement.dataset.theme === "dark");
        const media = window.matchMedia("(prefers-color-scheme: dark)");
        const systemChanged = () => {
            try { if (localStorage.getItem(storageKey)) return; } catch { /* Storage can be unavailable. */ }
            document.documentElement.dataset.theme = media.matches ? "dark" : "light";
            sync();
        };
        const storageChanged = (event: StorageEvent) => {
            if (event.key !== storageKey) return;
            document.documentElement.dataset.theme = event.newValue === "dark" || (!event.newValue && media.matches) ? "dark" : "light";
            sync();
        };
        sync();
        media.addEventListener("change", systemChanged);
        window.addEventListener("storage", storageChanged);
        return () => {
            media.removeEventListener("change", systemChanged);
            window.removeEventListener("storage", storageChanged);
        };
    }, []);

    return <button type="button" className="theme-toggle" aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"} onClick={() => {
        const next = !dark;
        document.documentElement.dataset.theme = next ? "dark" : "light";
        setDark(next);
        try { localStorage.setItem(storageKey, next ? "dark" : "light"); } catch { /* Keep the in-memory preference. */ }
    }}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>;
}
