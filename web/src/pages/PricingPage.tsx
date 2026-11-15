import { ArrowRight, Check, Key, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PublicFooter, PublicHeader } from "../components/PublicNav";
import { Badge, Button, Spinner, useToast } from "../components/ui";
import { api, getOrganizationId } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { CheckoutResponse } from "../lib/types";

interface PricingPlan {
  id: "free" | "pro" | "business" | "enterprise";
  name: string;
  badge?: string;
  description: string;
  priceUSDMonthly: number;
  priceUSDAnnual: number;
  priceETBMonthly: number;
  priceETBAnnual: number;
  highlighted?: boolean;
  features: string[];
  cta: string;
}

const PLANS: PricingPlan[] = [
  {
    id: "free",
    name: "Community",
    description: "Ideal for individual researchers, testing, and small open documents.",
    priceUSDMonthly: 0,
    priceUSDAnnual: 0,
    priceETBMonthly: 0,
    priceETBAnnual: 0,
    features: [
      "Up to 3 workspaces",
      "50 MB document storage",
      "50 questions / month",
      "Basic multilingual search (94 languages)",
      "Standard OCR for English & Swahili",
      "Local AI and community models",
      "Web chat interface",
    ],
    cta: "Start Free",
  },
  {
    id: "pro",
    name: "Professional",
    badge: "Most Popular",
    description: "For professionals, legal consultants, and power researchers needing live API keys.",
    priceUSDMonthly: 29,
    priceUSDAnnual: 24,
    priceETBMonthly: 1500,
    priceETBAnnual: 1200,
    highlighted: true,
    features: [
      "Up to 10 workspaces",
      "5 GB document storage",
      "1,000 questions / month",
      "Full Developer API Key Access (afri_live_*)",
      "Embeddable Customer Support Widget integration",
      "BYOK: Connect your OpenAI, Claude, or Gemini keys",
      "Hosted high-intelligence models (Claude 3.5 & GPT-4o)",
      "Advanced table extraction & cross-passage citations",
      "Priority OCR for Amharic, Oromo, Tigrinya & more",
      "Priority email support",
    ],
    cta: "Upgrade to Pro",
  },
  {
    id: "business",
    name: "Business",
    description: "For growing teams, cooperatives, universities, and customer support desks.",
    priceUSDMonthly: 99,
    priceUSDAnnual: 79,
    priceETBMonthly: 5000,
    priceETBAnnual: 4000,
    features: [
      "Up to 50 workspaces",
      "50 GB document storage",
      "5,000 questions / month",
      "10 Team seats included with granular RBAC",
      "Unlimited Developer API keys & rate limit tiers",
      "Live support widget & multi-channel webhook webhooks",
      "Team collaboration with shared citations & history",
      "Audit logging & usage metering breakdown",
      "Dedicated account manager & 99.9% uptime SLA",
    ],
    cta: "Upgrade to Business",
  },
  {
    id: "enterprise",
    name: "Enterprise",
    description: "For banks, telecom providers, government agencies, and custom deployments.",
    priceUSDMonthly: 399,
    priceUSDAnnual: 319,
    priceETBMonthly: 20000,
    priceETBAnnual: 16000,
    features: [
      "Unlimited workspaces & unlimited team seats",
      "500 GB+ high-speed document storage",
      "Custom question volume & dedicated model throughput",
      "Air-gapped on-premise Docker / Kubernetes deployment",
      "Custom OCR dictionary tuning for regional dialects",
      "SSO / SAML authentication integration",
      "Custom billing via bank transfer / PO invoice",
      "24/7 Phone & Slack engineer escalation SLA",
    ],
    cta: "Contact Enterprise",
  },
];

