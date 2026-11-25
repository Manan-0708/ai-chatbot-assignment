import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function generateSessionId() {
  return 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8);
}

export default function App() {
  // Generate a brand new session ID on every page refresh/load
  const [sessionId] = useState(() => generateSessionId());
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [simulateHeader, setSimulateHeader] = useState('');
  const [showConfig, setShowConfig] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const messagesEndRef = useRef(null);

  // Auto scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const trimmed = inputMessage.trim();
    if (!trimmed || loading) return;

    // Immediately clear input after sending
    setInputMessage('');
    setError(null);

    // Optimistically append user message to history
    const userMsg = { role: 'user', content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const headers = {
        'Content-Type': 'application/json',
      };
      if (simulateHeader.trim()) {
        headers['X-Simulate-Failure'] = simulateHeader.trim();
      }

      const payload = {
        session_id: sessionId,
        message: trimmed,
      };
      if (systemPrompt.trim()) {
        payload.system_prompt = systemPrompt.trim();
      }

      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        let errorMsg = 'Failed to get response from server';
        if (data && data.detail) {
          errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        } else if (res.status === 503) {
          errorMsg = '503 Service Unavailable: all providers unavailable';
        }
        throw new Error(errorMsg);
      }

      // Append assistant message with metadata
      const assistantMsg = {
        role: 'assistant',
        content: data.content,
        metadata: data.metadata,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>AI Chatbot</h1>
        <div className="session-info">
          <span>Session: <code>{sessionId}</code></span>
          <button 
            type="button" 
            className="config-toggle" 
            onClick={() => setShowConfig(!showConfig)}
          >
            {showConfig ? 'Hide Settings' : 'Settings / Failover Test'}
          </button>
        </div>
      </header>

      {showConfig && (
        <section className="config-panel">
          <div className="config-row">
            <label htmlFor="system-prompt">System Prompt (optional):</label>
            <input
              id="system-prompt"
              type="text"
              placeholder="e.g. You are a helpful math tutor."
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </div>
          <div className="config-row">
            <label htmlFor="simulate-fail">X-Simulate-Failure Header (testing):</label>
            <input
              id="simulate-fail"
              type="text"
              placeholder="e.g. key_1=429 or *=429 or key_1=500"
              value={simulateHeader}
              onChange={(e) => setSimulateHeader(e.target.value)}
            />
            <div className="preset-buttons">
              <button type="button" onClick={() => setSimulateHeader('')}>Clear</button>
              <button type="button" onClick={() => setSimulateHeader('key_1=429')}>key_1=429</button>
              <button type="button" onClick={() => setSimulateHeader('key_1=500')}>key_1=500</button>
              <button type="button" onClick={() => setSimulateHeader('key_1=429,key_2=500')}>key_1=429,key_2=500</button>
              <button type="button" onClick={() => setSimulateHeader('*=429')}>*=429</button>
            </div>
          </div>
        </section>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <strong>Error:</strong> {error}
        </div>
      )}

      <main className="chat-window">
        {messages.length === 0 ? (
          <div className="empty-state">
            <p>Send a message to start the conversation.</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} className={`message-row ${msg.role}`}>
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-bubble">{msg.content}</div>
                </div>
              ) : (
                <div className="assistant-container">
                  <div className="assistant-message" data-testid="assistant-message">
                    {msg.content}
                  </div>
                  {msg.metadata && (
                    <div className="metadata-bar">
                      <span className="meta-item">
                        Source: <strong data-testid="meta-source">{msg.metadata.source}</strong>
                      </span>
                      <span className="meta-separator">•</span>
                      <span className="meta-item">
                        Model: <span data-testid="meta-model">{msg.metadata.model}</span>
                      </span>
                      <span className="meta-separator">•</span>
                      <span className="meta-item">
                        Latency: <span data-testid="meta-latency">{msg.metadata.latency_ms}ms</span>
                      </span>
                      <span className="meta-separator">•</span>
                      <span className="meta-item">
                        In Tokens: <span data-testid="meta-input-tokens">{msg.metadata.input_tokens}</span>
                      </span>
                      <span className="meta-separator">•</span>
                      <span className="meta-item">
                        Out Tokens: <span data-testid="meta-output-tokens">{msg.metadata.output_tokens}</span>
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="message-row assistant">
            <div className="assistant-message loading-indicator">
              Thinking...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      <form className="chat-form" onSubmit={handleSendMessage}>
        <input
          type="text"
          data-testid="chat-input"
          placeholder="Type your message..."
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          disabled={loading}
          autoFocus
        />
        <button
          type="submit"
          data-testid="send-button"
          disabled={loading || !inputMessage.trim()}
        >
          {loading ? 'Sending...' : 'Send'}
        </button>
      </form>
    </div>
  );
}
