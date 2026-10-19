// Privacy notice and terms of use.
//
// These describe what this software actually stores and sends. They are a starting
// template, not legal advice: have a lawyer review them for your organisation and
// the countries you operate in (e.g. Ethiopia's Personal Data Protection
// Proclamation 2024, Kenya's Data Protection Act 2019) before launch.
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Logo } from "../components/ui";
import { useAuth } from "../lib/auth";

const UPDATED = "20 October 2026";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="mt-2 space-y-3 leading-7 text-ink-700 dark:text-ink-300">{children}</div>
    </section>
  );
}

function useParties() {
  const { config } = useAuth();
  const org = config?.org_name ?? "[Your organisation]";
  const contact = config?.contact_email ?? "[contact email]";
  const email = <a className="text-brand-700 underline dark:text-brand-400" href={`mailto:${contact}`}>{contact}</a>;
  return { org, email };
}

function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-ink-100 dark:border-ink-900">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-4 sm:px-6">
          <Link to="/"><Logo /></Link>
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink-500 hover:text-ink-900 dark:hover:text-white">
            <ArrowLeft className="h-4 w-4" /> Home
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 pb-20 pt-10 sm:px-6">
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-ink-500">Last updated {UPDATED}</p>
        {children}
        <p className="mt-12 border-t border-ink-200 pt-6 text-sm text-ink-500 dark:border-ink-800">
          See also: <Link to="/privacy" className="underline">Privacy notice</Link> · <Link to="/terms" className="underline">Terms of use</Link>
        </p>
      </main>
    </div>
  );
}

export function PrivacyPage() {
  const { org, email } = useParties();
  return (
    <Shell title="Privacy notice">
      <Section title="Who we are">
        <p>AfriSearch is operated by {org}. Questions about your data: {email}.</p>
      </Section>
      <Section title="What we store">
        <ul className="list-disc space-y-2 pl-5">
          <li><strong>Your account:</strong> name and email address, from the sign-in service we use (Supabase).</li>
          <li><strong>Your documents:</strong> the files you upload, the text read from them (including by OCR), and a search index built from that text.</li>
          <li><strong>Your questions and answers:</strong> saved chats, the passages each answer used, and ratings and comments you give.</li>
          <li><strong>Technical records:</strong> server logs (time, address, which page or action) for security and troubleshooting, and, if enabled, error reports that never include your documents or questions.</li>
        </ul>
      </Section>
      <Section title="How your documents are used">
        <p>Your documents are used only to answer questions asked in your workspace. People you add to a workspace can search its documents and see its ratings; your chats are visible only to you.</p>
        <p>When you choose a cloud AI model (Claude by Anthropic, ChatGPT by OpenAI, or Gemini by Google), your question and the passages needed to answer it are sent to that company to write the answer. They may be processed outside your country. With a local model, or with "Find passages only", nothing leaves our servers. We don't use your documents to train AI models, and we don't sell your data.</p>
      </Section>
      <Section title="Where and how long">
        <p>Data is stored on the servers that run AfriSearch for {org}. It is kept until you delete it or your account. Backups are kept for up to 14 days, after which deleted data is gone from them too.</p>
      </Section>
      <Section title="Your rights">
        <p>You can <strong>download</strong> all your data and <strong>delete</strong> your account at any time under Settings → Account. You can also ask us to correct your data, or object to how we use it, at {email}. If you think we handle your data unlawfully, you can complain to your country's data protection authority.</p>
      </Section>
      <Section title="Security">
        <p>Connections are encrypted (HTTPS), each workspace's data is kept apart, and access requires signing in. No system is perfectly secure; tell us at {email} if you find a problem.</p>
      </Section>
      <Section title="Changes">
        <p>If we change this notice in a way that matters, we'll tell you in the app or by email before it takes effect.</p>
      </Section>
    </Shell>
  );
}

export function TermsPage() {
  const { org, email } = useParties();
  return (
    <Shell title="Terms of use">
      <Section title="The service">
        <p>AfriSearch, operated by {org}, lets you upload documents and ask questions about them. By creating an account you agree to these terms.</p>
      </Section>
      <Section title="Your content">
        <p>You keep all rights to the documents you upload. Only upload documents you have the right to use and share with the people in your workspace, and that don't contain other people's personal data unless you're allowed to process it. You give us permission to store and process your documents only to run the service for you.</p>
      </Section>
      <Section title="Answers can be wrong">
        <p>Answers are generated by AI from your documents and may be incomplete or wrong, even when they cite a source. Check important information against the cited passages before relying on it, especially for health, legal, financial or safety decisions.</p>
      </Section>
      <Section title="Acceptable use">
        <ul className="list-disc space-y-2 pl-5">
          <li>Don't upload illegal content, malware, or content you aren't allowed to share.</li>
          <li>Don't try to access other people's workspaces or disrupt the service; usage limits apply to keep it fair for everyone.</li>
          <li>Don't use the service to harm, harass or deceive others.</li>
        </ul>
      </Section>
      <Section title="Accounts and ending">
        <p>You can delete your account at any time in Settings. We may suspend accounts that break these terms, and we'll tell you why when we can.</p>
      </Section>
      <Section title="Liability">
        <p>The service is provided as is. To the extent the law allows, {org} isn't liable for losses caused by relying on answers, or by interruptions or data loss; keep your own copies of important documents.</p>
      </Section>
      <Section title="Contact and law">
        <p>Questions: {email}. These terms are governed by the laws of [country].</p>
      </Section>
    </Shell>
  );
}
