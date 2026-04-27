"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Message {
  role: "user" | "assistant";
  content: string;
  artifact?: string;
  imagePreview?: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STARTER_PROMPTS = [
  { icon: "⚡", label: "MIG Setup", text: "How do I set up for MIG welding on 3mm mild steel?" },
  { icon: "🔧", label: "Troubleshoot", text: "I'm getting porosity in my welds — what could be wrong?" },
  { icon: "🔌", label: "Polarity", text: "Which polarity do I use for each welding process?" },
  { icon: "⏱️", label: "Duty Cycle", text: "What's the duty cycle for MIG at 200A on 240V?" },
];

// ─── Theme Hook ───
function useTheme() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    // Check localStorage on mount
    const stored = localStorage.getItem("vulcan-theme");
    if (stored === "light") {
      setDark(false);
      document.documentElement.classList.remove("dark");
    } else {
      setDark(true);
      document.documentElement.classList.add("dark");
    }
  }, []);

  const toggle = useCallback(() => {
    setDark((prev) => {
      const next = !prev;
      if (next) {
        document.documentElement.classList.add("dark");
        localStorage.setItem("vulcan-theme", "dark");
      } else {
        document.documentElement.classList.remove("dark");
        localStorage.setItem("vulcan-theme", "light");
      }
      return next;
    });
  }, []);

  return { dark, toggle };
}