const COMPARISON_ROWS = [
  { category: "Capacity & Workspaces", rows: [
    { name: "Accessible Workspaces", free: "3", pro: "10", business: "50", enterprise: "Unlimited" },
    { name: "Document Storage", free: "50 MB", pro: "5 GB", business: "50 GB", enterprise: "500 GB+" },
    { name: "Questions / Month", free: "50", pro: "1,000", business: "5,000", enterprise: "Custom volume" },
    { name: "Team Seats Included", free: "1", pro: "3", business: "10", enterprise: "Unlimited" },
  ]},
  { category: "Developer API & Integrations", rows: [
    { name: "Developer API Keys (afri_live_*)", free: "—", pro: "Yes (5 keys)", business: "Unlimited keys", enterprise: "Unlimited + dedicated tokens" },
    { name: "Live Customer Support Chat Widget", free: "—", pro: "Included", business: "Included", enterprise: "Custom white-label" },
    { name: "Direct Semantic Retrieval (/v1/search)", free: "—", pro: "Yes", business: "Yes", enterprise: "Yes + low latency edge" },
    { name: "Grounded Answer Generation (/v1/ask)", free: "—", pro: "Yes", business: "Yes", enterprise: "Yes" },
  ]},
  { category: "AI Models & BYOK", rows: [
    { name: "Hosted Cloud Models (No key required)", free: "Standard", pro: "Claude 3.5 Sonnet, GPT-4o", business: "All top-tier models", enterprise: "Dedicated cluster" },
    { name: "Bring-Your-Own-Key (BYOK) Encryption", free: "—", pro: "Included (Fernet encrypted)", business: "Included", enterprise: "Included + KMS" },
    { name: "Local On-Device Models", free: "Yes", pro: "Yes", business: "Yes", enterprise: "Yes" },
  ]},
  { category: "Document Ingestion & OCR", rows: [
    { name: "Supported Formats (PDF, DOCX, XLSX, PPTX, CSV, HTML)", free: "All", pro: "All", business: "All", enterprise: "All + custom connectors" },
    { name: "Ethiopic / Ge'ez OCR (Amharic, Tigrinya)", free: "Standard", pro: "High-precision OCR", business: "High-precision OCR", enterprise: "Tuned OCR pipeline" },
    { name: "Layout & Table-Aware Extraction", free: "Basic", pro: "Multi-column & table aware", business: "Multi-column & table aware", enterprise: "Custom parser rules" },
  ]},
  { category: "Security & Operations", rows: [
    { name: "Multi-Tenant Isolation", free: "Yes", pro: "Yes", business: "Yes", enterprise: "Air-gapped VPC available" },
    { name: "Workspace RBAC (Owner/Admin/Member/Viewer)", free: "Basic", pro: "Full", business: "Full + audit logs", enterprise: "Full + SSO/SAML" },
    { name: "Payment Methods", free: "N/A", pro: "Stripe & Chapa (Telebirr/Banks)", business: "Stripe & Chapa (Telebirr/Banks)", enterprise: "Wire / PO Invoice" },
  ]},
];

const PRICING_FAQ = [
  {
    q: "Do I need my own OpenAI or Anthropic API key to use AfriSearch?",
    a: "No! All paid plans (Pro, Business, and Enterprise) come with hosted access to high-performance AI models (including Claude 3.5 Sonnet and GPT-4o) out of the box. You do not need any external AI account. However, if your team already has enterprise API credits with OpenAI, Anthropic, or Google, you can optionally configure your own key (BYOK) in Settings at no extra charge.",
  },
  {
    q: "How does Developer API access work?",
    a: "Pro, Business, and Enterprise subscribers can generate cryptographically secure live API keys (starting with afri_live_) from the organization Settings. These keys allow you to integrate AfriSearch document retrieval, multilingual search, and cited Q&A into external software, mobile apps, and customer support widgets.",
  },
  {
    q: "Can I embed AfriSearch into my website as a customer support widget?",
    a: "Yes! Using your developer API key and workspace ID, you can easily embed an automated customer assistance chatbot into your website. AfriSearch answers customer questions in their chosen language and provides verifiable links directly to your public support manuals or policy documents.",
  },
  {
    q: "What payment methods are supported?",
    a: "We support international credit/debit cards (Visa, Mastercard, American Express) via Stripe. For customers in Ethiopia and East Africa, we support local payment channels including Telebirr, CBE Birr, Awash Bank, and Ethiopian bank transfers through our Chapa integration.",
  },
  {
    q: "Can I cancel or change my plan anytime?",
    a: "Yes. You can upgrade, downgrade, or cancel your subscription at any time directly from the Organization Settings page. If you cancel, your subscription remains active until the end of the paid billing period.",
  },
];

