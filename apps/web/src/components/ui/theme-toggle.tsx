"use client";

import * as React from "react";
import { useSyncExternalStore } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Moon, Sun } from "lucide-react";

/**
 * Theme toggle — flips the `dark` class on <html> and persists the choice to
 * localStorage. The initial class is set before paint by the inline script in
 * layout.tsx (no flash); this only mirrors + mutates it. The <html> class is
 * the single source of truth, mirrored into React via useSyncExternalStore.
 */
function subscribe(onStoreChange: () => void) {
  const observer = new MutationObserver(onStoreChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => observer.disconnect();
}

const getSnapshot = (): "light" | "dark" =>
  document.documentElement.classList.contains("dark") ? "dark" : "light";

// Static export prerenders without a DOM; light is the site default.
const getServerSnapshot = (): "light" | "dark" => "light";

export function ThemeToggle({ className }: { className?: string }) {
  const reduce = useReducedMotion();
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* private mode — ignore */
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      className={
        "relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--color-border-soft)] text-[var(--color-text-dim)] transition-colors hover:border-[var(--color-border-hover)] hover:text-[var(--color-text)] " +
        (className ?? "")
      }
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={reduce ? false : { rotate: -90, opacity: 0, scale: 0.6 }}
          animate={{ rotate: 0, opacity: 1, scale: 1 }}
          exit={reduce ? undefined : { rotate: 90, opacity: 0, scale: 0.6 }}
          transition={{ duration: 0.2 }}
          className="inline-flex"
        >
          {theme === "dark" ? (
            <Sun className="h-[18px] w-[18px]" />
          ) : (
            <Moon className="h-[18px] w-[18px]" />
          )}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
