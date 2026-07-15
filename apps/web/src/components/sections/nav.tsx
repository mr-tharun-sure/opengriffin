"use client";

import * as React from "react";
import { useState } from "react";
import Link from "next/link";
import { motion, useScroll, useReducedMotion } from "framer-motion";
import { GitHubIcon } from "@/components/icons/github";
import {
  Navbar,
  NavBody,
  NavItems,
  MobileNav,
  MobileNavHeader,
  MobileNavToggle,
  MobileNavMenu,
} from "@/components/ui/resizable-navbar";
import { ThemeToggle } from "@/components/ui/theme-toggle";

function GriffinMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M12 2L4 6v6c0 5 3.5 9 8 10 4.5-1 8-5 8-10V6l-8-4zm0 7l3 2v3l-3 2-3-2v-3l3-2z" />
    </svg>
  );
}

const NAV_LINKS = [
  { name: "Features", link: "#features" },
  { name: "Install", link: "#install" },
  { name: "Gateways", link: "#gateways" },
  { name: "Why", link: "#why" },
  { name: "FAQ", link: "#faq" },
  {
    name: "Docs",
    link: "https://github.com/ManasaEdavalli-TharunSure/opengriffin/blob/main/docs/index.md",
    external: true,
  },
];

const GITHUB_URL = "https://github.com/ManasaEdavalli-TharunSure/opengriffin";

function Brand() {
  const reduce = useReducedMotion();
  return (
    <Link
      href="/"
      className="relative z-20 flex items-center gap-2 px-2 font-semibold text-[var(--color-text)]"
    >
      <motion.span
        whileHover={reduce ? undefined : { rotate: -8 }}
        transition={{ type: "spring", stiffness: 300, damping: 18 }}
        className="inline-flex"
      >
        <GriffinMark className="h-6 w-6 text-[var(--color-brand)] drop-shadow-[0_0_8px_var(--color-brand-glow)]" />
      </motion.span>
      <span>OpenGriffin</span>
      <span className="mono ml-1 rounded border border-[var(--color-brand)]/40 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[var(--color-brand-soft)]">
        v0.1
      </span>
    </Link>
  );
}

function GithubButton({
  onClick,
  className,
}: {
  onClick?: () => void;
  className?: string;
}) {
  return (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noreferrer"
      onClick={onClick}
      className={
        "flex items-center gap-1.5 rounded-md bg-[var(--color-text)] px-3 py-1.5 text-sm font-medium text-[var(--color-bg-canvas)] transition-all hover:scale-[1.03] hover:opacity-90 active:scale-[0.98] " +
        (className ?? "")
      }
    >
      <GitHubIcon size={14} />
      GitHub
    </a>
  );
}

export function Nav() {
  const { scrollYProgress } = useScroll();
  const [open, setOpen] = useState(false);

  // Lock body scroll while the mobile menu is open.
  React.useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <Navbar>
        {/* Desktop — resizable pill */}
        <NavBody>
          <Brand />
          <NavItems items={NAV_LINKS} />
          <div className="relative z-20 flex items-center gap-2">
            <ThemeToggle />
            <GithubButton />
          </div>
        </NavBody>

        {/* Mobile */}
        <MobileNav>
          <MobileNavHeader>
            <Brand />
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <MobileNavToggle isOpen={open} onClick={() => setOpen((v) => !v)} />
            </div>
          </MobileNavHeader>
          <MobileNavMenu isOpen={open}>
            {NAV_LINKS.map((link, i) => (
              <motion.a
                key={link.link}
                href={link.link}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noreferrer" : undefined}
                onClick={() => setOpen(false)}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.04 + i * 0.04, duration: 0.25 }}
                className="w-full rounded-md px-3 py-3 text-lg text-[var(--color-text)] transition-colors hover:bg-white/5 hover:text-[var(--color-brand-soft)]"
              >
                {link.name}
              </motion.a>
            ))}
            <GithubButton
              onClick={() => setOpen(false)}
              className="mt-3 w-full justify-center py-3"
            />
          </MobileNavMenu>
        </MobileNav>

        {/* Scroll progress bar — OpenGriffin signature, pinned to the very top edge */}
        <motion.div
          aria-hidden
          className="absolute left-0 top-0 h-[2px] w-full origin-left"
          style={{
            scaleX: scrollYProgress,
            backgroundImage:
              "linear-gradient(90deg, var(--color-brand) 0%, var(--color-alive) 50%, var(--color-brand-soft) 100%)",
            boxShadow: "0 0 8px var(--color-brand-glow)",
          }}
        />
      </Navbar>

      {/* Spacer so page content doesn't slide under the fixed header */}
      <div aria-hidden className="h-16" />
    </>
  );
}
