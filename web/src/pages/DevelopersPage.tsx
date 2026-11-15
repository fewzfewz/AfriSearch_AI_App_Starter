import { ArrowRight, Check, Copy, MessagesSquare, Terminal } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { PublicFooter, PublicHeader } from "../components/PublicNav";
import { Badge } from "../components/ui";

export function DevelopersPage() {
  const [activeTab, setActiveTab] = useState<"curl" | "python" | "typescript">("curl");
  const [copiedSection, setCopiedSection] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSection(id);
    setTimeout(() => setCopiedSection(null), 2000);
  };

  const curlCode = `# 1. Ask a question and receive a grounded answer with citations
curl -X POST "https://your-domain.com/api/v1/ask" \\
  -H "Authorization: Bearer afri_live_YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "question": "What is the recommended coffee drying time?",
    "top_k": 5,
    "rerank": true
  }'

# 2. Directly perform multilingual semantic document search
curl -X POST "https://your-domain.com/api/v1/search" \\
  -H "Authorization: Bearer afri_live_YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "የቡና ማድረቂያ መመሪያ",
    "top_k": 3
  }'`;

  const pythonCode = `import requests

API_KEY = "afri_live_YOUR_API_KEY"
BASE_URL = "https://your-domain.com/api/v1"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Ask question with verifiable citations
def ask_afrisearch(question: str, workspace_id: str = None):
    payload = {
        "question": question,
        "workspace_id": workspace_id,
        "top_k": 5,
        "rerank": True
    }
    response = requests.post(f"{BASE_URL}/ask", headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    
    print("Answer:", data["answer"])
    print("\\nSources Cited:")
    for source in data.get("sources", []):
        print(f"- [{source.get('source_id')}] (page {source.get('page')}): {source.get('filename')}")
    return data

if __name__ == "__main__":
    ask_afrisearch("What are the primary symptoms of leaf rust in Amharic documents?")`;

  const tsCode = `// TypeScript / Modern JavaScript integration
const API_KEY = "afri_live_YOUR_API_KEY";
const BASE_URL = "https://your-domain.com/api/v1";

interface AskResponse {
  question: string;
  answer: string | null;
  sources: Array<{
    source_id: string;
    filename: string;
    page: number | null;
    text: string;
    score?: number;
  }>;
  covered: boolean;
}

async function queryKnowledgeBase(question: string): Promise<AskResponse> {
  const response = await fetch(\`\${BASE_URL}/ask\`, {
    method: "POST",
    headers: {
      "Authorization": \`Bearer \${API_KEY}\`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      top_k: 5,
      rerank: true,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "API Error" }));
    throw new Error(error.detail || \`Error \${response.status}\`);
  }

  return response.json();
}

// Example usage
queryKnowledgeBase("What are the storage guidelines for maize?")
  .then((res) => {
    console.log("AI Answer:", res.answer);
    console.log("Citations:", res.sources.length);
  });`;

  const widgetSnippet = `<!-- Add this container anywhere on your website -->
<div id="afrisearch-widget" style="position:fixed;bottom:20px;right:20px;z-index:9999;">
  <button id="afri-toggle-btn" style="background:#b45309;color:white;border:none;border-radius:50px;padding:12px 20px;font-weight:bold;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,0.25);">
    💬 Ask Our Knowledge Base
  </button>
  
  <div id="afri-chat-box" style="display:none;width:360px;height:480px;background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,0.2);margin-bottom:12px;overflow:hidden;flex-direction:column;font-family:sans-serif;border:1px solid #e5e7eb;">
    <div style="background:#b45309;color:white;padding:14px;font-weight:bold;display:flex;justify-content:between;">
      <span>Customer Support Assistant</span>
    </div>
    <div id="afri-messages" style="flex:1;padding:14px;overflow-y:auto;font-size:14px;display:flex;flex-direction:column;gap:8px;"></div>
    <div style="padding:10px;border-top:1px solid #eee;display:flex;gap:6px;">
      <input id="afri-input" placeholder="Ask a question..." style="flex:1;border:1px solid #ddd;border-radius:8px;padding:8px 10px;font-size:14px;outline:none;" />
      <button id="afri-send" style="background:#b45309;color:white;border:none;border-radius:8px;padding:0 12px;cursor:pointer;">Send</button>
    </div>
  </div>
</div>

<script>
(function() {
  const API_KEY = "afri_live_YOUR_API_KEY";
  const ENDPOINT = "https://your-domain.com/api/v1/ask";
  
  const toggleBtn = document.getElementById("afri-toggle-btn");
  const chatBox = document.getElementById("afri-chat-box");
  const messagesDiv = document.getElementById("afri-messages");
  const input = document.getElementById("afri-input");
  const sendBtn = document.getElementById("afri-send");

  toggleBtn.onclick = () => {
    chatBox.style.display = chatBox.style.display === "none" ? "flex" : "none";
  };

  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    
    messagesDiv.innerHTML += \`<div style="align-self:flex-end;background:#f3f4f6;padding:8px 12px;border-radius:12px;max-width:85%;">\${text}</div>\`;
    const loadingId = "load-" + Date.now();
    messagesDiv.innerHTML += \`<div id="\${loadingId}" style="align-self:flex-start;color:#888;font-style:italic;">Searching documents...</div>\`;
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    try {
      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Authorization": "Bearer " + API_KEY, "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, top_k: 4, rerank: true })
      });
      const data = await res.json();
      document.getElementById(loadingId).remove();
      
      let answer = data.answer || "I could not find relevant information in our knowledge base.";
      let citationsHtml = (data.sources || []).map((s, idx) => 
        \`<span style="display:inline-block;background:#fef3c7;color:#92400e;font-size:11px;padding:2px 6px;border-radius:4px;margin-right:4px;">[\${idx+1}] \${s.filename}</span>\`
      ).join(" ");
      
      messagesDiv.innerHTML += \`<div style="align-self:flex-start;background:#fffbeb;border:1px solid #fde68a;padding:10px 12px;border-radius:12px;max-width:85%;line-height:1.4;">
        <div>\${answer}</div>
        \${citationsHtml ? '<div style="margin-top:6px;border-top:1px solid #fef3c7;padding-top:4px;">' + citationsHtml + '</div>' : ''}
      </div>\`;
    } catch (e) {
      document.getElementById(loadingId).innerText = "Error querying knowledge base.";
    }
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  sendBtn.onclick = sendMessage;
  input.onkeypress = (e) => { if (e.key === "Enter") sendMessage(); };
})();
</script>`;

  return (
    <div className="min-h-screen bg-ink-50/50 dark:bg-ink-950">
      <PublicHeader />

      <main className="py-16 sm:py-24">
        {/* Hero */}
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="max-w-3xl">
            <Badge tone="blue" className="mb-4 inline-flex items-center gap-1.5 px-3 py-1 text-sm font-semibold">
              <Terminal className="h-4 w-4" /> AfriSearch Developer Platform
            </Badge>
            <h1 className="font-display text-4xl font-bold tracking-tight text-ink-950 dark:text-white sm:text-5xl">
              Build with multilingual cited AI
            </h1>
            <p className="mt-4 text-lg text-ink-600 dark:text-ink-300 leading-relaxed">
              Integrate AfriSearch semantic document search, multilingual retrieval (94 languages), and hallucination-free cited question-answering directly into your applications, mobile clients, and live customer service chatbots.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <Link
                to="/pricing"
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand-700 px-5 text-sm font-semibold text-white shadow hover:bg-brand-800 transition"
              >
                Get Developer Access <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href="/api/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-11 items-center gap-2 rounded-xl border border-ink-200 bg-white px-5 text-sm font-semibold text-ink-700 hover:bg-ink-50 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-300 dark:hover:bg-ink-800 transition"
              >
                Interactive OpenAPI Docs <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </div>
        </div>

        {/* 3 Step Integration Quickstart */}
        <div className="mx-auto mt-16 max-w-6xl px-4 sm:px-6">
          <div className="grid gap-6 md:grid-cols-3">
            <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-sm dark:border-ink-800 dark:bg-ink-900">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-300 font-bold">
                1
              </div>
              <h3 className="mt-4 font-semibold text-ink-950 dark:text-white text-lg">
                Generate API Key
              </h3>
              <p className="mt-2 text-sm text-ink-500 dark:text-ink-400 leading-relaxed">
                On any Pro or Business workspace, navigate to <strong>Settings → Developer API Keys</strong> to generate a live key with optional workspace scoping.
              </p>
            </div>

            <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-sm dark:border-ink-800 dark:bg-ink-900">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-300 font-bold">
                2
              </div>
              <h3 className="mt-4 font-semibold text-ink-950 dark:text-white text-lg">
                Authenticate Requests
              </h3>
              <p className="mt-2 text-sm text-ink-500 dark:text-ink-400 leading-relaxed">
                Pass your key in standard HTTP headers as either <code className="text-xs bg-ink-100 dark:bg-ink-800 px-1.5 py-0.5 rounded">Authorization: Bearer afri_live_*</code> or <code className="text-xs bg-ink-100 dark:bg-ink-800 px-1.5 py-0.5 rounded">X-API-Key: afri_live_*</code>.
              </p>
            </div>

            <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-sm dark:border-ink-800 dark:bg-ink-900">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-300 font-bold">
                3
              </div>
              <h3 className="mt-4 font-semibold text-ink-950 dark:text-white text-lg">
                Retrieve & Synthesize
              </h3>
              <p className="mt-2 text-sm text-ink-500 dark:text-ink-400 leading-relaxed">
                Call <code className="text-xs bg-ink-100 dark:bg-ink-800 px-1.5 py-0.5 rounded">/api/v1/ask</code> for answers with verified page citations, or <code className="text-xs bg-ink-100 dark:bg-ink-800 px-1.5 py-0.5 rounded">/api/v1/search</code> for pure semantic search.
              </p>
            </div>
          </div>
        </div>

        {/* Code Snippets Section */}
        <section className="mx-auto mt-20 max-w-6xl px-4 sm:px-6">
          <div className="rounded-3xl border border-ink-800 bg-ink-900 shadow-2xl overflow-hidden">
            {/* Header tab controls */}
            <div className="flex items-center justify-between border-b border-ink-800 px-6 py-4 bg-ink-950">
              <div className="flex items-center gap-2">
                <div className="flex gap-1.5 mr-4">
                  <span className="h-3 w-3 rounded-full bg-rose-500" />
                  <span className="h-3 w-3 rounded-full bg-amber-500" />
                  <span className="h-3 w-3 rounded-full bg-emerald-500" />
                </div>
                <button
                  type="button"
                  onClick={() => setActiveTab("curl")}
                  className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                    activeTab === "curl"
                      ? "bg-brand-700 text-white"
                      : "text-ink-400 hover:text-white"
                  }`}
                >
                  cURL
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("python")}
                  className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                    activeTab === "python"
                      ? "bg-brand-700 text-white"
                      : "text-ink-400 hover:text-white"
                  }`}
                >
                  Python
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("typescript")}
                  className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                    activeTab === "typescript"
                      ? "bg-brand-700 text-white"
                      : "text-ink-400 hover:text-white"
                  }`}
                >
                  TypeScript
                </button>
              </div>

              <button
                type="button"
                onClick={() => {
                  const code = activeTab === "curl" ? curlCode : activeTab === "python" ? pythonCode : tsCode;
                  copyToClipboard(code, "code-tab");
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-ink-700 bg-ink-800 px-3 py-1.5 text-xs font-medium text-ink-300 hover:text-white transition"
              >
                {copiedSection === "code-tab" ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-400" /> Copied!
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" /> Copy Code
                  </>
                )}
              </button>
            </div>

            {/* Code Body */}
            <div className="p-6 overflow-x-auto text-sm font-mono text-ink-200 leading-relaxed">
              <pre>
                <code>
                  {activeTab === "curl" && curlCode}
                  {activeTab === "python" && pythonCode}
                  {activeTab === "typescript" && tsCode}
                </code>
              </pre>
            </div>
          </div>
        </section>

        {/* API Endpoint Reference */}
        <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
          <div className="mb-10">
            <h2 className="font-display text-3xl font-bold text-ink-950 dark:text-white">
              Core Developer Endpoints
            </h2>
            <p className="mt-2 text-ink-600 dark:text-ink-400">
              Clean, JSON-first REST endpoints for your backend services and client applications.
            </p>
          </div>

          <div className="space-y-6">
            {/* POST /api/v1/ask */}
            <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-sm dark:border-ink-800 dark:bg-ink-900">
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-lg bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                  POST
                </span>
                <code className="text-base font-bold text-ink-900 dark:text-white">
                  /api/v1/ask
                </code>
                <span className="text-sm text-ink-500">
                  Ask a question and receive a grounded answer with verifiable citations
                </span>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-500 mb-2">Request Body</h4>
                  <pre className="rounded-xl bg-ink-50 p-4 text-xs font-mono text-ink-800 dark:bg-ink-950 dark:text-ink-200 overflow-x-auto border border-ink-200 dark:border-ink-800">
{`{
  "question": "string (required, max 4000 chars)",
  "workspace_id": "string (optional, defaults to primary)",
  "top_k": 5,
  "rerank": true,
  "tags": ["extension", "crops"]
}`}
                  </pre>
                </div>
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-500 mb-2">Response Example</h4>
                  <pre className="rounded-xl bg-ink-50 p-4 text-xs font-mono text-ink-800 dark:bg-ink-950 dark:text-ink-200 overflow-x-auto border border-ink-200 dark:border-ink-800">
{`{
  "question": "What is the drying time?",
  "answer": "Dry on raised beds for 2-3 weeks [S1].",
  "sources": [
    {
      "source_id": "doc_123",
      "filename": "coffee_guide.pdf",
      "page": 2,
      "text": "Dry beans for two to three weeks..."
    }
  ],
  "covered": true,
  "model": "claude-3-5-sonnet"
}`}
                  </pre>
                </div>
              </div>
            </div>

            {/* POST /api/v1/search */}
            <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-sm dark:border-ink-800 dark:bg-ink-900">
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-lg bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                  POST
                </span>
                <code className="text-base font-bold text-ink-900 dark:text-white">
                  /api/v1/search
                </code>
                <span className="text-sm text-ink-500">
                  Semantic document retrieval without generating natural language text
                </span>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-500 mb-2">Request Body</h4>
                  <pre className="rounded-xl bg-ink-50 p-4 text-xs font-mono text-ink-800 dark:bg-ink-950 dark:text-ink-200 overflow-x-auto border border-ink-200 dark:border-ink-800">
{`{
  "query": "string (required, query in any of 94 languages)",
  "workspace_id": "string (optional)",
  "top_k": 5,
  "rerank": true
}`}
                  </pre>
                </div>
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-500 mb-2">Response Example</h4>
                  <pre className="rounded-xl bg-ink-50 p-4 text-xs font-mono text-ink-800 dark:bg-ink-950 dark:text-ink-200 overflow-x-auto border border-ink-200 dark:border-ink-800">
{`{
  "query": "የቡና ማድረቂያ መመሪያ",
  "workspace_id": "ws_abc",
  "count": 2,
  "sources": [
    {
      "source_id": "doc_123",
      "filename": "coffee_guide.pdf",
      "score": 0.892,
      "text": "..."
    }
  ]
}`}
                  </pre>
                </div>
              </div>
            </div>

            {/* GET /api/v1/workspaces */}
            <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-sm dark:border-ink-800 dark:bg-ink-900">
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-lg bg-blue-100 px-2.5 py-1 text-xs font-bold text-blue-800 dark:bg-blue-950 dark:text-blue-300">
                  GET
                </span>
                <code className="text-base font-bold text-ink-900 dark:text-white">
                  /api/v1/workspaces
                </code>
                <span className="text-sm text-ink-500">
                  List workspaces authorized for the API token
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Tutorial: Customer Support Widget */}
        <section className="mx-auto mt-28 max-w-6xl px-4 sm:px-6">
          <div className="rounded-3xl border border-amber-200 bg-amber-50/60 p-8 dark:border-amber-900/60 dark:bg-amber-950/20 sm:p-12">
            <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300">
              <MessagesSquare className="h-6 w-6" />
              <span className="text-sm font-bold uppercase tracking-wider">Tutorial & Widget Guide</span>
            </div>
            <h2 className="mt-3 font-display text-3xl font-bold text-ink-950 dark:text-white">
              Embed a Live Customer Support Assistant
            </h2>
            <p className="mt-3 max-w-2xl text-ink-700 dark:text-ink-300 leading-relaxed">
              Add a responsive floating customer support bot to your company website or portal in under 5 minutes. The widget connects directly to your workspace documentation and handles questions in English, Amharic, Swahili, and 90+ other languages.
            </p>

            <div className="mt-8">
              <div className="flex items-center justify-between rounded-t-xl bg-ink-900 px-5 py-3 text-white border-b border-ink-800">
                <span className="text-xs font-mono text-ink-300">support-widget.html</span>
                <button
                  type="button"
                  onClick={() => copyToClipboard(widgetSnippet, "widget-snippet")}
                  className="inline-flex items-center gap-1.5 rounded bg-ink-800 px-2.5 py-1 text-xs font-medium text-ink-200 hover:text-white transition"
                >
                  {copiedSection === "widget-snippet" ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-400" /> Copied Widget Code!
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" /> Copy Full HTML Widget
                    </>
                  )}
                </button>
              </div>
              <pre className="rounded-b-xl bg-ink-950 p-5 text-xs font-mono text-ink-300 overflow-x-auto max-h-96">
                <code>{widgetSnippet}</code>
              </pre>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
