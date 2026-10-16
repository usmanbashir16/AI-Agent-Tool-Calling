
import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";
const MAX_PDF_SIZE = 20 * 1024 * 1024;

function App() {
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [activities, setActivities] = useState([]);
  const [input, setInput] = useState("");

  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [backendConnected, setBackendConnected] = useState(false);
  const [error, setError] = useState("");

  // PDF upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState(false);
  const fileInputRef = useRef(null);

  const busyRef = useRef(false);
  const conversationIdRef = useRef(null);
  const messagesEndRef = useRef(null);
  const activityEndRef = useRef(null);

  const addActivity = useCallback((message, type = "info") => {
    setActivities((previous) => [
      ...previous,
      {
        id: `${Date.now()}-${Math.random()}`,
        message,
        type,
        time: new Date().toLocaleTimeString(),
      },
    ]);
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/conversations`);

      if (!response.ok) {
        throw new Error("Could not load conversations.");
      }

      const data = await response.json();
      setConversations(data.conversations || []);
      setBackendConnected(true);
      return data.conversations || [];
    } catch (err) {
      setBackendConnected(false);
      throw err;
    }
  }, []);

  const checkBackend = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/health`);
      setBackendConnected(response.ok);
    } catch {
      setBackendConnected(false);
    }
  }, []);

  const openConversation = useCallback(
    async (id) => {
      if (!id || busyRef.current) return;

      setHistoryLoading(true);
      setError("");
      setActivities([]);
      conversationIdRef.current = id;
      setConversationId(id);

      try {
        const response = await fetch(
          `${API_BASE}/conversations/${encodeURIComponent(id)}/messages`
        );

        if (!response.ok) {
          throw new Error("Could not load this conversation.");
        }

        const data = await response.json();

        setMessages(
          (data.messages || []).map((message) => ({
            role:
              message.role === "model" || message.role === "assistant"
                ? "assistant"
                : "user",
            content: message.content,
          }))
        );

        addActivity("Conversation history loaded.", "success");
      } catch (err) {
        setError(err.message || "Failed to load conversation.");
        addActivity("Failed to load conversation history.", "error");
      } finally {
        setHistoryLoading(false);
      }
    },
    [addActivity]
  );

  const createNewConversation = useCallback(async () => {
    if (busyRef.current) return;

    setError("");
    setActivities([]);
    setMessages([]);
    setInput("");
    conversationIdRef.current = null;
    setConversationId(null);

    try {
      const response = await fetch(`${API_BASE}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New conversation" }),
      });

      if (!response.ok) {
        throw new Error("Could not create a new conversation.");
      }

      const data = await response.json();
      const id = data.id || data.conversation_id;

      if (!id) {
        throw new Error("The backend did not return a conversation ID.");
      }

      conversationIdRef.current = id;
      setConversationId(id);
      addActivity("New conversation created.", "success");
      await refreshConversations();
    } catch (err) {
      setError(err.message || "Failed to create conversation.");
      addActivity("Could not create a new conversation.", "error");
    }
  }, [addActivity, refreshConversations]);

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      try {
        const items = await refreshConversations();

        if (cancelled) return;

        if (items.length > 0) {
          await openConversation(items[0].id);
        } else {
          await createNewConversation();
        }
      } catch {
        if (!cancelled) {
          setError("Backend is unavailable. Start your FastAPI server.");
        }
      }
    }

    initialize();
    checkBackend();

    const intervalId = setInterval(checkBackend, 5000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [
    refreshConversations,
    openConversation,
    createNewConversation,
    checkBackend,
  ]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    activityEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activities]);

  // =======================================================
  // PDF FILE SELECTION
  // =======================================================

  const handleFileSelection = (event) => {
    const file = event.target.files?.[0];

    // Allow selecting the same file again after clearing it.
    if (!file) return;

    setUploadMessage("");
    setUploadError(false);

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setSelectedFile(null);
      setUploadMessage("Please select a PDF file.");
      setUploadError(true);
      event.target.value = "";
      return;
    }

    if (file.size === 0) {
      setSelectedFile(null);
      setUploadMessage("The selected file is empty.");
      setUploadError(true);
      event.target.value = "";
      return;
    }

    if (file.size > MAX_PDF_SIZE) {
      setSelectedFile(null);
      setUploadMessage("PDF must be 20 MB or smaller.");
      setUploadError(true);
      event.target.value = "";
      return;
    }

    setSelectedFile(file);
  };

  // =======================================================
  // UPLOAD PDF TO FASTAPI
  // =======================================================

  const uploadPdf = async () => {
    if (!selectedFile || uploading) return;

    if (!backendConnected) {
      setUploadMessage("Backend is disconnected. Start FastAPI first.");
      setUploadError(true);
      return;
    }

    setUploading(true);
    setUploadMessage("Uploading and indexing PDF...");
    setUploadError(false);

    addActivity(`Uploading PDF: ${selectedFile.name}`, "info");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${API_BASE}/upload-pdf`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data.detail || `PDF upload failed (${response.status}).`
        );
      }

      if (data.status === "already_exists") {
        setUploadMessage(
          `${data.filename} is already indexed. You can ask questions about it.`
        );
        addActivity(
          `PDF already indexed: ${data.filename}`,
          "success"
        );
      } else {
        setUploadMessage(
          `${data.filename}: ${data.pages_processed} pages processed, ` +
            `${data.chunks_stored} chunks indexed.`
        );

        addActivity(
          `PDF indexed successfully: ${data.filename} ` +
            `(${data.chunks_stored} chunks)`,
          "success"
        );
      }

      setSelectedFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      setUploadMessage(err.message || "PDF upload failed.");
      setUploadError(true);
      addActivity(err.message || "PDF upload failed.", "error");
    } finally {
      setUploading(false);
    }
  };

  // =======================================================
  // CHAT STREAMING
  // =======================================================

  const sendMessage = async (event) => {
    event.preventDefault();

    const text = input.trim();

    if (!text || loading || busyRef.current) return;

    if (!backendConnected) {
      setError("Backend is disconnected. Please start the backend first.");
      return;
    }

    busyRef.current = true;
    setLoading(true);
    setError("");
    setInput("");

    setMessages((previous) => [
      ...previous,
      { role: "user", content: text },
    ]);

    addActivity("Sending message to the AI agent...", "info");

    let assistantText = "";
    let assistantMessageAdded = false;
    let streamBuffer = "";

    const ensureAssistantMessage = () => {
      if (!assistantMessageAdded) {
        assistantMessageAdded = true;
        setMessages((previous) => [
          ...previous,
          { role: "assistant", content: assistantText },
        ]);
      } else {
        setMessages((previous) => {
          const updated = [...previous];
          const last = updated[updated.length - 1];

          if (last?.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: assistantText,
            };
          }

          return updated;
        });
      }
    };

    const handleEvent = (rawEvent) => {
      const dataLines = rawEvent
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());

      if (!dataLines.length) return;

      let payload;

      try {
        payload = JSON.parse(dataLines.join("\n"));
      } catch {
        return;
      }

      const type = String(
        payload.type || payload.event || ""
      ).toLowerCase();

      const message =
        payload.message ||
        payload.activity ||
        payload.content ||
        payload.text ||
        "";

      if (
        type.includes("activity") ||
        type.includes("tool") ||
        type.includes("status") ||
        type.includes("search") ||
        type.includes("memory") ||
        type.includes("step") ||
        type.includes("error")
      ) {
        if (message) {
          addActivity(
            message,
            type.includes("error") ? "error" : "info"
          );
        }
      }

      if (type === "token" || type === "chunk") {
        assistantText += payload.text || payload.content || "";
        ensureAssistantMessage();
      } else if (
        type === "answer" ||
        type === "response" ||
        type === "final" ||
        type === "complete"
      ) {
        const finalText =
          payload.answer ||
          payload.response ||
          payload.content ||
          payload.text;

        if (finalText) {
          assistantText = finalText;
          ensureAssistantMessage();
        }

        addActivity("Agent response received.", "success");
      } else if (type === "error") {
        setError(message || "The agent encountered an error.");
        addActivity(message || "Agent error.", "error");
      } else if (payload.answer && typeof payload.answer === "string") {
        assistantText = payload.answer;
        ensureAssistantMessage();
      }
    };

    try {
      let activeId = conversationIdRef.current;

      if (!activeId) {
        const createResponse = await fetch(`${API_BASE}/conversations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "New conversation" }),
        });

        if (!createResponse.ok) {
          throw new Error("Could not create a conversation.");
        }

        const created = await createResponse.json();
        activeId = created.id || created.conversation_id;

        if (!activeId) {
          throw new Error("No conversation ID returned by the backend.");
        }

        conversationIdRef.current = activeId;
        setConversationId(activeId);
      }

      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          message: text,
          conversation_id: activeId,
        }),
      });

      if (!response.ok) {
        const details = await response.text();
        throw new Error(
          `Chat request failed (${response.status}). ${details.slice(0, 300)}`
        );
      }

      if (!response.body) {
        throw new Error("The backend did not return a stream.");
      }

      addActivity("Connected to the agent stream.", "success");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        streamBuffer += decoder.decode(value, { stream: true });

        const blocks = streamBuffer.split(/\r?\n\r?\n/);
        streamBuffer = blocks.pop() || "";

        for (const block of blocks) {
          handleEvent(block);
        }
      }

      if (streamBuffer.trim()) {
        handleEvent(streamBuffer);
      }

      if (!assistantText && !assistantMessageAdded) {
        addActivity(
          "The stream ended without a recognized answer event. " +
            "Check the backend SSE event format.",
          "warning"
        );
      }

      await refreshConversations();
      addActivity("Conversation saved.", "success");
    } catch (err) {
      setError(
        err.message || "Something went wrong while sending the message."
      );
      addActivity(err.message || "Request failed.", "error");
    } finally {
      busyRef.current = false;
      setLoading(false);
    }
  };

  const currentConversation = conversations.find(
    (item) => item.id === conversationId
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">AI</div>
          <div>
            <h2>Frostyy's Agent</h2>
            <p>Tool Calling Assistant</p>
          </div>
        </div>

        <button
          className="new-chat-button"
          onClick={createNewConversation}
          disabled={loading || uploading}
        >
          <span>＋</span> New Conversation
        </button>

        <div className="sidebar-section-title">YOUR CONVERSATIONS</div>

        <div className="conversation-list">
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              className={`conversation-item ${
                conversation.id === conversationId ? "active" : ""
              }`}
              onClick={() => openConversation(conversation.id)}
              disabled={loading || historyLoading || uploading}
              title={conversation.title}
            >
              <span className="conversation-icon">▤</span>
              <span className="conversation-title">
                {conversation.title || "New conversation"}
              </span>
            </button>
          ))}

          {conversations.length === 0 && (
            <p className="empty-sidebar">No conversations yet.</p>
          )}
        </div>

        <div className="sidebar-footer">
          <div className="connection-card">
            <span
              className={`status-dot ${
                backendConnected ? "connected" : "disconnected"
              }`}
            />
            <div>
              <div className="connection-title">Backend Connection</div>
              <div
                className={`connection-label ${
                  backendConnected ? "online" : "offline"
                }`}
              >
                {backendConnected ? "Connected" : "Disconnected"}
              </div>
            </div>
            <button
              className="refresh-status"
              title="Check backend connection"
              onClick={checkBackend}
            >
              ↻
            </button>
          </div>
          <p className="sidebar-version">AI Agent · Local Environment</p>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <h1>{currentConversation?.title || "New Conversation"}</h1>
            <p>Ask questions and let your AI agent use its tools.</p>
          </div>

          <div className="topbar-status">
            <span
              className={`status-dot ${
                backendConnected ? "connected" : "disconnected"
              }`}
            />
            {backendConnected ? "Backend Online" : "Backend Offline"}
          </div>
        </header>

        <div className="workspace">
          <section className="chat-panel">
            <div className="messages">
              {historyLoading && (
                <div className="loading-history">
                  Loading conversation...
                </div>
              )}

              {!historyLoading && messages.length === 0 && (
                <div className="welcome-screen">
                  <div className="welcome-icon">✦</div>
                  <h2>How can I help you?</h2>
                  <p>
                    Ask a question. Your agent can use tools, search
                    information, and remember conversations.
                  </p>
                </div>
              )}

              {messages.map((message, index) => (
                <div
                  key={`${conversationId}-${index}`}
                  className={`message-row ${message.role}`}
                >
                  <div className={`message-avatar ${message.role}`}>
                    {message.role === "assistant" ? "AI" : "You"}
                  </div>
                  <div className="message-content">
                    <div className="message-author">
                      {message.role === "assistant" ? "AI Agent" : "You"}
                    </div>
                    <div className="message-bubble">{message.content}</div>
                  </div>
                </div>
              ))}

              {loading && (
                <div className="message-row assistant">
                  <div className="message-avatar assistant">AI</div>
                  <div className="message-content">
                    <div className="message-author">AI Agent</div>
                    <div className="thinking-indicator">
                      <span />
                      <span />
                      <span />
                      <small>Working...</small>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {error && (
              <div className="error-banner">
                <span>{error}</span>
                <button onClick={() => setError("")}>×</button>
              </div>
            )}

            {/* PDF upload and chat input */}
            <form className="chat-input-area" onSubmit={sendMessage}>
              <div className="pdf-upload-area">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,application/pdf"
                  onChange={handleFileSelection}
                  disabled={uploading}
                  hidden
                />

                <button
                  type="button"
                  className="pdf-select-button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={!backendConnected || uploading}
                  title="Select a PDF to index"
                >
                  {uploading ? "Processing PDF..." : "＋ Upload PDF"}
                </button>

                {selectedFile && (
                  <div className="selected-pdf">
                    <span className="pdf-file-icon">PDF</span>
                    <span className="selected-pdf-name" title={selectedFile.name}>
                      {selectedFile.name}
                    </span>
                    <button
                      type="button"
                      className="remove-pdf-button"
                      onClick={() => {
                        setSelectedFile(null);
                        setUploadMessage("");
                        setUploadError(false);
                        if (fileInputRef.current) {
                          fileInputRef.current.value = "";
                        }
                      }}
                      disabled={uploading}
                      aria-label="Remove selected PDF"
                    >
                      ×
                    </button>
                    <button
                      type="button"
                      className="pdf-upload-submit"
                      onClick={uploadPdf}
                      disabled={uploading || !backendConnected}
                    >
                      {uploading ? "Uploading..." : "Index PDF"}
                    </button>
                  </div>
                )}

                {uploadMessage && (
                  <div
                    className={`pdf-upload-message ${
                      uploadError ? "error" : "success"
                    }`}
                    role="status"
                  >
                    {uploadMessage}
                  </div>
                )}

                <p className="pdf-upload-hint">
                  Upload a PDF to search its contents · Maximum 20 MB
                </p>
              </div>

              <div className="input-wrapper">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder={
                    backendConnected
                      ? "Message your AI agent..."
                      : "Backend disconnected..."
                  }
                  rows={1}
                  disabled={loading || !backendConnected}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                />

                <button
                  type="submit"
                  className="send-button"
                  disabled={!input.trim() || loading || !backendConnected}
                  title="Send message"
                >
                  {loading ? "…" : "↑"}
                </button>
              </div>

              <p className="input-hint">
                Enter to send · Shift + Enter for a new line
              </p>
            </form>
          </section>

          <aside className="activity-panel">
            <div className="activity-header">
              <div>
                <h2>Activity Log</h2>
                <p>Live agent activity</p>
              </div>
              <span className="activity-count">{activities.length}</span>
            </div>

            <div className="activity-status">
              <span
                className={`status-dot ${
                  backendConnected ? "connected" : "disconnected"
                }`}
              />
              {backendConnected ? "Backend connected" : "Backend unavailable"}
            </div>

            <div className="activity-list">
              {activities.length === 0 ? (
                <div className="activity-empty">
                  <span className="activity-empty-icon">⌁</span>
                  <p>No activity yet</p>
                  <small>
                    Agent steps and tool events will appear here.
                  </small>
                </div>
              ) : (
                activities.map((activity) => (
                  <div
                    key={activity.id}
                    className={`activity-item ${activity.type}`}
                  >
                    <div className="activity-timeline">
                      <span className="activity-dot" />
                      <span className="activity-line" />
                    </div>
                    <div className="activity-details">
                      <div className="activity-message">
                        {activity.message}
                      </div>
                      <div className="activity-time">{activity.time}</div>
                    </div>
                  </div>
                ))
              )}
              <div ref={activityEndRef} />
            </div>

            <div className="activity-footer">
              <span className="live-indicator" />
              Activity updates during agent execution
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}

export default App;