export function PricingPage() {
  const { signedIn } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [currency, setCurrency] = useState<"USD" | "ETB">("USD");
  const [annual, setAnnual] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  const handleSelectPlan = async (plan: PricingPlan) => {
    if (plan.id === "free") {
      if (signedIn) navigate("/app");
      else navigate("/signin?mode=signup");
      return;
    }

    if (plan.id === "enterprise") {
      window.location.href = "mailto:enterprise@afrisearch.ai?subject=AfriSearch%20Enterprise%20Inquiry";
      return;
    }

    if (!signedIn) {
      navigate(`/signin?mode=signup&plan=${plan.id}`);
      return;
    }

    // Authenticated checkout flow
    const orgId = getOrganizationId();
    if (!orgId) {
      navigate("/app/settings");
      return;
    }

    setCheckoutLoading(plan.id);
    const provider = currency === "ETB" ? "chapa" : "stripe";
    try {
      const res = await api<CheckoutResponse>(`/organizations/${encodeURIComponent(orgId)}/checkout`, {
        method: "POST",
        json: {
          plan_id: plan.id,
          provider,
          currency,
          interval: annual ? "year" : "month",
        },
      });

      if (res.checkout_url) {
        window.location.href = res.checkout_url;
      } else {
        toast(`Upgraded to ${plan.name} plan!`, "success");
        navigate("/app/settings");
      }
    } catch (err: any) {
      toast(err.message || "Failed to initiate checkout session.", "error");
    } finally {
      setCheckoutLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-ink-50/50 dark:bg-ink-950">
      <PublicHeader />

      <main className="py-16 sm:py-24">
        {/* Header */}
        <div className="mx-auto max-w-6xl px-4 text-center sm:px-6">
          <Badge tone="blue" className="mb-4 inline-flex items-center gap-1.5 px-3 py-1 text-sm font-semibold">
            <Sparkles className="h-4 w-4" /> Transparent, Predictable Plans
          </Badge>
          <h1 className="font-display text-4xl font-bold tracking-tight text-ink-950 dark:text-white sm:text-5xl">
            Simple pricing for teams & developers
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-ink-600 dark:text-ink-300">
            All paid tiers include hosted AI models out of the box, full Developer API access, and the freedom to bring your own provider keys (BYOK).
          </p>

          {/* Toggles */}
          <div className="mt-10 flex flex-wrap items-center justify-center gap-6">
            {/* Currency toggle */}
            <div className="inline-flex rounded-xl border border-ink-200 bg-white p-1 shadow-sm dark:border-ink-800 dark:bg-ink-900">
              <button
                type="button"
                onClick={() => setCurrency("USD")}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  currency === "USD"
                    ? "bg-brand-700 text-white shadow-sm"
                    : "text-ink-600 hover:text-ink-900 dark:text-ink-400 dark:hover:text-white"
                }`}
              >
                USD ($) — Stripe
              </button>
              <button
                type="button"
                onClick={() => setCurrency("ETB")}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  currency === "ETB"
                    ? "bg-brand-700 text-white shadow-sm"
                    : "text-ink-600 hover:text-ink-900 dark:text-ink-400 dark:hover:text-white"
                }`}
              >
                ETB (Br) — Chapa / Telebirr
              </button>
            </div>

            {/* Monthly / Annual toggle */}
            <div className="inline-flex items-center gap-3 text-sm font-medium text-ink-600 dark:text-ink-400">
              <span className={!annual ? "font-semibold text-ink-900 dark:text-white" : ""}>Monthly</span>
              <button
                type="button"
                role="switch"
                aria-checked={annual}
                onClick={() => setAnnual(!annual)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  annual ? "bg-brand-700" : "bg-ink-300 dark:bg-ink-700"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    annual ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
              <span className={annual ? "font-semibold text-ink-900 dark:text-white" : ""}>
                Yearly <span className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">Save 20%</span>
              </span>
            </div>
          </div>
        </div>

        {/* Plan Cards Grid */}
        <div className="mx-auto mt-14 max-w-6xl px-4 sm:px-6">
          <div className="grid gap-8 lg:grid-cols-4">
            {PLANS.map((plan) => {
              const isHighlight = plan.highlighted;
              const price = currency === "USD"
                ? (annual ? plan.priceUSDAnnual : plan.priceUSDMonthly)
                : (annual ? plan.priceETBAnnual : plan.priceETBMonthly);

              const formattedPrice = currency === "USD" ? `$${price}` : `${price.toLocaleString()} ETB`;

              return (
                <div
                  key={plan.id}
                  className={`relative flex flex-col justify-between rounded-3xl border bg-white p-7 shadow-sm transition hover:shadow-md dark:bg-ink-900 ${
                    isHighlight
                      ? "border-brand-500 ring-2 ring-brand-500/30 dark:border-brand-500 dark:ring-brand-500/20"
                      : "border-ink-200 dark:border-ink-800"
                  }`}
                >
                  {plan.badge && (
                    <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                      <span className="rounded-full bg-brand-700 px-3 py-1 text-xs font-bold uppercase tracking-wider text-white shadow-sm">
                        {plan.badge}
                      </span>
                    </div>
                  )}

                  <div>
                    <h3 className="font-display text-2xl font-bold text-ink-950 dark:text-white">
                      {plan.name}
                    </h3>
                    <p className="mt-2 text-sm text-ink-500 dark:text-ink-400 min-h-[40px]">
                      {plan.description}
                    </p>

                    <div className="mt-6 flex items-baseline gap-1">
                      <span className="text-4xl font-extrabold tracking-tight text-ink-950 dark:text-white">
                        {formattedPrice}
                      </span>
                      {plan.priceUSDMonthly > 0 && (
                        <span className="text-sm font-medium text-ink-500">/ month</span>
                      )}
                    </div>
                    {annual && plan.priceUSDMonthly > 0 && (
                      <div className="mt-1 text-xs font-medium text-brand-700 dark:text-brand-400">
                        Billed annually ({currency === "USD" ? `$${price * 12}/yr` : `${(price * 12).toLocaleString()} ETB/yr`})
                      </div>
                    )}

                    <div className="mt-8 border-t border-ink-100 pt-6 dark:border-ink-800">
                      <div className="text-xs font-semibold uppercase tracking-wider text-ink-900 dark:text-ink-200 mb-3">
                        Included Features
                      </div>
                      <ul className="space-y-3 text-sm text-ink-600 dark:text-ink-300">
                        {plan.features.map((feat) => (
                          <li key={feat} className="flex items-start gap-2.5">
                            <Check className="h-4 w-4 shrink-0 text-brand-700 mt-0.5 dark:text-brand-400" />
                            <span>{feat}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="mt-8 pt-4">
                    <Button
                      onClick={() => handleSelectPlan(plan)}
                      disabled={checkoutLoading === plan.id}
                      variant={isHighlight ? "primary" : "secondary"}
                      className="w-full justify-center h-11 text-sm font-semibold"
                    >
                      {checkoutLoading === plan.id ? (
                        <>
                          <Spinner className="h-4 w-4 mr-2" /> Connecting...
                        </>
                      ) : (
                        plan.cta
                      )}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Feature Comparison Matrix */}
        <section className="mx-auto mt-28 max-w-6xl px-4 sm:px-6">
          <div className="text-center">
            <h2 className="font-display text-3xl font-bold text-ink-950 dark:text-white">
              Compare plan capabilities
            </h2>
            <p className="mt-2 text-ink-600 dark:text-ink-400">
              Detailed breakdown of features across every AfriSearch subscription tier.
            </p>
          </div>

          <div className="mt-12 overflow-x-auto rounded-2xl border border-ink-200 bg-white shadow-sm dark:border-ink-800 dark:bg-ink-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-200 bg-ink-50/70 dark:border-ink-800 dark:bg-ink-950/70">
                  <th className="py-4 pl-6 pr-4 font-semibold text-ink-900 dark:text-white w-2/5">Feature</th>
                  <th className="py-4 px-4 font-semibold text-ink-900 dark:text-white">Community</th>
                  <th className="py-4 px-4 font-semibold text-brand-700 dark:text-brand-400">Professional</th>
                  <th className="py-4 px-4 font-semibold text-ink-900 dark:text-white">Business</th>
                  <th className="py-4 px-4 font-semibold text-ink-900 dark:text-white">Enterprise</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                {COMPARISON_ROWS.map((section) => (
                  <tr key={section.category} className="contents">
                    <tr className="bg-ink-50/40 dark:bg-ink-950/40">
                      <td colSpan={5} className="py-3 pl-6 text-xs font-bold uppercase tracking-wider text-brand-700 dark:text-brand-400">
                        {section.category}
                      </td>
                    </tr>
                    {section.rows.map((row) => (
                      <tr key={row.name} className="hover:bg-ink-50/30 dark:hover:bg-ink-950/30">
                        <td className="py-3.5 pl-6 pr-4 font-medium text-ink-900 dark:text-white">
                          {row.name}
                        </td>
                        <td className="py-3.5 px-4 text-ink-600 dark:text-ink-300">{row.free}</td>
                        <td className="py-3.5 px-4 font-semibold text-brand-700 dark:text-brand-300">{row.pro}</td>
                        <td className="py-3.5 px-4 text-ink-600 dark:text-ink-300">{row.business}</td>
                        <td className="py-3.5 px-4 text-ink-600 dark:text-ink-300">{row.enterprise}</td>
                      </tr>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Developer Integration Highlight Box */}
        <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-ink-900 via-brand-950 to-ink-900 p-8 sm:p-12 text-white shadow-xl">
            <div className="relative z-10 max-w-2xl">
              <span className="inline-flex items-center gap-1.5 rounded-md bg-brand-500/20 px-2.5 py-1 text-xs font-semibold text-brand-300">
                <Key className="h-3.5 w-3.5" /> Programmatic Developer Access
              </span>
              <h2 className="mt-4 font-display text-3xl font-bold sm:text-4xl">
                Integrate AfriSearch AI directly into your apps
              </h2>
              <p className="mt-3 text-ink-200 leading-relaxed">
                Connect your organization's knowledge base to your live customer support widgets, internal Slackbots, or custom client portals using our REST API.
              </p>
              <div className="mt-6 flex flex-wrap gap-4">
                <Link
                  to="/developers"
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-white px-5 font-semibold text-ink-950 shadow hover:bg-brand-50 transition"
                >
                  Explore Developer Documentation <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  to="/features"
                  className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/20 px-5 font-semibold text-white hover:bg-white/10 transition"
                >
                  View Solutions & Features
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* Pricing FAQ */}
        <section className="mx-auto mt-24 max-w-4xl px-4 sm:px-6">
          <div className="text-center">
            <h2 className="font-display text-3xl font-bold text-ink-950 dark:text-white">
              Frequently Asked Questions
            </h2>
            <p className="mt-2 text-ink-600 dark:text-ink-400">
              Got questions about billing, API tokens, or model credentials? We have answers.
            </p>
          </div>

          <div className="mt-10 divide-y divide-ink-200 border-y border-ink-200 dark:divide-ink-800 dark:border-ink-800">
            {PRICING_FAQ.map((item) => (
              <details key={item.q} className="group py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium text-ink-950 dark:text-white">
                  <span className="text-base font-semibold">{item.q}</span>
                  <span className="text-xl text-ink-400 transition group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 leading-relaxed text-ink-600 dark:text-ink-400 text-sm">
                  {item.a}
                </p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
