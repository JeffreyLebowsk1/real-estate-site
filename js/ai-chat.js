// js/ai-chat.js — AI Chat Widget for homes.mdilworth.com
// Renders a floating bubble (all pages) or an embedded panel (find-a-home)

(function () {
  "use strict";

  const API_URL = "/api/ask";
  const MAX_HISTORY = 10;

  let chatHistory = [];
  let isStreaming = false;

  // ── Render widget into a container ──────────────────────────────────────
  function createChatPanel(container, embedded) {
    container.innerHTML = `
      <div class="ai-chat-panel ${embedded ? 'ai-chat-embedded' : ''}">
        <div class="ai-chat-header">
          <span class="ai-chat-title">🏠 Ask about Sanford real estate</span>
          ${embedded ? '' : '<button class="ai-chat-close" aria-label="Close">&times;</button>'}
        </div>
        <div class="ai-chat-messages">
          <div class="ai-msg ai-msg-assistant">
            <p>Hi! I can help with questions about buying or selling a home in Sanford, NC. What would you like to know?</p>
          </div>
        </div>
        <form class="ai-chat-input">
          <input type="text" placeholder="Ask about neighborhoods, market trends..." autocomplete="off" maxlength="500">
          <button type="submit" aria-label="Send">➤</button>
        </form>
      </div>`;

    const panel = container.querySelector(".ai-chat-panel");
    const messagesEl = container.querySelector(".ai-chat-messages");
    const form = container.querySelector(".ai-chat-input");
    const input = form.querySelector("input");
    const closeBtn = container.querySelector(".ai-chat-close");

    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        container.classList.remove("ai-chat-open");
      });
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text || isStreaming) return;
      input.value = "";
      sendMessage(text, messagesEl);
    });

    return panel;
  }

  // ── Send message + stream response ─────────────────────────────────────
  async function sendMessage(text, messagesEl) {
    isStreaming = true;

    // Add user message
    appendMessage(messagesEl, "user", text);
    chatHistory.push({ role: "user", content: text });

    // Create assistant placeholder
    const assistantEl = appendMessage(messagesEl, "assistant", "");
    const contentEl = assistantEl.querySelector(".ai-msg-content");
    contentEl.innerHTML = '<span class="ai-typing">Searching...</span>';

    try {
      const resp = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: chatHistory.slice(-MAX_HISTORY),
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        contentEl.textContent = err.error || "Sorry, something went wrong.";
        isStreaming = false;
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let fullText = "";
      let citations = [];
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        while (buffer.includes("\n\n")) {
          const idx = buffer.indexOf("\n\n");
          const eventStr = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          for (const line of eventStr.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6);
            if (payload.trim() === "[DONE]") continue;

            try {
              const obj = JSON.parse(payload);
              if (obj.error) {
                contentEl.textContent = obj.error;
                isStreaming = false;
                return;
              }
              if (obj.citations) {
                citations = obj.citations;
              }
              if (obj.content) {
                fullText += obj.content;
                contentEl.innerHTML = formatMarkdown(fullText);
                messagesEl.scrollTop = messagesEl.scrollHeight;
              }
            } catch (e) { /* skip bad JSON */ }
          }
        }
      }

      // Append citations if any
      if (citations.length > 0) {
        const citEl = document.createElement("div");
        citEl.className = "ai-citations";
        citEl.innerHTML = "<strong>Sources:</strong> " + citations.map((url, i) => {
          try {
            const domain = new URL(url).hostname.replace("www.", "");
            return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(domain)}</a>`;
          } catch { return ""; }
        }).filter(Boolean).join(", ");
        contentEl.appendChild(citEl);
      }

      chatHistory.push({ role: "assistant", content: fullText });

    } catch (err) {
      contentEl.textContent = "Network error. Please try again.";
    }

    isStreaming = false;
  }

  // ── Helpers ─────────────────────────────────────────────────────────────
  function appendMessage(container, role, text) {
    const el = document.createElement("div");
    el.className = `ai-msg ai-msg-${role}`;
    el.innerHTML = `<div class="ai-msg-content">${role === "user" ? escapeHtml(text) : text}</div>`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return el;
  }

  function formatMarkdown(text) {
    // Minimal markdown: bold, links, line breaks
    return text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\n/g, "<br>");
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Floating bubble (all pages) ────────────────────────────────────────
  function initFloatingBubble() {
    // Don't double-init
    if (document.getElementById("ai-chat-floating")) return;

    const wrapper = document.createElement("div");
    wrapper.id = "ai-chat-floating";
    wrapper.innerHTML = '<button class="ai-chat-fab" aria-label="Ask AI about real estate">💬</button>';
    document.body.appendChild(wrapper);

    const fab = wrapper.querySelector(".ai-chat-fab");
    fab.addEventListener("click", () => {
      if (!wrapper.querySelector(".ai-chat-panel")) {
        createChatPanel(wrapper, false);
      }
      wrapper.classList.toggle("ai-chat-open");
    });
  }

  // ── Embedded panel (for find-a-home) ───────────────────────────────────
  function initEmbedded(selector) {
    const target = document.querySelector(selector);
    if (!target) return;
    createChatPanel(target, true);
  }

  // ── Public API ─────────────────────────────────────────────────────────
  window.AiChat = { initFloatingBubble, initEmbedded };

  // Auto-init floating bubble on every page
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFloatingBubble);
  } else {
    initFloatingBubble();
  }
})();