// ─── Theme Toggle Button ───
function ThemeToggle({ dark, onToggle }: { dark: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="p-1.5 rounded-md transition-colors"
      style={{
        color: "var(--text-muted)",
        background: "transparent",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--bg-secondary)";
        e.currentTarget.style.color = "var(--text-secondary)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.color = "var(--text-muted)";
      }}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {dark ? (
        // Sun icon
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="5" />
          <line x1="12" y1="1" x2="12" y2="3" />
          <line x1="12" y1="21" x2="12" y2="23" />
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="1" y1="12" x2="3" y2="12" />
          <line x1="21" y1="12" x2="23" y2="12" />
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
      ) : (
        // Moon icon
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

// ─── Artifact Renderer ───
function ArtifactRenderer({ code }: { code: string }) {
  const [hasError, setHasError] = useState(false);
  const [iframeHeight, setIframeHeight] = useState(360);

  const processedCode = (() => {
    const match = code.match(/function\s+(\w+)\s*\(/);
    const funcName = match ? match[1] : null;
    let processed = code
      .replace(/export default function/, "function")
      .replace(/export default/, "");
    if (funcName && funcName !== "Component") {
      processed += `\nvar Component = ${funcName};`;
    }
    // Prepend React hooks destructuring + render call
    const prefix = `var useState = React.useState, useEffect = React.useEffect, useRef = React.useRef, useMemo = React.useMemo, useCallback = React.useCallback;\n`;
    const suffix = `\nReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Component));`;
    return prefix + processed + suffix;
  })();

  const bodyStyle = [
    "@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap');",
    "body{margin:0;padding:16px;background:#141414;color:#e5e5e5;font-family:'Geist',system-ui,-apple-system,sans-serif}",
    "select,input,option{color:#e5e5e5!important;background:#262626!important;border:1px solid #404040;padding:6px 10px;border-radius:6px;font-size:14px;font-family:inherit}",
    "select{min-width:140px;cursor:pointer}",
    "select:focus,input:focus{outline:2px solid #f97316;outline-offset:1px;border-color:#f97316}",
    "label{font-weight:500;font-size:14px;color:#a3a3a3}",
    "p,h1,h2,h3,h4,h5,span,li,div{color:#e5e5e5}",
    "h1,h2,h3{color:#fdba74}",
    "table{width:100%;border-collapse:collapse;font-size:13px}",
    "th{background:#292929;color:#fdba74!important;padding:10px 12px;text-align:left;font-weight:600;border-bottom:1px solid #404040}",
    "td{padding:10px 12px;border-bottom:1px solid #262626;color:#d4d4d4}",
    "tr:hover td{background:#1a1a1a}",
    "button{cursor:pointer;padding:8px 16px;border-radius:6px;font-size:14px;font-weight:500;border:1px solid #404040;background:#262626;color:#e5e5e5;transition:all 0.15s;font-family:inherit}",
    "button:hover{border-color:#f97316;color:#fdba74}",
    "button.active,button[style*='background: rgb(239']{background:#f97316!important;color:#fff!important;border-color:#f97316!important}",
    ".warning,.important{background:#1a1a0a;border-left:3px solid #f97316;padding:8px 12px;border-radius:4px}",
  ].join("");

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === "resize" && typeof e.data.height === "number") {
        setIframeHeight(Math.min(Math.max(e.data.height + 32, 200), 520));
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>${bodyStyle}
#loading{display:flex;align-items:center;justify-content:center;height:100px;color:#a3a3a3;font-family:system-ui;font-size:13px}
#loading .dot{width:6px;height:6px;background:#f97316;border-radius:50%;margin:0 3px;animation:bounce 1s infinite}
#loading .dot:nth-child(2){animation-delay:0.15s}
#loading .dot:nth-child(3){animation-delay:0.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-8px)}}
</style>
</head>
<body>
<div id="root"><div id="loading"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>
<script>
// Sequential script loader — ensures each CDN dependency loads before the next
var scripts = [
  'https://unpkg.com/react@18/umd/react.production.min.js',
  'https://unpkg.com/react-dom@18/umd/react-dom.production.min.js',
  'https://unpkg.com/@babel/standalone@7.23.5/babel.min.js'
];
var loaded = 0;
function loadNext() {
  if (loaded >= scripts.length) { runApp(); return; }
  var s = document.createElement('script');
  s.src = scripts[loaded];
  s.onload = function() { loaded++; loadNext(); };
  s.onerror = function() {
    // Retry once on failure
    var r = document.createElement('script');
    r.src = scripts[loaded];
    r.onload = function() { loaded++; loadNext(); };
    r.onerror = function() {
      document.getElementById('root').innerHTML = '<div style="color:#f97316;padding:20px;font-size:13px">Failed to load dependencies. Please retry.</div>';
    };
    document.head.appendChild(r);
  };
  document.head.appendChild(s);
}
function runApp() {
  try {
    var code = ${JSON.stringify(processedCode)};
    var transformed = Babel.transform(code, { presets: ['react'] }).code;
    var fn = new Function('React', 'ReactDOM', transformed);
    fn(React, ReactDOM);
    // Auto-resize
    var ro = new ResizeObserver(function() {
      var h = document.getElementById('root') ? document.getElementById('root').scrollHeight : 0;
      if (h) window.parent.postMessage({ type: 'resize', height: h }, '*');
    });
    ro.observe(document.getElementById('root'));
  } catch(e) {
    document.getElementById('root').innerHTML = '<div style="color:#dc2626;padding:20px;font-family:monospace;font-size:13px"><b>Render error:</b><br/>' + e.message + '</div>';
  }
}
loadNext();
<\/script>
</body>
</html>`;

  if (hasError) {
    return (
      <div className="mt-2 p-4 rounded-lg text-sm" style={{ background: "rgba(153,27,27,0.2)", border: "1px solid rgba(185,28,28,0.5)", color: "#fca5a5" }}>
        Artifact failed to render. Try asking the question again.
      </div>
    );
  }

  return (
    <div className="mt-3 max-w-[75ch]">
      <div className="flex items-center gap-2 mb-1.5">
        <div className="w-3 h-3 rounded-sm" style={{ background: "var(--accent)", opacity: 0.8 }} />
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>Interactive Tool</span>
      </div>
      <iframe
        srcDoc={html}
        className="w-full rounded-lg"
        style={{ height: `${iframeHeight}px`, transition: "height 0.2s ease", border: "1px solid var(--border-subtle)", background: "#141414" }}
        sandbox="allow-scripts"
        onError={() => setHasError(true)}
      />
    </div>
  );
}

// ─── Copy Button ───
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="opacity-0 group-hover:opacity-100 transition-opacity duration-150 absolute top-2 right-2 p-1.5 rounded-md"
      style={{ background: "var(--copy-btn-bg)", color: "var(--copy-btn-text)" }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--copy-btn-hover)";
        e.currentTarget.style.color = "var(--copy-btn-hover-text)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "var(--copy-btn-bg)";
        e.currentTarget.style.color = "var(--copy-btn-text)";
      }}
      title="Copy response"
    >
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
      )}
    </button>
  );
}

// ─── Message Bubble ───
function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-5`}>
      <div className={`w-full ${isUser ? "ml-8 sm:ml-16 flex justify-end" : "mr-4 sm:mr-8"}`}>
        {!isUser && (
          <div className="flex items-center gap-2 mb-1.5">
            <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0" style={{ background: "var(--accent)" }}>
              <span className="text-white text-[10px] font-bold">V</span>
            </div>
            <span className="text-xs font-medium tracking-wide" style={{ color: "var(--accent-text-light)" }}>VULCAN AI</span>
          </div>
        )}

        <div
          className={`relative group rounded-2xl px-4 py-3 ${isUser ? "w-fit max-w-2xl ml-auto" : ""}`}
          style={{
            background: isUser ? "var(--bg-bubble-user)" : "var(--bg-bubble-ai)",
            color: isUser ? "var(--text-on-accent)" : "var(--text-primary)",
            border: isUser ? "none" : "1px solid var(--border-subtle)",
          }}
        >
          {!isUser && <CopyButton text={message.content} />}

          {message.imagePreview && (
            <div className="mb-2">
              <img src={message.imagePreview} alt="Uploaded" className="max-w-xs max-h-48 rounded-lg" style={{ border: "1px solid var(--border-subtle)" }} />
            </div>
          )}

          {isUser ? (
            message.content ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
            ) : null
          ) : (
            <div className="text-sm leading-relaxed">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-3 rounded-lg" style={{ border: `1px solid var(--table-border)` }}>
                      <table className="w-full text-sm border-collapse">{children}</table>
                    </div>
                  ),
                  thead: ({ children }) => (
                    <thead style={{ background: "var(--table-header-bg)", color: "var(--table-header-text)" }}>{children}</thead>
                  ),
                  th: ({ children }) => (
                    <th className="px-3 py-2 text-left text-xs font-semibold whitespace-nowrap" style={{ color: "var(--table-header-text)", borderBottom: "1px solid var(--table-border)" }}>{children}</th>
                  ),
                  td: ({ children }) => (
                    <td className="px-3 py-2" style={{ borderBottom: "1px solid var(--table-border)", color: "var(--table-text)" }}>{children}</td>
                  ),
                  tr: ({ children }) => (
                    <tr style={{ transition: "background 0.1s" }} onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--table-hover)"; }} onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>{children}</tr>
                  ),
                  code: ({ className, children, ...props }: React.ComponentProps<"code"> & { className?: string }) => {
                    const isBlock = className?.includes("language-");
                    if (isBlock) {
                      return (
                        <div className="my-3 rounded-lg overflow-hidden" style={{ border: "1px solid var(--border-subtle)" }}>
                          <div className="px-3 py-1.5 text-[10px] font-mono" style={{ background: "var(--code-block-header)", color: "var(--text-muted)", borderBottom: "1px solid var(--border-subtle)" }}>
                            {className?.replace("language-", "") || "code"}
                          </div>
                          <pre className="p-3 overflow-x-auto" style={{ background: "var(--code-block-bg)" }}>
                            <code className="text-sm font-mono" style={{ color: "var(--code-block-text)" }}>{children}</code>
                          </pre>
                        </div>
                      );
                    }
                    return (
                      <code className="px-1.5 py-0.5 rounded text-[13px] font-mono" style={{ background: "var(--code-bg)", color: "var(--code-text)" }} {...props}>{children}</code>
                    );
                  },
                  p: ({ children }) => (
                    <p className="mb-3 leading-relaxed last:mb-0" style={{ color: "var(--text-secondary)" }}>{children}</p>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-semibold" style={{ color: "var(--accent-text)" }}>{children}</strong>
                  ),
                  em: ({ children }) => (
                    <em style={{ color: "var(--text-secondary)" }}>{children}</em>
                  ),
                  ul: ({ children }) => (
                    <ul className="mb-3 ml-4 space-y-1.5 list-disc" style={{ markerColor: "var(--accent)" } as React.CSSProperties}>{children}</ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="mb-3 ml-4 space-y-1.5 list-decimal" style={{ markerColor: "var(--accent-text)" } as React.CSSProperties}>{children}</ol>
                  ),
                  li: ({ children }) => (
                    <li className="pl-1" style={{ color: "var(--text-secondary)" }}>{children}</li>
                  ),
                  h1: ({ children }) => (
                    <h1 className="text-lg font-semibold mb-2 mt-4 first:mt-0" style={{ color: "var(--accent-text)" }}>{children}</h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="text-base font-semibold mb-2 mt-3 first:mt-0" style={{ color: "var(--accent-text)" }}>{children}</h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="text-sm font-semibold mb-1.5 mt-3 first:mt-0" style={{ color: "var(--accent-text)" }}>{children}</h3>
                  ),
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 transition-colors" style={{ color: "var(--accent)" }}>{children}</a>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="pl-3 my-3 italic" style={{ borderLeft: "2px solid var(--accent)", opacity: 0.8, color: "var(--text-muted)" }}>{children}</blockquote>
                  ),
                  hr: () => <hr className="my-4" style={{ borderColor: "var(--border-subtle)" }} />,
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>
        {message.artifact && <ArtifactRenderer code={message.artifact} />}
      </div>
    </div>
  );
}

