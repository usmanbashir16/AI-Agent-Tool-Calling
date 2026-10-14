
import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/chat/stream";

const suggestions = [
  {
    icon: "🧮",
    title: "Calculate something",
    prompt: "Calculate 245 multiplied by 38",
  },
  {
    icon: "🌐",
    title: "Search the web",
    prompt: "Search the web for the latest AI news",
  },
  {
    icon: "🧠",
    title: "Explore my memory",
    prompt: "What do you remember about me?",
  },
];

function formatEvent(event) {
  const type = (event.type || "activity")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

  const details = Object.entries(event)
    .filter(([key]) => key !== "type")
    .map(([key, value]) => {
      const formattedValue =
        typeof value === "string"
          ? value
          : JSON.stringify(value);

      return `${key}: ${formattedValue}`;
    });

  return {
    type: event.type || "activity",
    title: type,
    details,
    time: new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
  };
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [activities, setActivities] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessionCount, setSessionCount] = useState(0);

  async function sendMessage(text = input) {
    const message = text.trim();

    if (!message || loading) return;

    setInput("");
    setError("");
    setLoading(true);

    setMessages((previous) => [
      ...previous,
      { role: "user", content: message },
    ]);

    setActivities([
      {
        type: "user_message",
        title: "Message received",
        details: [message],
        time: new Date().toLocaleTimeString(),
      },
    ]);

    let finalAnswer = "";
    let streamError = "";

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        throw new Error(
          `Backend returned ${response.status}. Is api.py running?`
        );
      }

      if (!response.body) {
        throw new Error("The browser could not read the response stream.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      function processEvent(block) {
        const dataLines = block
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart());

        if (!dataLines.length) return;

        try {
          const event = JSON.parse(dataLines.join("\n"));

          if (event.type === "answer") {
            finalAnswer = event.message || "";
            return;
          }

          if (event.type === "error") {
            streamError = event.message || "The agent encountered an error.";
            return;
          }

          if (event.type === "done") return;

          const activity = formatEvent(event);
          setActivities((previous) => [...previous, activity]);
        } catch (parseError) {
          console.warn("Could not parse activity event:", parseError);
        }
      }

      while (true) {
        const { value, done } = await reader.read();

        buffer += decoder.decode(value || new Uint8Array(), {
          stream: !done,
        });

        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";

        blocks.forEach(processEvent);

        if (done) break;
      }

      if (buffer.trim()) processEvent(buffer);

      if (streamError) {
        throw new Error(streamError);
      }

      if (!finalAnswer) {
        throw new Error(
          "No answer received. Check the backend terminal for errors."
        );
      }

      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: finalAnswer },
      ]);

      setActivities((previous) => [
        ...previous,
        {
          type: "completed",
          title: "Agent completed",
          details: ["Response delivered successfully"],
          time: new Date().toLocaleTimeString(),
        },
      ]);

      setSessionCount((count) => count + 1);
    } catch (err) {
      setError(err.message || "Something went wrong.");

      setActivities((previous) => [
        ...previous,
        {
          type: "error",
          title: "Request failed",
          details: [err.message || "Unknown error"],
          time: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage();
  }

  function clearChat() {
    if (loading) return;
    setMessages([]);
    setActivities([]);
    setError("");
    setSessionCount(0);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">✳</div>
          <div>
            <h1>Agent Studio</h1>
            <p>AI WORKSPACE</p>
          </div>
        </div>

        <button className="new-chat-button" onClick={clearChat} disabled={loading}>
          <span>＋</span> New conversation
        </button>

        <div className="sidebar-label">WORKSPACE</div>
        <div className="nav-item active">
          <span>◫</span> Agent Chat
          <span className="nav-dot" />
        </div>
        <div className="nav-item">
          <span>⌘</span> Tool Activity
        </div>
        <div className="nav-item">
          <span>◷</span> Conversation
        </div>

        <div className="sidebar-spacer" />

        <div className="backend-card">
          <div className="status-line">
            <span className="status-dot" />
            <span>Backend connection</span>
          </div>
          <p>Local Python API</p>
          <code>localhost:8000</code>
        </div>

        <div className="profile">
          <div className="avatar">AI</div>
          <div>
            <strong>AI Agent</strong>
            <p>Gemini · Tool Calling</p>
          </div>
          <span className="profile-menu">···</span>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span> <strong>Agent Chat</strong>
          </div>
          <div className="topbar-right">
            <span className="live-pill"><span /> LIVE SESSION</span>
            <div className="topbar-avatar">U</div>
          </div>
        </header>

        <div className="workspace">
          <section className="chat-panel">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">YOUR AI ASSISTANT</div>
                <h2>Let's get things done.</h2>
                <p>Ask a question or give your agent a task.</p>
              </div>
              <div className="model-badge">
                <span className="model-icon">✦</span>
                Gemini Agent
              </div>
            </div>

            <div className="chat-content">
              {messages.length === 0 ? (
                <div className="welcome">
                  <div className="welcome-icon">✳</div>
                  <h3>What can I help you with?</h3>
                  <p>
                    I can answer questions, use tools, search the web,
                    and work with saved memories.
                  </p>

                  <div className="suggestions">
                    {suggestions.map((item) => (
                      <button
                        className="suggestion-card"
                        key={item.title}
                        onClick={() => sendMessage(item.prompt)}
                        disabled={loading}
                      >
                        <span className="suggestion-icon">{item.icon}</span>
                        <span>
                          <strong>{item.title}</strong>
                          <small>{item.prompt}</small>
                        </span>
                        <span className="suggestion-arrow">↗</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="messages">
                  {messages.map((message, index) => (
                    <div
                      className={`message-row ${message.role}`}
                      key={`${index}-${message.role}`}
                    >
                      <div className="message-avatar">
                        {message.role === "user" ? "U" : "✳"}
                      </div>
                      <div className="message-body">
                        <div className="message-author">
                          {message.role === "user" ? "You" : "AI Agent"}
                        </div>
                        <div className="message-bubble">
                          {message.content}
                        </div>
                      </div>
                    </div>
                  ))}

                  {loading && (
                    <div className="message-row assistant">
                      <div className="message-avatar">✳</div>
                      <div className="message-body">
                        <div className="message-author">AI Agent</div>
                        <div className="message-bubble thinking">
                          <span className="typing-dots">
                            <i /><i /><i />
                          </span>
                          Working on your request...
                        </div>
                      </div>
                    </div>
                  )}

                  <div id="chat-bottom" />
                </div>
              )}
            </div>

            {error && <div className="error-banner">⚠ {error}</div>}

            <div className="composer-area">
              <form className="composer" onSubmit={handleSubmit}>
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      handleSubmit(event);
                    }
                  }}
                  placeholder="Message your AI agent..."
                  rows={1}
                  disabled={loading}
                />
                <div className="composer-footer">
                  <span className="composer-hint">↵ Send · Shift + ↵ New line</span>
                  <button
                    type="submit"
                    className="send-button"
                    disabled={loading || !input.trim()}
                    aria-label="Send message"
                  >
                    {loading ? "…" : "↑"}
                  </button>
                </div>
              </form>
              <p className="disclaimer">
                AI can make mistakes. Verify important information.
              </p>
            </div>
          </section>

          <aside className="activity-panel">
            <div className="activity-heading">
              <div>
                <div className="eyebrow">UNDER THE HOOD</div>
                <h2>Agent Activity</h2>
              </div>
              <span className={`activity-status ${loading ? "running" : ""}`}>
                <span /> {loading ? "RUNNING" : "READY"}
              </span>
            </div>

            <div className="activity-summary">
              <div>
                <span className="summary-icon">ϟ</span>
                <div><small>Requests</small><strong>{sessionCount}</strong></div>
              </div>
              <div>
                <span className="summary-icon">⌘</span>
                <div><small>Events</small><strong>{activities.length}</strong></div>
              </div>
            </div>

            <div className="activity-feed">
              {activities.length === 0 ? (
                <div className="activity-empty">
                  <div className="empty-orbit">⌘</div>
                  <strong>Waiting for activity</strong>
                  <p>Send a message to watch your agent think and use its tools.</p>
                </div>
              ) : (
                <>
                  <div className="feed-caption">LIVE EVENT STREAM</div>
                  {activities.map((activity, index) => (
                    <div className="activity-item" key={`${index}-${activity.time}`}>
                      <div className={`activity-marker ${activity.type}`}>
                        {activity.type === "error"
                          ? "!"
                          : activity.type === "completed"
                            ? "✓"
                            : activity.type?.includes("tool")
                              ? "⌘"
                              : "•"}
                      </div>
                      <div className="activity-details">
                        <div className="activity-item-top">
                          <strong>{activity.title}</strong>
                          <time>{activity.time}</time>
                        </div>
                        {activity.details.map((detail, detailIndex) => (
                          <p key={detailIndex}>{detail}</p>
                        ))}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="streaming-indicator">
                      <span className="pulse-dot" /> Listening for events...
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="activity-footer">
              <span className="status-dot" />
              <span>Streaming via Server-Sent Events</span>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}