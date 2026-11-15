import { ArrowRight, Menu, X } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Logo } from "./ui";
import { useAuth } from "../lib/auth";

export function PublicHeader() {
  const { config, signedIn } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  const start = signedIn || config?.auth === "none" ? "/app" : "/signin?mode=signup";
  const startLabel = signedIn ? "Open Workspace" : "Get started";

  const navItems = [
    { name: "Features", href: "/features" },
    { name: "Pricing", href: "/pricing" },
    { name: "Developers", href: "/developers" },
    { name: "About", href: "/about" },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-ink-100/80 bg-white/90 backdrop-blur dark:border-ink-900 dark:bg-ink-950/90">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center">
            <Logo />
          </Link>
          <nav className="hidden gap-6 text-sm font-medium text-ink-600 dark:text-ink-400 md:flex">
            {navItems.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                className={`transition hover:text-ink-900 dark:hover:text-white ${
                  location.pathname === item.href
                    ? "font-semibold text-brand-700 dark:text-brand-400"
                    : ""
                }`}
              >
                {item.name}
              </Link>
            ))}
          </nav>
        </div>

        <div className="hidden items-center gap-3 md:flex">
          {config?.auth === "supabase" && !signedIn && (
            <Link
              to="/signin"
              className="h-9 inline-flex items-center rounded-lg px-3 text-sm font-medium text-ink-700 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800"
            >
              Sign in
            </Link>
          )}
          <Link
            to={start}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-700 px-4 text-sm font-medium text-white shadow-sm transition hover:bg-brand-800"
          >
            {startLabel} <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        {/* Mobile menu toggle */}
        <div className="flex md:hidden">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="rounded-lg p-2 text-ink-600 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800"
            aria-label="Toggle Menu"
          >
            {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </div>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="border-b border-ink-200 bg-white px-4 py-4 dark:border-ink-800 dark:bg-ink-950 md:hidden">
          <div className="flex flex-col gap-3">
            {navItems.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`px-2 py-1.5 text-base font-medium rounded-md ${
                  location.pathname === item.href
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300"
                    : "text-ink-700 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-900"
                }`}
              >
                {item.name}
              </Link>
            ))}
            <div className="mt-3 pt-3 border-t border-ink-100 dark:border-ink-800 flex flex-col gap-2">
              {config?.auth === "supabase" && !signedIn && (
                <Link
                  to="/signin"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex h-10 items-center justify-center rounded-lg border border-ink-200 font-medium text-ink-700 dark:border-ink-700 dark:text-ink-200"
                >
                  Sign in
                </Link>
              )}
              <Link
                to={start}
                onClick={() => setMobileMenuOpen(false)}
                className="flex h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 font-medium text-white hover:bg-brand-800"
              >
                {startLabel} <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export function PublicFooter() {
  const { config } = useAuth();
  return (
    <footer className="border-t border-ink-200 bg-white py-12 dark:border-ink-900 dark:bg-ink-950">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-5">
          <div className="col-span-2">
            <Logo className="text-ink-900 dark:text-white" />
            <p className="mt-3 max-w-sm text-sm text-ink-500 leading-relaxed">
              Multilingual semantic document retrieval, OCR, and verifiable cited answers for teams and developers across Africa.
            </p>
            <div className="mt-4 text-xs text-ink-400">
              Version {config?.version ?? "1.0.0"} · MIT License
            </div>
          </div>

          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-900 dark:text-white">Product</h4>
            <ul className="mt-3 space-y-2 text-sm text-ink-600 dark:text-ink-400">
              <li><Link to="/features" className="hover:text-brand-700 dark:hover:text-white">Features</Link></li>
              <li><Link to="/pricing" className="hover:text-brand-700 dark:hover:text-white">Pricing</Link></li>
              <li><Link to="/developers" className="hover:text-brand-700 dark:hover:text-white">Developers & API</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-900 dark:text-white">Resources</h4>
            <ul className="mt-3 space-y-2 text-sm text-ink-600 dark:text-ink-400">
              <li><Link to="/about" className="hover:text-brand-700 dark:hover:text-white">About & Mission</Link></li>
              <li><a href="/api/docs" className="hover:text-brand-700 dark:hover:text-white">Interactive Swagger</a></li>
              <li><a href="https://github.com/fewzfewz/AfriSearch_AI_App_Starter" target="_blank" rel="noopener noreferrer" className="hover:text-brand-700 dark:hover:text-white">GitHub Repo</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-900 dark:text-white">Legal & Trust</h4>
            <ul className="mt-3 space-y-2 text-sm text-ink-600 dark:text-ink-400">
              <li><Link to="/privacy" className="hover:text-brand-700 dark:hover:text-white">Privacy Policy</Link></li>
              <li><Link to="/terms" className="hover:text-brand-700 dark:hover:text-white">Terms of Service</Link></li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-ink-100 pt-6 text-center text-xs text-ink-400 dark:border-ink-900">
          © {new Date().getFullYear()} AfriSearch AI. Built for the African continent. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
