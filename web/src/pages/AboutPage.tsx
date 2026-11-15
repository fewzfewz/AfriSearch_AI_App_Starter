import { ArrowRight, BookOpen, Globe, Lock, Shield, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { PublicFooter, PublicHeader } from "../components/PublicNav";
import { Badge } from "../components/ui";

const PILLARS = [
  {
    icon: Globe,
    title: "Bridging the African Language Divide",
    description:
      "Most enterprise search tools fail on African languages, dialects, and non-Latin scripts. AfriSearch natively supports 94 languages—including Amharic, Oromo, Tigrinya, Swahili, Somali, Hausa, Yoruba, and Zulu—enabling cross-lingual retrieval where you can question in one language and discover answers in another.",
  },
  {
    icon: BookOpen,
    title: "Ethiopic Script & Regional OCR",
    description:
      "Decades of agricultural extensions, legal contracts, healthcare manuals, and cooperative records across Africa exist solely on physical paper or unindexed scanned PDFs. Our specialized OCR engine reads Fidäl (Ge'ez/Amharic) and Latin-based African orthographies with high precision.",
  },
  {
    icon: Shield,
    title: "Truth-Grounded Attribution",
    description:
      "Hallucination is unacceptable in healthcare, legal advice, and cooperative management. AfriSearch enforces a strict zero-hallucination policy: every single claim is cited to an exact paragraph and page number. If the documents do not contain the answer, AfriSearch explicitly says so.",
  },
  {
    icon: Lock,
    title: "Data Sovereignty & Enterprise Privacy",
    description:
      "Your documents remain strictly yours. With organization-level data isolation, AES/Fernet encryption at rest, and support for local offline on-premise model execution, sensitive data never leaves your controlled environment unless you choose a hosted provider.",
  },
];

const MILESTONES = [
  { year: "94+", label: "African & Global Languages", detail: "Cross-lingual search across diverse orthographies and scripts." },
  { year: "100%", label: "Verifiable Citations", detail: "Direct clickable links to original PDF pages and document snippets." },
  { year: "Zero", label: "Model Hallucinations", detail: "Strict refusal when queries fall outside indexed documentation." },
  { year: "100%", label: "Open Standards & REST API", detail: "Easily integrate with web apps, support desks, and mobile clients." },
];

export function AboutPage() {
  return (
    <div className="min-h-screen bg-ink-50/50 dark:bg-ink-950">
      <PublicHeader />

      <main className="py-16 sm:py-24">
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="mx-auto max-w-3xl text-center">
            <Badge tone="blue" className="mb-4 inline-flex items-center gap-1.5 px-3 py-1 text-sm font-semibold">
              <Sparkles className="h-4 w-4" /> Mission & Technology
            </Badge>
            <h1 className="font-display text-4xl font-bold tracking-tight text-ink-950 dark:text-white sm:text-5xl">
              Unlocking knowledge across Africa’s languages
            </h1>
            <p className="mt-5 text-lg leading-relaxed text-ink-600 dark:text-ink-300">
              AfriSearch AI was founded on a simple principle: every institution, cooperative, student, and researcher across Africa deserves immediate, cited access to their knowledge base in their native language.
            </p>
          </div>
        </section>

        {/* Stats Grid */}
        <section className="mx-auto mt-16 max-w-6xl px-4 sm:px-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {MILESTONES.map((item) => (
              <div
                key={item.label}
                className="rounded-2xl border border-ink-200 bg-white p-6 text-center shadow-sm dark:border-ink-800 dark:bg-ink-900"
              >
                <div className="font-display text-3xl font-extrabold text-brand-700 dark:text-brand-400 sm:text-4xl">
                  {item.year}
                </div>
                <div className="mt-1 font-semibold text-ink-900 dark:text-white">{item.label}</div>
                <div className="mt-2 text-xs text-ink-500 dark:text-ink-400">{item.detail}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Pillars */}
        <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
          <div className="text-center max-w-2xl mx-auto mb-14">
            <h2 className="font-display text-3xl font-bold text-ink-950 dark:text-white">
              Engineered for regional realities
            </h2>
            <p className="mt-3 text-ink-600 dark:text-ink-400">
              Why AfriSearch is architected differently from standard Western AI search systems.
            </p>
          </div>

          <div className="grid gap-8 md:grid-cols-2">
            {PILLARS.map((pillar) => {
              const Icon = pillar.icon;
              return (
                <div
                  key={pillar.title}
                  className="rounded-3xl border border-ink-200 bg-white p-8 shadow-sm dark:border-ink-800 dark:bg-ink-900"
                >
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
                    <Icon className="h-6 w-6" />
                  </div>
                  <h3 className="mt-5 font-display text-xl font-bold text-ink-950 dark:text-white">
                    {pillar.title}
                  </h3>
                  <p className="mt-3 text-sm leading-relaxed text-ink-600 dark:text-ink-300">
                    {pillar.description}
                  </p>
                </div>
              );
            })}
          </div>
        </section>

        {/* Architecture Section */}
        <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
          <div className="rounded-3xl border border-ink-200 bg-white p-8 shadow-sm dark:border-ink-800 dark:bg-ink-900 sm:p-12">
            <div className="max-w-3xl">
              <span className="text-xs font-bold uppercase tracking-wider text-brand-700 dark:text-brand-400">
                Core Architecture
              </span>
              <h2 className="mt-2 font-display text-3xl font-bold text-ink-950 dark:text-white">
                How AfriSearch processes your documents
              </h2>
              <p className="mt-4 text-ink-600 dark:text-ink-300 leading-relaxed text-sm">
                From initial document ingestion to real-time cited response generation, each step is optimized for high accuracy, low latency, and zero hallucination.
              </p>
            </div>

            <div className="mt-10 grid gap-6 md:grid-cols-3">
              <div className="rounded-2xl border border-ink-100 bg-ink-50/70 p-5 dark:border-ink-800 dark:bg-ink-950/60">
                <div className="text-xs font-mono font-bold text-brand-700 dark:text-brand-400">STAGE 01</div>
                <h4 className="mt-2 font-semibold text-ink-900 dark:text-white">Ingestion & OCR</h4>
                <p className="mt-2 text-xs text-ink-500 leading-relaxed">
                  Automatic layout detection, multi-page PDF splitting, Amharic/Swahili optical character recognition, and table-aware Markdown parsing.
                </p>
              </div>

              <div className="rounded-2xl border border-ink-100 bg-ink-50/70 p-5 dark:border-ink-800 dark:bg-ink-950/60">
                <div className="text-xs font-mono font-bold text-brand-700 dark:text-brand-400">STAGE 02</div>
                <h4 className="mt-2 font-semibold text-ink-900 dark:text-white">Multilingual Semantic Indexing</h4>
                <p className="mt-2 text-xs text-ink-500 leading-relaxed">
                  Passages are encoded into shared semantic vector space using state-of-the-art cross-lingual embeddings, enabling cross-language matching.
                </p>
              </div>

              <div className="rounded-2xl border border-ink-100 bg-ink-50/70 p-5 dark:border-ink-800 dark:bg-ink-950/60">
                <div className="text-xs font-mono font-bold text-brand-700 dark:text-brand-400">STAGE 03</div>
                <h4 className="mt-2 font-semibold text-ink-900 dark:text-white">Grounded Synthesis & Citations</h4>
                <p className="mt-2 text-xs text-ink-500 leading-relaxed">
                  Cross-encoder reranking isolates the exact relevant paragraphs. The chosen model writes answers referencing verified source citations [S1].
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
          <div className="rounded-3xl bg-gradient-to-br from-brand-800 via-brand-700 to-amber-700 px-8 py-12 text-center text-white shadow-xl">
            <h2 className="font-display text-3xl font-bold sm:text-4xl">Ready to empower your organization?</h2>
            <p className="mx-auto mt-3 max-w-xl text-white/85">
              Start building workspaces, uploading documents, and querying knowledge in minutes.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <Link
                to="/pricing"
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-white px-6 font-semibold text-brand-800 shadow hover:bg-brand-50 transition"
              >
                View Plans & Pricing <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                to="/developers"
                className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/20 px-6 font-semibold text-white hover:bg-white/10 transition"
              >
                Developer API Docs
              </Link>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
