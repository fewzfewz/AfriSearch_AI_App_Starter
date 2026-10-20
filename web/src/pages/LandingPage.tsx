// The public home page.
import {
  ArrowRight, BookOpenCheck, Building2, Cpu, FileSearch, GraduationCap, HeartPulse, Languages, Lock, MessagesSquare,
  ScanText, Sprout, Upload, Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, Logo } from "../components/ui";
import { useAuth } from "../lib/auth";

const LANGUAGES = ["English", "አማርኛ", "Kiswahili", "Soomaali", "Afaan Oromoo", "Hausa", "Yorùbá", "isiZulu", "Français", "العربية", "Português", "ትግርኛ"];

const FEATURES = [
  { icon: Languages, title: "Ask in your language", text: "Search understands 94 languages and matches across them: ask in Amharic, find the answer in an English report." },
  { icon: ScanText, title: "Reads scans and photos", text: "Scanned PDFs and photos of printed pages are read with OCR, including Amharic and Swahili." },
  { icon: BookOpenCheck, title: "Every answer is cited", text: "Answers link each claim to the exact passage and page, so you can check before you act." },
  { icon: FileSearch, title: "Knows what it doesn't know", text: "When your documents don't cover a question, AfriSearch says so instead of inventing an answer." },
  { icon: Cpu, title: "Your choice of AI", text: "Use Claude, ChatGPT or Gemini, or a model running on your own computer, with nothing sent outside." },
  { icon: Users, title: "Built for teams", text: "Separate workspaces for each team or project, shared with the people who need them." },
];

const USE_CASES = [
  { icon: Sprout, title: "Agriculture & cooperatives", text: "Extension guides, crop and storage manuals, market reports." },
  { icon: HeartPulse, title: "Health programmes", text: "Protocols, training material and field reports for health workers." },
  { icon: GraduationCap, title: "Schools & universities", text: "Course readers, research papers and policies in several languages." },
  { icon: Building2, title: "NGOs & businesses", text: "Policies, contracts, procedures and years of reports in one place." },
];

const FAQ = [
  ["Which languages does it support?", "Search works in 94 languages, including Amharic, Swahili, Somali, Afaan Oromo, Hausa, Yoruba, Zulu, French, Arabic and English, and you can ask in a different language from the document. Reading scans (OCR) is set up for English, Amharic and Swahili by default, and more Tesseract languages can be added."],
  ["Can it read scanned documents?", "Yes. Pages without a text layer and photos of pages are read with OCR. Clear, straight, well-lit scans give the best results; handwriting isn't supported."],
  ["Does it make things up?", "Answers are written only from passages found in your documents, and each claim cites its source. When nothing relevant is found, AfriSearch says the documents don't cover the question. Answers can still be wrong, which is why every source is one click away."],
  ["Where are my documents stored?", "On the server that runs AfriSearch. If you choose a cloud model (Claude, ChatGPT or Gemini), the passages needed for an answer are sent to that provider; with a local model nothing leaves the server."],
  ["Can my team share documents?", "Yes. Each workspace has its own documents and chats, and its owner can add colleagues by email."],
  ["Is it open source?", "Yes, under the MIT license. You can run it on your own computer or server with Docker."],
];

