import {
  ArrowRight, Check, FileSpreadsheet, Key, Languages, ScanText, ShieldCheck, Sparkles, Terminal,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PublicFooter, PublicHeader } from "../components/PublicNav";
import { Badge } from "../components/ui";

const CORE_FEATURES = [
  {
    icon: Languages,
    tag: "Multilingual Retrieval",
    title: "Ask in your language, search across all documents",
    description:
      "AfriSearch understands 94 languages natively and performs cross-lingual semantic matching. Ask a question in Amharic, Oromo, Tigrinya, Swahili, Somali, or Yoruba, and AfriSearch retrieves answers from reports written in English, French, or Arabic.",
    points: [
      "Cross-lingual query embedding without loss of semantic nuance",
      "Native script support for Ethiopic (Fidäl), Ge'ez, Arabic, and Latin variants",
      "Automatic language identification and script-aware normalization",
    ],
  },
  {
    icon: ScanText,
    tag: "OCR & Document Vision",
    title: "Read scanned PDFs, physical forms, and photos",
    description:
      "Legacy paper records, field assessments, and scanned manuals are automatically digitized. Our dual-layer OCR pipeline processes image-only pages and reconstructs high-fidelity text streams for indexing.",
    points: [
      "Specialized Amharic and Swahili Tesseract OCR dictionaries",
      "Automatic skew correction, noise suppression, and contrast enhancement",
      "Transparent badge indicators showing exactly which passages were read with OCR",
    ],
  },
  {
    icon: FileSpreadsheet,
    tag: "Table & Layout Engine",
    title: "Table-aware extraction and header preservation",
    description:
      "Numerical data, cooperative budgets, and clinical protocols often live inside complex multi-column tables. AfriSearch parses tabular structures into structured Markdown tables and propagates column headers across chunk splits so numerical context is never lost.",
    points: [
      "Table header preservation prevents ambiguous numbers in downstream retrieval",
      "Multi-column PDF layout flow detection without merging adjacent text blocks",
      "Full support for spreadsheets (XLSX, CSV) and structured presentations (PPTX)",
    ],
  },
  {
    icon: ShieldCheck,
    tag: "Zero-Hallucination Citations",
    title: "Every claim anchored to the exact page and paragraph",
    description:
      "When stakes are high, AI summaries without sources cannot be trusted. AfriSearch generates grounded answers where every claim links directly to its source document and page number. If the knowledge base does not cover the question, AfriSearch explicitly refuses rather than guessing.",
    points: [
      "Interactive source pills ([S1], [S2]) preview the exact cited paragraph on hover",
      "One-click PDF viewer opens directly to the highlighted source page",
      "Automated citation scrubbing removes ungrounded references before presentation",
    ],
  },
  {
    icon: Key,
    tag: "BYOK & Model Flexibility",
    title: "Use hosted models or Bring Your Own Keys (BYOK)",
    description:
      "Paid subscribers get immediate hosted access to world-class models like Claude 3.5 Sonnet and GPT-4o. If your enterprise already maintains credits with OpenAI, Anthropic, or Google, simply add your custom key in Settings. Keys are encrypted at rest using Fernet encryption.",
    points: [
      "Zero-configuration hosted models included on Pro, Business, and Enterprise tiers",
      "Fernet-encrypted BYOK key storage: keys are decrypted only in memory during inference",
      "Local offline model support for completely air-gapped on-premise environments",
    ],
  },
  {
    icon: Terminal,
    tag: "Developer REST API",
    title: "Embed AfriSearch into your websites & customer support",
    description:
      "Empower your own apps, client portals, and customer care helpdesks with AfriSearch intelligence. Generate cryptographically secured API keys (afri_live_*) to programmatically query semantic search, retrieve cited answers, and stream responses.",
    points: [
      "RESTful /api/v1/ask and /api/v1/search endpoints with sub-second response times",
      "Plug-and-play embeddable customer service chat widget snippet",
      "Granular token scoping: bind API keys to all organization workspaces or a specific workspace",
    ],
  },
];