// ─── Main App ───
export default function Home() {
  const { dark, toggle: toggleTheme } = useTheme();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [selectedImage, setSelectedImage] = useState<{ base64: string; type: string; preview: string } | null>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const dragCountRef = useRef(0);
  const [dragOver, setDragOver] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll
  useEffect(() => {
    if (!showScrollBtn) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, showScrollBtn]);

  // Scroll detection
  useEffect(() => {
    const container = chatContainerRef.current;
    if (!container) return;
    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      setShowScrollBtn(scrollHeight - scrollTop - clientHeight > 120);
    };
    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, []);

  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, []);
  useEffect(() => { resizeTextarea(); }, [input, resizeTextarea]);

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  function parseArtifact(text: string) {
    const match = text.match(/<artifact type="react">([\s\S]*?)<\/artifact>/);
    if (match) {
      return { content: text.replace(/<artifact type="react">[\s\S]*?<\/artifact>/, "").trim(), artifact: match[1].trim() };
    }
    return { content: text };
  }

  function buildHistory(currentMessages: Message[]) {
    return currentMessages.map((msg) => ({
      role: msg.role,
      content: msg.artifact ? `${msg.content}\n<artifact type="react">${msg.artifact}</artifact>` : msg.content,
    }));
  }

  function handleImageSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type)) { setToast("Please upload a JPEG, PNG, or WebP image."); return; }
    if (file.size > 5 * 1024 * 1024) { setToast("Image must be under 5MB."); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setSelectedImage({ base64: dataUrl.split(",")[1], type: file.type, preview: dataUrl });
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  }

  function clearImage() { setSelectedImage(null); }

  function handleClearChat() {
    if (messages.length === 0) return;
    if (window.confirm("Start a new session? This will clear the current conversation.")) {
      setMessages([]); setStreamingText(""); setInput(""); setSelectedImage(null);
    }
  }

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    setShowScrollBtn(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type)) { setToast("Please drop a JPEG, PNG, or WebP image."); return; }
    if (file.size > 5 * 1024 * 1024) { setToast("Image must be under 5MB."); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setSelectedImage({ base64: dataUrl.split(",")[1], type: file.type, preview: dataUrl });
    };
    reader.readAsDataURL(file);
  }

  async function sendMessage(overrideText?: string) {
    const messageText = overrideText || input.trim();
    if ((!messageText && !selectedImage) || loading) return;

    const questionText = messageText || "Analyze this image in the context of the Vulcan OmniPro 220 welder. Describe what you see and provide relevant advice.";
    const isImageOnly = !messageText && !!selectedImage;
    const userMessage: Message = { role: "user", content: isImageOnly ? "" : questionText, imagePreview: selectedImage?.preview };
    setMessages((prev) => [...prev, userMessage]);
    setInput(""); setLoading(true); setStreamingText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const imageData = selectedImage;
    setSelectedImage(null);

    try {
      const history = buildHistory(messages);
      const body: Record<string, unknown> = { question: questionText, history };
      if (imageData) { body.image = imageData.base64; body.image_type = imageData.type; }

      const res = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        if (res.status === 429) throw new Error("Rate limited — the AI service is busy. Please wait a moment and try again.");
        throw new Error(`Server error: ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let accumulated = "";
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6);
          if (!jsonStr.trim()) continue;
          try {
            const event = JSON.parse(jsonStr);
            if (event.type === "token") {
              accumulated += event.text;
              let displayText = accumulated;
              const artifactStart = displayText.indexOf('<artifact type="react">');
              if (artifactStart !== -1) displayText = displayText.substring(0, artifactStart).trim();
              setStreamingText(displayText);
            }
          } catch { /* skip */ }
        }
      }

      const { content, artifact } = parseArtifact(accumulated);
      setMessages((prev) => [...prev, { role: "assistant", content, artifact }]);
      setStreamingText("");
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Unknown error";
      setToast(errorMsg);
      setMessages((prev) => [...prev, { role: "assistant", content: `**Connection error:** ${errorMsg}\n\nMake sure the Python backend is running on ${API_URL}` }]);
      setStreamingText("");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }

  const isEmpty = messages.length === 0 && !streamingText;

  return (
    <div
      className="min-h-screen flex flex-col relative"
      style={{ background: "var(--bg-primary)" }}
      onDragOver={(e) => { e.preventDefault(); }}
      onDragEnter={(e) => { e.preventDefault(); dragCountRef.current++; setDragOver(true); }}
      onDragLeave={() => { dragCountRef.current--; if (dragCountRef.current <= 0) { dragCountRef.current = 0; setDragOver(false); } }}
      onDrop={(e) => { dragCountRef.current = 0; handleDrop(e); }}
    >
      {/* Drag overlay */}
      {dragOver && (
        <div className="fixed inset-0 z-50 flex items-end justify-center pb-32"
          style={{ background: "rgba(0,0,0,0.3)" }}>
          <div className="px-6 py-3 rounded-xl border-2 border-dashed"
            style={{ background: "var(--bg-secondary)", borderColor: "var(--accent)", color: "var(--accent)" }}>
            <span className="text-base font-medium">Drop image to upload</span>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 animate-[slideDown_0.3s_ease-out]">
          <div className="px-4 py-2.5 rounded-lg text-sm shadow-lg flex items-center gap-3"
            style={{ background: "var(--toast-bg)", border: "1px solid var(--toast-border)", color: "var(--toast-text)" }}>
            <span>{toast}</span>
            <button onClick={() => setToast(null)} className="transition-colors" style={{ color: "var(--toast-text)", opacity: 0.7 }}>✕</button>
          </div>
        </div>
      )}

      {/* ── Header ── */}
      <div className="px-4 sm:px-6 py-3 flex items-center gap-3 backdrop-blur-sm sticky top-0 z-40"
        style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-primary)" }}>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: "var(--accent)" }}>
          <span className="text-white text-xs font-bold">V</span>
        </div>
        <div className="min-w-0">
          <h1 className="font-semibold text-sm truncate" style={{ color: "var(--text-primary)" }}>Vulcan OmniPro 220</h1>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>AI Welding Assistant</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {/* Theme toggle */}
          <ThemeToggle dark={dark} onToggle={toggleTheme} />

          {/* Clear chat */}
          {messages.length > 0 && (
            <button onClick={handleClearChat} className="p-1.5 rounded-md transition-colors"
              style={{ color: "var(--text-muted)" }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-secondary)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
              title="New session">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14" /></svg>
            </button>
          )}

          {/* Live indicator */}
          <div className="flex items-center gap-1.5 ml-1">
            <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>Live</span>
          </div>
        </div>
      </div>

      {/* ── Messages ── */}
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 relative">
        <div className="max-w-4xl mx-auto">
        {/* Empty state */}
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full min-h-[60vh] text-center px-4">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-6" style={{ background: "var(--accent)", boxShadow: "0 8px 24px rgba(249,115,22,0.2)" }}>
              <span className="text-white text-2xl font-bold">V</span>
            </div>
            <h2 className="text-xl font-semibold mb-1" style={{ color: "var(--text-primary)" }}>Vulcan OmniPro 220</h2>
            <p className="text-sm mb-8 max-w-sm" style={{ color: "var(--text-muted)" }}>
              Ask about setup, settings, troubleshooting, or upload a photo of your weld for analysis.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
              {STARTER_PROMPTS.map((prompt) => (
                <button key={prompt.label} onClick={() => sendMessage(prompt.text)}
                  className="flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all group"
                  style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)" }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)"; }}>
                  <span className="text-lg">{prompt.icon}</span>
                  <div>
                    <div className="text-sm font-medium transition-colors" style={{ color: "var(--text-secondary)" }}>{prompt.label}</div>
                    <div className="text-xs leading-snug mt-0.5" style={{ color: "var(--text-muted)" }}>{prompt.text}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => <MessageBubble key={i} message={msg} />)}

        {/* Streaming */}
        {streamingText && (
          <div className="flex justify-start mb-5">
            <div className="w-full mr-4 sm:mr-8">
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0" style={{ background: "var(--accent)" }}>
                  <span className="text-white text-[10px] font-bold">V</span>
                </div>
                <span className="text-xs font-medium tracking-wide" style={{ color: "var(--accent-text-light)" }}>VULCAN AI</span>
              </div>
              <div className="rounded-2xl px-4 py-3 max-w-[75ch]" style={{ background: "var(--bg-bubble-ai)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
                <div className="text-sm leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
                  <span className="inline-block w-1.5 h-4 ml-0.5 animate-pulse rounded-sm align-text-bottom" style={{ background: "var(--accent)" }} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Loading dots */}
        {loading && !streamingText && (
          <div className="flex justify-start mb-5">
            <div className="flex items-center gap-2 mb-1.5">
              <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0" style={{ background: "var(--accent)" }}>
                <span className="text-white text-[10px] font-bold">V</span>
              </div>
            </div>
            <div className="rounded-2xl px-4 py-3 ml-2" style={{ background: "var(--bg-bubble-ai)", border: "1px solid var(--border-subtle)" }}>
              <div className="flex gap-1.5 items-center">
                <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: "var(--accent)", animationDelay: "0ms" }} />
                <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: "var(--accent)", animationDelay: "150ms" }} />
                <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: "var(--accent)", animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
        </div>
      </div>

      {/* Scroll-to-bottom */}
      {showScrollBtn && (
        <button onClick={scrollToBottom}
          className="absolute bottom-32 left-1/2 -translate-x-1/2 z-30 p-2 rounded-full shadow-lg transition-all"
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
        </button>
      )}

      {/* Image preview bar */}
      {selectedImage && (
        <div className="px-4 sm:px-6 py-2" style={{ borderTop: "1px solid var(--border-primary)", background: "var(--bg-overlay)" }}>
          <div className="flex items-center gap-3 max-w-3xl mx-auto">
            <img src={selectedImage.preview} alt="Selected" className="w-14 h-14 object-cover rounded-lg" style={{ border: "1px solid var(--border-secondary)" }} />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>Image attached</p>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>Add a question or just send</p>
            </div>
            <button onClick={clearImage} className="text-sm p-1.5 transition-colors rounded-md"
              style={{ color: "var(--text-muted)" }}
              title="Remove image">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            </button>
          </div>
        </div>
      )}

      {/* ── Input ── */}
      <div className="px-4 sm:px-6 py-3 backdrop-blur-sm" style={{ borderTop: "1px solid var(--border-primary)", background: "var(--bg-header)" }}>
        <div className="flex gap-2.5 max-w-3xl mx-auto items-end">
          <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={handleImageSelect} className="hidden" />

          {/* Upload btn */}
          <button onClick={() => fileInputRef.current?.click()} disabled={loading}
            className="p-2.5 rounded-xl transition-all flex-shrink-0 mb-0.5 disabled:opacity-50"
            style={{ background: "var(--bg-input)", border: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}
            title="Upload an image">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef} value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedImage ? "Ask about this image (or just hit Send)..." : "Ask about setup, settings, troubleshooting..."}
            rows={1}
            className="flex-1 rounded-xl px-4 py-2.5 text-sm resize-none overflow-hidden leading-relaxed focus:outline-none transition-colors"
            style={{
              background: "var(--bg-input)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-primary)",
              minHeight: "42px",
              maxHeight: "160px",
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
            onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border-subtle)"; }}
          />

          {/* Send btn */}
          <button onClick={() => sendMessage()}
            disabled={loading || (!input.trim() && !selectedImage)}
            className="p-2.5 rounded-xl transition-all flex-shrink-0 mb-0.5 disabled:opacity-40"
            style={{ background: "var(--accent)", color: "var(--text-on-accent)" }}
            title="Send message">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
          </button>
        </div>
        <p className="text-[10px] text-center mt-1.5 tracking-wide" style={{ color: "var(--text-faint)" }}>
          Powered by Claude + Vulcan OmniPro 220 Manual
        </p>
      </div>

      <style jsx global>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translate(-50%, -12px); }
          to { opacity: 1; transform: translate(-50%, 0); }
        }
      `}</style>
    </div>
  );
}