function HeroIllustration() {
  return (
    <div className="relative mx-auto w-full max-w-xl" aria-hidden="true">
      <div className="absolute -inset-6 rounded-[2rem] bg-gradient-to-br from-brand-200/60 via-amber-100/40 to-transparent blur-2xl dark:from-brand-900/40 dark:via-amber-900/10" />
      <div className="relative rounded-2xl border border-ink-200 bg-white p-5 shadow-2xl shadow-ink-900/10 dark:border-ink-800 dark:bg-ink-900">
        <div className="flex justify-end">
          <div className="rounded-2xl rounded-br-md bg-ink-100 px-4 py-2.5 text-sm dark:bg-ink-800">የቡና ፍሬ ለምን ያህል ጊዜ መድረቅ አለበት?</div>
        </div>
        <div className="mt-4 flex gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-700 text-white"><MessagesSquare className="h-4 w-4" /></div>
          <div className="min-w-0 text-sm leading-6">
            <p>
              ፍሬውን ከመሬት ከፍ ባለ የማድረቂያ አልጋ ላይ ከሁለት እስከ ሶስት ሳምንት ያድርቁ፤ በቀን ብዙ ጊዜ ይገልብጡት
              <span className="mx-1 rounded-md bg-brand-100 px-1.5 py-0.5 text-[11px] font-semibold text-brand-800 dark:bg-brand-900 dark:text-brand-200">S1</span>
            </p>
            <div className="mt-3 rounded-xl border border-brand-200 bg-brand-50/60 p-3 dark:border-brand-900 dark:bg-brand-950/40">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded bg-brand-700 px-1.5 py-0.5 font-bold text-white">S1</span>
                <span className="font-medium">coffee_care_guide.pdf</span>
                <span className="text-ink-500">· page 2</span>
                <Badge tone="blue"><ScanText className="h-3 w-3" />read with OCR</Badge>
              </div>
              <p className="mt-2 line-clamp-2 text-xs text-ink-600 dark:text-ink-400">ማድረቅ። የተለቀመውን ፍሬ ከመሬት ከፍ ባለ የማድረቂያ አልጋ ላይ ከሁለት እስከ ሶስት ሳምንት ያድርቁ…</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LandingPage() {
  const { config, signedIn } = useAuth();
  const start = signedIn || config?.auth === "none" ? "/app" : "/signin?mode=signup";
  const startLabel = signedIn ? "Open AfriSearch" : "Get started";
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-ink-100/80 bg-white/80 backdrop-blur dark:border-ink-900 dark:bg-ink-950/80">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Link to="/"><Logo /></Link>
          <nav className="hidden gap-6 text-sm text-ink-600 dark:text-ink-400 md:flex">
            <a href="#features" className="hover:text-ink-900 dark:hover:text-white">Features</a>
            <a href="#how" className="hover:text-ink-900 dark:hover:text-white">How it works</a>
            <a href="#privacy" className="hover:text-ink-900 dark:hover:text-white">Privacy</a>
            <a href="#faq" className="hover:text-ink-900 dark:hover:text-white">FAQ</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {config?.auth === "supabase" && !signedIn && (
              <Link to="/signin" className="hidden h-9 items-center rounded-lg px-3 text-sm font-medium text-ink-700 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800 sm:inline-flex">Sign in</Link>
            )}
            <Link to={start} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-700 px-4 text-sm font-medium text-white shadow-sm hover:bg-brand-800">
              {startLabel} <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </header>

      <main>
        <div className="relative isolate">
        <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
          <div className="bg-glow absolute inset-0" />
          <div className="bg-dots absolute inset-0 opacity-70" />
        </div>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-2 lg:pt-24">
          <div>
            <Badge tone="brand" className="px-2.5 py-1">Open source · cloud or on your own server</Badge>
            <h1 className="mt-5 font-display text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">
              Answers from your documents, <span className="text-brand-700 dark:text-brand-500">in your language.</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-8 text-ink-600 dark:text-ink-400">
              Upload reports, manuals and scanned pages. Ask in Amharic, Swahili, English or 90+ other languages, and get answers that cite the exact passage and page.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to={start} className="inline-flex h-12 items-center gap-2 rounded-xl bg-brand-700 px-6 font-medium text-white shadow-lg shadow-brand-700/20 hover:bg-brand-800">
                {startLabel} <ArrowRight className="h-4 w-4" />
              </Link>
              <a href="#how" className="inline-flex h-12 items-center rounded-xl px-6 font-medium text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50 dark:text-ink-200 dark:ring-ink-800 dark:hover:bg-ink-900">See how it works</a>
            </div>
          </div>
          <HeroIllustration />
        </section>

        </div>
        <section className="border-y border-ink-100 bg-ink-50/60 py-8 dark:border-ink-900 dark:bg-ink-900/40" aria-label="Languages">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="text-center text-sm font-medium text-ink-500">Ask and search in</p>
            <div className="mt-4 flex flex-wrap justify-center gap-x-6 gap-y-2 text-lg font-semibold text-ink-700 dark:text-ink-300">
              {LANGUAGES.map((language) => <span key={language}>{language}</span>)}
              <span className="text-ink-400">+ 80 more</span>
            </div>
          </div>
        </section>

        <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-20 sm:px-6">
          <h2 className="font-display text-3xl font-semibold sm:text-4xl">Everything your documents know, one question away</h2>
          <p className="mt-3 max-w-2xl text-lg text-ink-600 dark:text-ink-400">Built for the documents and languages organisations across Africa actually work with.</p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="rounded-2xl border border-ink-200 p-6 dark:border-ink-800">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-400"><Icon className="h-5 w-5" /></div>
                <h3 className="mt-4 font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-ink-600 dark:text-ink-400">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="how" className="scroll-mt-20 bg-ink-950 py-20 text-white">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-semibold sm:text-4xl">How it works</h2>
            <div className="mt-12 grid gap-8 md:grid-cols-3">
              {[
                [Upload, "1. Add your documents", "Drag in PDFs, text files or photos of pages. AfriSearch reads them, runs OCR on scans, and builds a private search index."],
                [MessagesSquare, "2. Ask a question", "Type it the way you'd ask a colleague, in any language. Follow-up questions keep the context of the conversation."],
                [BookOpenCheck, "3. Check the sources", "Each claim cites a passage. Click it to read the original text, or open the document at that page."],
              ].map(([Icon, title, text]) => {
                const StepIcon = Icon as typeof Upload;
                return (
                  <div key={title as string}>
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-700"><StepIcon className="h-5 w-5" /></div>
                    <h3 className="mt-4 text-lg font-semibold">{title as string}</h3>
                    <p className="mt-2 leading-7 text-ink-300">{text as string}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <h2 className="font-display text-3xl font-semibold sm:text-4xl">Made for real work</h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {USE_CASES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="rounded-2xl bg-ink-50 p-6 dark:bg-ink-900">
                <Icon className="h-6 w-6 text-brand-700 dark:text-brand-500" />
                <h3 className="mt-3 font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm leading-6 text-ink-600 dark:text-ink-400">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="privacy" className="mx-auto max-w-6xl scroll-mt-20 px-4 pb-20 sm:px-6">
          <div className="grid items-center gap-10 rounded-3xl border border-ink-200 p-8 dark:border-ink-800 sm:p-12 lg:grid-cols-2">
            <div>
              <Lock className="h-8 w-8 text-brand-700 dark:text-brand-500" />
              <h2 className="mt-4 font-display text-3xl font-semibold">Your documents stay yours</h2>
              <p className="mt-3 text-lg leading-8 text-ink-600 dark:text-ink-400">
                Run AfriSearch on your own server and choose a local AI model, and nothing leaves your network. Using a cloud model is your choice per question, and only the passages needed for the answer are sent.
              </p>
            </div>
            <ul className="space-y-3 text-sm">
              {["Separate, private workspace for each team", "Local AI models for sensitive documents", "Open source (MIT): inspect it, host it, extend it", "Every answer traceable to its source passage"].map((item) => (
                <li key={item} className="flex items-center gap-3 rounded-xl bg-ink-50 px-4 py-3 dark:bg-ink-900">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-700 text-xs text-white">✓</span>{item}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="faq" className="mx-auto max-w-3xl scroll-mt-20 px-4 pb-20 sm:px-6">
          <h2 className="font-display text-3xl font-semibold">Questions</h2>
          <div className="mt-8 divide-y divide-ink-200 border-y border-ink-200 dark:divide-ink-800 dark:border-ink-800">
            {FAQ.map(([question, answer]) => (
              <details key={question} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium">
                  {question}
                  <span className="text-xl text-ink-400 transition group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 leading-7 text-ink-600 dark:text-ink-400">{answer}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="px-4 pb-20 sm:px-6">
          <div className="mx-auto max-w-6xl rounded-3xl bg-gradient-to-br from-brand-800 via-brand-700 to-amber-700 px-8 py-14 text-center text-white">
            <h2 className="font-display text-3xl font-semibold sm:text-4xl">Start asking your documents</h2>
            <p className="mx-auto mt-3 max-w-xl text-lg text-white/85">Set up a workspace, add a few documents, and ask your first question in minutes.</p>
            <Link to={start} className="mt-8 inline-flex h-12 items-center gap-2 rounded-xl bg-white px-6 font-semibold text-brand-800 shadow-lg hover:bg-brand-50">
              {startLabel} <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-ink-100 dark:border-ink-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-8 text-sm text-ink-500 sm:px-6">
          <Logo className="text-ink-900 dark:text-white" />
          <span>Version {config?.version ?? ""} · MIT license</span>
          <Link to="/privacy" className="ml-auto hover:text-ink-900 dark:hover:text-white">Privacy</Link>
          <Link to="/terms" className="hover:text-ink-900 dark:hover:text-white">Terms</Link>
          <a href="https://github.com/fewzfewz/AfriSearch_AI_App_Starter" className="hover:text-ink-900 dark:hover:text-white">GitHub</a>
          <a href="/api/docs" className="hover:text-ink-900 dark:hover:text-white">API</a>
        </div>
      </footer>
    </div>
  );
}