export function FeaturesPage() {
  return (
    <div className="min-h-screen bg-ink-50/50 dark:bg-ink-950">
      <PublicHeader />

      <main className="py-16 sm:py-24">
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="mx-auto max-w-3xl text-center">
            <Badge tone="blue" className="mb-4 inline-flex items-center gap-1.5 px-3 py-1 text-sm font-semibold">
              <Sparkles className="h-4 w-4" /> Comprehensive Feature Tour
            </Badge>
            <h1 className="font-display text-4xl font-bold tracking-tight text-ink-950 dark:text-white sm:text-5xl">
              Engineered for intelligence, accuracy, and regional scale
            </h1>
            <p className="mt-5 text-lg leading-relaxed text-ink-600 dark:text-ink-300">
              Explore how AfriSearch AI combines multilingual vector embeddings, document OCR vision, table-aware chunking, and strict citation grounding into one unified platform.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <Link
                to="/pricing"
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand-700 px-6 font-semibold text-white shadow hover:bg-brand-800 transition"
              >
                View Plans & Pricing <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                to="/developers"
                className="inline-flex h-11 items-center gap-2 rounded-xl border border-ink-200 bg-white px-6 font-semibold text-ink-700 hover:bg-ink-50 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-200 transition"
              >
                Developer API Docs
              </Link>
            </div>
          </div>
        </section>

        {/* Feature Cards Grid */}
        <section className="mx-auto mt-20 max-w-6xl px-4 sm:px-6">
          <div className="grid gap-10 lg:grid-cols-2">
            {CORE_FEATURES.map((feature) => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.title}
                  className="flex flex-col justify-between rounded-3xl border border-ink-200 bg-white p-8 shadow-sm transition hover:shadow-md dark:border-ink-800 dark:bg-ink-900"
                >
                  <div>
                    <div className="flex items-center gap-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
                        <Icon className="h-6 w-6" />
                      </div>
                      <span className="rounded-md bg-ink-100 px-2.5 py-1 text-xs font-bold uppercase tracking-wider text-ink-700 dark:bg-ink-800 dark:text-ink-300">
                        {feature.tag}
                      </span>
                    </div>

                    <h3 className="mt-6 font-display text-2xl font-bold text-ink-950 dark:text-white">
                      {feature.title}
                    </h3>
                    <p className="mt-3 text-sm leading-relaxed text-ink-600 dark:text-ink-300">
                      {feature.description}
                    </p>
                  </div>

                  <div className="mt-8 border-t border-ink-100 pt-6 dark:border-ink-800">
                    <ul className="space-y-2.5 text-xs text-ink-700 dark:text-ink-300">
                      {feature.points.map((pt) => (
                        <li key={pt} className="flex items-start gap-2">
                          <Check className="h-4 w-4 shrink-0 text-brand-700 dark:text-brand-400 mt-0.5" />
                          <span>{pt}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Formats Supported Banner */}
        <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
          <div className="rounded-3xl border border-ink-200 bg-white p-8 dark:border-ink-800 dark:bg-ink-900 shadow-sm text-center">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-700 dark:text-brand-400">
              Universal Document Compatibility
            </span>
            <h2 className="mt-2 font-display text-2xl font-bold text-ink-950 dark:text-white sm:text-3xl">
              Drop in any document format. We handle the rest.
            </h2>
            <div className="mt-8 flex flex-wrap justify-center gap-3 sm:gap-4">
              {["PDF (Native & Scanned)", "Microsoft Word (.docx)", "Excel Workbooks (.xlsx, .csv)", "PowerPoint (.pptx)", "Markdown (.md)", "HTML & Web Transcripts"].map((fmt) => (
                <div
                  key={fmt}
                  className="rounded-xl border border-ink-200 bg-ink-50/60 px-4 py-2.5 text-xs font-semibold text-ink-800 dark:border-ink-800 dark:bg-ink-950/60 dark:text-ink-200"
                >
                  {fmt}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
          <div className="rounded-3xl bg-gradient-to-br from-brand-800 via-brand-700 to-amber-700 px-8 py-14 text-center text-white shadow-xl">
            <h2 className="font-display text-3xl font-bold sm:text-4xl">Experience AfriSearch in your workflow</h2>
            <p className="mx-auto mt-3 max-w-xl text-lg text-white/85">
              Start querying your document collection today with enterprise-grade security and zero hallucination.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <Link
                to="/pricing"
                className="inline-flex h-12 items-center gap-2 rounded-xl bg-white px-6 font-semibold text-brand-800 shadow hover:bg-brand-50 transition"
              >
                Choose a Plan <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
