"use client";
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Message {
  role: "user" | "assistant";
  content: string;
  artifact?: string;
  imagePreview?: string; // data URL for displaying uploaded image in chat
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function ArtifactRenderer({ code }: { code: string }) {
  const [hasError, setHasError] = useState(false);

  const processedCode = (() => {
    const match = code.match(/function\s+(\w+)\s*\(/);
    const funcName = match ? match[1] : null;

    let processed = code
      .replace(/export default function/, "function")
      .replace(/export default/, "");

    if (funcName && funcName !== "Component") {
      processed += `\nconst Component = ${funcName};`;
    }

    return processed;
  })();

  const bodyStyle = [
    "body{margin:0;padding:16px;background:#f9fafb;color:#111827;font-family:system-ui,-apple-system,sans-serif}",
    "select,input,option{color:#111827!important;background:#ffffff!important;border:1px solid #d1d5db;padding:6px 10px;border-radius:6px;font-size:14px}",
    "select{min-width:140px;cursor:pointer}",
    "select:focus,input:focus{outline:2px solid #f97316;outline-offset:1px}",
    "label{font-weight:500;font-size:14px}",
    "p,h1,h2,h3,h4,h5,span,td,th,li,div{color:#111827}",
    "table{width:100%;border-collapse:collapse;font-size:14px}",
    "th{background:#1e40af;color:#ffffff!important;padding:10px 12px;text-align:left;font-weight:600}",
    "td{padding:10px 12px;border-bottom:1px solid #e5e7eb}",
    "tr:hover td{background:#f3f4f6}",
    "button{cursor:pointer;padding:8px 16px;border-radius:6px;font-size:14px;font-weight:500;border:none;transition:all 0.15s}",
  ].join("");

  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script src="https://unpkg.com/react@18/umd/react.development.js" crossorigin><\/script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js" crossorigin><\/script>
<script src="https://unpkg.com/@babel/standalone@7.23.5/babel.min.js"><\/script>
<script src="https://cdn.tailwindcss.com"><\/script>
<style>${bodyStyle}<\/style>
</head>
<body>
<div id="root"></div>
<script type="text/babel" data-presets="react">
const { useState, useEffect, useRef, useMemo, useCallback } = React;
try {
${processedCode}
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Component));
} catch(e) {
document.getElementById('root').innerHTML = '<div style="color:#dc2626;padding:20px;font-family:monospace"><b>Artifact render error:</b><br/>' + e.message + '</div>';
}
<\/script>
</body>
</html>`;

  if (hasError) {
    return (
      <div className="mt-2 p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
        Artifact failed to render. Try asking the question again.
      </div>
    );
  }

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2 mb-1.5">
        <div className="w-3 h-3 rounded-sm bg-orange-500/80"></div>
        <span className="text-xs text-gray-400 font-mono">Interactive Tool</span>
      </div>
      <iframe
        srcDoc={html}
        className="w-full border border-gray-700 rounded-lg bg-white"
        style={{ height: "480px" }}
        sandbox="allow-scripts"
        onError={() => setHasError(true)}
      />
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const textContent = message.content;
  const artifactCode = message.artifact;

  return (
    <div
      className={`flex ${message.role === "user" ? "justify-end" : "justify-start"} mb-4`}
    >
      <div
        className={`max-w-3xl w-full ${message.role === "user" ? "ml-12" : "mr-4"}`}
      >
        {message.role === "assistant" && (
          <div className="text-xs text-orange-400 mb-1 font-mono tracking-wide">
            VULCAN AI
          </div>
        )}
        <div
          className={`rounded-xl px-4 py-3 ${
            message.role === "user"
              ? "bg-orange-500 text-white ml-auto w-fit max-w-lg"
              : "bg-gray-800 text-gray-100 border border-gray-700"
          }`}
        >
          {/* Show uploaded image in user bubble */}
          {message.imagePreview && (
            <div className="mb-2">
              <img
                src={message.imagePreview}
                alt="Uploaded"
                className="max-w-xs max-h-48 rounded-lg border border-orange-300/30"
              />
            </div>
          )}
          {message.role === "user" ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {textContent}
            </p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none prose-headings:text-orange-300 prose-headings:font-semibold prose-strong:text-orange-200 prose-li:text-gray-200 prose-p:text-gray-200 prose-p:leading-relaxed prose-a:text-orange-400">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {textContent}
              </ReactMarkdown>
            </div>
          )}
        </div>
        {artifactCode && <ArtifactRenderer code={artifactCode} />}
      </div>
    </div>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hey! I'm your **Vulcan OmniPro 220** assistant. Ask me anything — setup, settings, troubleshooting, duty cycles. You can also **upload a photo** of your weld or settings panel for analysis. What do you need?",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingText, setStreamingText] = useState(""); // accumulates tokens during streaming
  const [selectedImage, setSelectedImage] = useState<{
    base64: string;
    type: string;
    preview: string;
  } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  function parseArtifact(text: string): {
    content: string;
    artifact?: string;
  } {
    const match = text.match(
      /<artifact type="react">([\s\S]*?)<\/artifact>/
    );
    if (match) {
      return {
        content: text
          .replace(/<artifact type="react">[\s\S]*?<\/artifact>/, "")
          .trim(),
        artifact: match[1].trim(),
      };
    }
    return { content: text };
  }

  function buildHistory(currentMessages: Message[]): { role: string; content: string }[] {
    const conversationMessages = currentMessages.slice(1);
    return conversationMessages.map((msg) => ({
      role: msg.role,
      content: msg.artifact
        ? `${msg.content}\n<artifact type="react">${msg.artifact}</artifact>`
        : msg.content,
    }));
  }

  function handleImageSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type)) {
      alert("Please upload a JPEG, PNG, or WebP image.");
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      alert("Image must be under 5MB.");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      // dataUrl format: "data:image/jpeg;base64,/9j/4AAQ..."
      const base64 = dataUrl.split(",")[1];
      setSelectedImage({
        base64,
        type: file.type,
        preview: dataUrl,
      });
    };
    reader.readAsDataURL(file);

    // Reset file input so same file can be re-selected
    e.target.value = "";
  }

  function clearImage() {
    setSelectedImage(null);
  }

  async function sendMessage() {
    if ((!input.trim() && !selectedImage) || loading) return;

    const questionText = input.trim() || "Analyze this image in the context of the Vulcan OmniPro 220 welder. Describe what you see and provide relevant advice.";

    const userMessage: Message = {
      role: "user",
      content: questionText,
      imagePreview: selectedImage?.preview,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setStreamingText("");

    // Capture image data before clearing
    const imageData = selectedImage;
    setSelectedImage(null);

    try {
      const history = buildHistory(messages);

      const body: Record<string, unknown> = {
        question: questionText,
        history: history,
      };

      // Attach image if present
      if (imageData) {
        body.image = imageData.base64;
        body.image_type = imageData.type;
      }

      const res = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      // --- SSE streaming reader ---
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let accumulated = "";
      let buffer = ""; // handles partial SSE lines across chunks

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE lines from buffer
        const lines = buffer.split("\n");
        // Keep the last potentially incomplete line in the buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;

          const jsonStr = line.slice(6); // remove "data: " prefix
          if (!jsonStr.trim()) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === "token") {
              accumulated += event.text;
              // Update streaming text — show text but hide artifact code while streaming
              // Strip incomplete artifact tags during streaming for clean display
              let displayText = accumulated;
              // If we're mid-artifact, only show text before the artifact tag
              const artifactStart = displayText.indexOf("<artifact type=\"react\">");
              if (artifactStart !== -1) {
                displayText = displayText.substring(0, artifactStart).trim();
              }
              setStreamingText(displayText);
            }
            // metadata and done events: we don't need to display them
          } catch {
            // Skip malformed JSON lines (shouldn't happen, but be safe)
          }
        }
      }

      // --- Stream complete: parse final accumulated text ---
      const { content, artifact } = parseArtifact(accumulated);

      const assistantMessage: Message = {
        role: "assistant",
        content,
        artifact,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setStreamingText(""); // clear streaming display
    } catch (err) {
      const errorMsg =
        err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `**Connection error:** ${errorMsg}\n\nMake sure the Python backend is running on ${API_URL}`,
        },
      ]);
      setStreamingText("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <div className="border-b border-gray-800 px-6 py-4 flex items-center gap-3">
        <div className="w-8 h-8 bg-orange-500 rounded-lg flex items-center justify-center">
          <span className="text-white text-xs font-bold">V</span>
        </div>
        <div>
          <h1 className="text-white font-semibold text-sm">
            Vulcan OmniPro 220
          </h1>
          <p className="text-gray-500 text-xs">AI Welding Assistant</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
          <span className="text-gray-500 text-xs">Live</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Streaming message — shows tokens as they arrive */}
        {streamingText && (
          <div className="flex justify-start mb-4">
            <div className="max-w-3xl w-full mr-4">
              <div className="text-xs text-orange-400 mb-1 font-mono tracking-wide">
                VULCAN AI
              </div>
              <div className="rounded-xl px-4 py-3 bg-gray-800 text-gray-100 border border-gray-700">
                <div className="prose prose-invert prose-sm max-w-none prose-headings:text-orange-300 prose-headings:font-semibold prose-strong:text-orange-200 prose-li:text-gray-200 prose-p:text-gray-200 prose-p:leading-relaxed prose-a:text-orange-400">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {streamingText}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Loading dots — only show before first token arrives */}
        {loading && !streamingText && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-3">
              <div className="flex gap-1.5 items-center">
                <div
                  className="w-2 h-2 bg-orange-400 rounded-full animate-bounce"
                  style={{ animationDelay: "0ms" }}
                ></div>
                <div
                  className="w-2 h-2 bg-orange-400 rounded-full animate-bounce"
                  style={{ animationDelay: "150ms" }}
                ></div>
                <div
                  className="w-2 h-2 bg-orange-400 rounded-full animate-bounce"
                  style={{ animationDelay: "300ms" }}
                ></div>
                <span className="text-xs text-gray-500 ml-2">
                  Thinking...
                </span>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Image preview bar */}
      {selectedImage && (
        <div className="border-t border-gray-800 px-6 py-2 bg-gray-900">
          <div className="flex items-center gap-3 max-w-4xl mx-auto">
            <img
              src={selectedImage.preview}
              alt="Selected"
              className="w-16 h-16 object-cover rounded-lg border border-gray-600"
            />
            <div className="flex-1">
              <p className="text-gray-300 text-xs">Image attached</p>
              <p className="text-gray-500 text-xs">Add a question or send as-is</p>
            </div>
            <button
              onClick={clearImage}
              className="text-gray-400 hover:text-red-400 text-sm px-2 py-1 transition-colors"
              title="Remove image"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-gray-800 px-6 py-4">
        <div className="flex gap-3 max-w-4xl mx-auto">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleImageSelect}
            className="hidden"
          />

          {/* Upload button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            className="bg-gray-800 border border-gray-700 hover:border-orange-500 disabled:opacity-50 text-gray-300 hover:text-orange-400 px-3 py-3 rounded-xl text-sm transition-colors"
            title="Upload an image"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <polyline points="21 15 16 10 5 21"/>
            </svg>
          </button>

          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder={
              selectedImage
                ? "Ask about this image (or just hit Send)..."
                : "Ask about setup, settings, troubleshooting..."
            }
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-orange-500 transition-colors"
          />
          <button
            onClick={sendMessage}
            disabled={loading}
            className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white px-6 py-3 rounded-xl text-sm font-medium transition-colors"
          >
            Send
          </button>
        </div>
        <p className="text-gray-600 text-xs text-center mt-2">
          Powered by Claude + Vulcan OmniPro 220 Manual
        </p>
      </div>
    </div>
  );
}
