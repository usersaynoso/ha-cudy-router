class CudyRouterSmsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    this._route = null;
    this._narrow = false;
    this._entries = [];
    this._selectedEntryId = "";
    this._selectedTab = "inbox";
    this._selectedMessageKey = "";
    this._data = null;
    this._entriesLoading = false;
    this._messagesLoading = false;
    this._sendPending = false;
    this._error = "";
    this._notice = "";
    this._composePhone = "";
    this._composeMessage = "";
    this._bootstrapped = false;
  }

  set hass(hass) {
    const firstLoad = !this._hass;
    this._hass = hass;
    if (firstLoad && !this._bootstrapped) {
      this._bootstrapped = true;
      this._loadEntries();
    }
    this._render();
  }

  set panel(panel) {
    this._panel = panel;
    this._render();
  }

  set route(route) {
    this._route = route;
    this._render();
  }

  set narrow(narrow) {
    this._narrow = Boolean(narrow);
    this._render();
  }

  async _callApi(message) {
    if (!this._hass) {
      throw new Error("Home Assistant connection is not ready.");
    }
    return this._hass.connection.sendMessagePromise(message);
  }

  async _loadEntries(preserveSelection = true) {
    this._entriesLoading = true;
    this._error = "";
    this._render();
    try {
      const result = await this._callApi({
        type: "cudy_router/sms/list_entries",
      });
      this._entries = Array.isArray(result.entries) ? result.entries : [];

      if (!this._entries.length) {
        this._selectedEntryId = "";
        this._data = null;
        this._selectedMessageKey = "";
        return;
      }

      const stillValid =
        preserveSelection &&
        this._selectedEntryId &&
        this._entries.some((entry) => entry.entry_id === this._selectedEntryId);

      if (!stillValid) {
        this._selectedEntryId = this._entries[0].entry_id;
      }

      await this._loadMessages();
    } catch (err) {
      this._error = err?.message || "Failed to load SMS-capable routers.";
    } finally {
      this._entriesLoading = false;
      this._render();
    }
  }

  async _loadMessages() {
    if (!this._selectedEntryId) {
      this._data = null;
      this._selectedMessageKey = "";
      this._render();
      return;
    }

    this._messagesLoading = true;
    this._error = "";
    this._notice = "";
    this._render();
    try {
      this._data = await this._callApi({
        type: "cudy_router/sms/get_messages",
        entry_id: this._selectedEntryId,
      });
      this._syncSelectedMessage();
    } catch (err) {
      this._error = err?.message || "Failed to load SMS messages.";
      this._data = null;
      this._selectedMessageKey = "";
    } finally {
      this._messagesLoading = false;
      this._render();
    }
  }

  _mailbox(folder) {
    return this._data?.mailboxes?.[folder] || { available: false, messages: [] };
  }

  _messageKey(message) {
    return message.cfg || `${message.folder || this._selectedTab}:${message.index || message.timestamp || ""}`;
  }

  _messagesForSelectedTab() {
    return this._mailbox(this._selectedTab).messages || [];
  }

  _syncSelectedMessage() {
    const messages = this._messagesForSelectedTab();
    if (!messages.length) {
      this._selectedMessageKey = "";
      return;
    }

    const existing = messages.find(
      (message) => this._messageKey(message) === this._selectedMessageKey,
    );
    if (!existing) {
      this._selectedMessageKey = this._messageKey(messages[0]);
    }
  }

  _selectedMessage() {
    return this._messagesForSelectedTab().find(
      (message) => this._messageKey(message) === this._selectedMessageKey,
    ) || null;
  }

  async _sendSms() {
    if (!this._selectedEntryId || !this._composePhone.trim() || !this._composeMessage.trim()) {
      this._error = "Phone number and message are required.";
      this._notice = "";
      this._render();
      return;
    }

    this._sendPending = true;
    this._error = "";
    this._notice = "";
    this._render();
    try {
      const result = await this._callApi({
        type: "cudy_router/sms/send",
        entry_id: this._selectedEntryId,
        phone_number: this._composePhone.trim(),
        message: this._composeMessage,
      });
      this._notice = result.message || "SMS sent.";
      this._composeMessage = "";
      await this._loadMessages();
      await this._loadEntries(true);
    } catch (err) {
      this._error = err?.message || "Failed to send SMS.";
    } finally {
      this._sendPending = false;
      this._render();
    }
  }

  _setSelectedTab(tab) {
    this._selectedTab = tab;
    this._selectedMessageKey = "";
    this._syncSelectedMessage();
    this._render();
  }

  _replyToSelectedMessage() {
    const message = this._selectedMessage();
    if (!message) {
      return;
    }
    this._composePhone = message.phone || "";
    this._notice = "Recipient copied into the compose form.";
    this._error = "";
    this._render();
    const textarea = this.shadowRoot.querySelector("#compose-message");
    if (textarea) {
      textarea.focus();
    }
  }

  _escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  _renderMessageList() {
    const mailbox = this._mailbox(this._selectedTab);
    if (!mailbox.available) {
      return `<div class="empty">The router did not return the ${this._selectedTab} mailbox details.</div>`;
    }

    if (!mailbox.messages.length) {
      return `<div class="empty">No ${this._selectedTab} messages on this router.</div>`;
    }

    return mailbox.messages
      .map((message) => {
        const key = this._messageKey(message);
        const activeClass = key === this._selectedMessageKey ? "message-item active" : "message-item";
        const status = this._selectedTab === "inbox"
          ? `<span class="chip ${message.read ? "muted" : "unread"}">${message.read ? "Read" : "Unread"}</span>`
          : `<span class="chip muted">Sent</span>`;
        return `
          <button class="${activeClass}" data-message-key="${this._escapeHtml(key)}">
            <div class="message-row">
              <div class="message-phone">
                <strong>${this._escapeHtml(message.phone || "Unknown number")}</strong>
              </div>
              ${status}
            </div>
            <div class="message-preview">${this._escapeHtml(message.preview || message.text || "No preview available.")}</div>
            <div class="message-meta">${this._escapeHtml(message.timestamp || "Unknown time")}</div>
          </button>
        `;
      })
      .join("");
  }

  _renderMessageDetail() {
    const message = this._selectedMessage();
    if (!message) {
      return `<div class="empty detail-empty">Select a message to read its full contents.</div>`;
    }

    const body = this._escapeHtml(message.text || "No message body available.").replaceAll("\n", "<br>");
    const statusLine =
      this._selectedTab === "inbox"
        ? `<div class="detail-meta"><span>Status</span><strong>${message.read ? "Read" : "Unread"}</strong></div>`
        : "";

    return `
      <div class="detail-card">
        <div class="detail-header">
          <div>
            <div class="detail-label">${this._selectedTab === "inbox" ? "From" : "To"}</div>
            <h2>${this._escapeHtml(message.phone || "Unknown number")}</h2>
          </div>
          <button id="reply-button" class="secondary">Reply</button>
        </div>
        <div class="detail-meta"><span>Time</span><strong>${this._escapeHtml(message.timestamp || "Unknown")}</strong></div>
        ${statusLine}
        <div class="detail-body">${body}</div>
      </div>
    `;
  }

  _render() {
    const selectedEntry = this._entries.find((entry) => entry.entry_id === this._selectedEntryId) || null;
    const counts = this._data?.counts || selectedEntry?.counts || { inbox: 0, outbox: 0, unread: 0 };
    const loading = this._entriesLoading || this._messagesLoading;
    const selectedMessage = this._selectedMessage();
    const darkMode = Boolean(this._hass?.themes?.darkMode);
    const theme = darkMode
      ? {
          pageBackground: "#11161c",
          cardBackground: "#1b212c",
          subtleBackground: "#151b24",
          surfaceHover: "#232c39",
          text: "#e8edf5",
          muted: "#a9b4c6",
          divider: "rgba(232, 237, 245, 0.14)",
          border: "rgba(232, 237, 245, 0.16)",
          borderStrong: "rgba(232, 237, 245, 0.24)",
          cardBorder: "rgba(232, 237, 245, 0.12)",
          controlBackground: "#121821",
          controlBorder: "rgba(232, 237, 245, 0.22)",
          controlOutline: "rgba(232, 237, 245, 0.14)",
          shadow: "0 18px 36px rgba(0, 0, 0, 0.34), 0 4px 12px rgba(0, 0, 0, 0.28)",
          success: "#81c784",
          warning: "#ffca28",
          error: "#ef9a9a",
          accent: "#03a9f4",
        }
      : {
          pageBackground: "#f6f8fc",
          cardBackground: "#ffffff",
          subtleBackground: "#f3f5f9",
          surfaceHover: "#eef4fc",
          text: "#1f2937",
          muted: "#5f6b7a",
          divider: "rgba(31, 41, 55, 0.14)",
          border: "rgba(31, 41, 55, 0.14)",
          borderStrong: "rgba(31, 41, 55, 0.22)",
          cardBorder: "rgba(31, 41, 55, 0.10)",
          controlBackground: "#ffffff",
          controlBorder: "rgba(31, 41, 55, 0.18)",
          controlOutline: "rgba(31, 41, 55, 0.12)",
          shadow: "0 12px 32px rgba(15, 23, 42, 0.08), 0 2px 8px rgba(15, 23, 42, 0.05)",
          success: "#2e7d32",
          warning: "#b26a00",
          error: "#d14343",
          accent: "#009ac7",
        };

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --sms-panel-font-family: var(
            --paper-font-common-base_-_font-family,
            "Roboto",
            "Noto Sans",
            sans-serif
          );
          --sms-panel-page-background: var(--primary-background-color, ${theme.pageBackground});
          --sms-panel-card-background: var(
            --ha-card-background,
            var(--card-background-color, ${theme.cardBackground})
          );
          --sms-panel-subtle-background: var(--secondary-background-color, ${theme.subtleBackground});
          --sms-panel-text: var(--primary-text-color, ${theme.text});
          --sms-panel-muted: var(--secondary-text-color, ${theme.muted});
          --sms-panel-divider: var(--divider-color, ${theme.divider});
          --sms-panel-border: ${theme.border};
          --sms-panel-border-strong: ${theme.borderStrong};
          --sms-panel-card-border: ${theme.cardBorder};
          --sms-panel-control-background: ${theme.controlBackground};
          --sms-panel-control-border: ${theme.controlBorder};
          --sms-panel-control-outline: ${theme.controlOutline};
          --sms-panel-surface: var(--sms-panel-card-background);
          --sms-panel-surface-alt: var(--sms-panel-subtle-background);
          --sms-panel-surface-hover: ${theme.surfaceHover};
          --sms-panel-accent: var(--primary-color, ${theme.accent});
          --sms-panel-accent-contrast: #fff;
          --sms-panel-accent-soft: color-mix(in srgb, var(--sms-panel-accent) 16%, transparent);
          --sms-panel-accent-bright: color-mix(in srgb, var(--sms-panel-accent) 84%, white 16%);
          --sms-panel-accent-deep: color-mix(in srgb, var(--sms-panel-accent) 72%, black 28%);
          --sms-panel-shadow: ${theme.shadow};
          --sms-panel-success: ${theme.success};
          --sms-panel-warning: ${theme.warning};
          --sms-panel-error: ${theme.error};
          --sms-panel-radius: var(--ha-card-border-radius, 16px);
          display: block;
          min-height: 100%;
          box-sizing: border-box;
          background:
            radial-gradient(circle at top left, var(--sms-panel-accent-soft), transparent 28%),
            var(--sms-panel-page-background);
          color: var(--sms-panel-text);
          padding: 24px;
          font-family: var(--sms-panel-font-family);
          font-size: 16px;
          line-height: 1.5;
          -webkit-font-smoothing: antialiased;
          text-rendering: optimizeLegibility;
        }

        * {
          box-sizing: border-box;
          font-family: inherit;
        }

        .shell {
          display: grid;
          gap: 18px;
          max-width: 1480px;
          margin: 0 auto;
        }

        .hero,
        .list-pane,
        .detail-pane,
        .composer {
          background: var(--sms-panel-card-background);
          border: 1px solid var(--sms-panel-card-border);
          box-shadow:
            0 0 0 1px color-mix(in srgb, var(--sms-panel-card-border) 72%, transparent),
            var(--sms-panel-shadow);
          border-radius: var(--sms-panel-radius);
        }

        .hero {
          padding: 20px;
          display: grid;
          gap: 18px;
        }

        .hero-top {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          gap: 12px;
          align-items: start;
        }

        .hero-copy {
          display: grid;
          gap: 4px;
          max-width: 760px;
        }

        .hero-grid {
          display: grid;
          grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
          gap: 16px;
          align-items: end;
        }

        .pane-header {
          display: flex;
          justify-content: space-between;
          align-items: start;
          gap: 12px;
        }

        .pane-title {
          display: grid;
          gap: 4px;
        }

        .pane-kicker {
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--sms-panel-muted);
          font-size: 0.73rem;
          font-weight: 700;
        }

        .eyebrow {
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--sms-panel-muted);
          font-size: 0.75rem;
          font-weight: 600;
        }

        h1 {
          margin: 4px 0 0;
          font-size: clamp(1.55rem, 2vw, 2.15rem);
          line-height: 1.15;
          font-weight: 700;
          letter-spacing: -0.02em;
        }

        h2 {
          margin: 0;
          font-size: 1.45rem;
          line-height: 1.2;
          font-weight: 700;
          letter-spacing: -0.01em;
        }

        label {
          display: grid;
          gap: 6px;
        }

        .control-shell {
          display: flex;
          align-items: center;
          min-height: 50px;
          border: 1px solid var(--sms-panel-control-border);
          border-radius: 12px;
          background: var(--sms-panel-control-background);
          box-shadow:
            inset 0 1px 0 color-mix(in srgb, var(--sms-panel-text) 4%, transparent),
            0 0 0 1px var(--sms-panel-control-outline),
            0 1px 2px color-mix(in srgb, black 12%, transparent);
          transition:
            border-color 120ms ease,
            box-shadow 120ms ease,
            background 120ms ease,
            transform 120ms ease;
        }

        .control-shell:focus-within {
          border-color: var(--sms-panel-accent);
          background: color-mix(in srgb, var(--sms-panel-control-background) 86%, var(--sms-panel-accent-soft) 14%);
          box-shadow:
            inset 0 1px 0 color-mix(in srgb, var(--sms-panel-accent) 12%, transparent),
            0 0 0 1px var(--sms-panel-control-outline),
            0 0 0 3px color-mix(in srgb, var(--sms-panel-accent) 30%, transparent);
        }

        .control-shell.multiline {
          align-items: stretch;
          min-height: 170px;
        }

        .field-label {
          color: var(--sms-panel-muted);
          font-size: 0.88rem;
          font-weight: 600;
        }

        .subtle {
          color: var(--sms-panel-muted);
          font-size: 0.95rem;
          line-height: 1.45;
        }

        select,
        textarea,
        input,
        button {
          font: inherit;
          color: var(--sms-panel-text);
        }

        select,
        textarea,
        input {
          width: 100%;
          border: 0;
          border-radius: 12px;
          background: transparent;
          color: inherit;
          padding: 12px 14px;
          outline: none;
          box-shadow: none;
          transition: background 120ms ease;
        }

        select option {
          background: var(--sms-panel-surface);
          color: var(--sms-panel-text);
        }

        select {
          appearance: none;
          background-image:
            linear-gradient(45deg, transparent 50%, var(--sms-panel-muted) 50%),
            linear-gradient(135deg, var(--sms-panel-muted) 50%, transparent 50%);
          background-position:
            calc(100% - 20px) calc(50% - 2px),
            calc(100% - 14px) calc(50% - 2px);
          background-size: 6px 6px, 6px 6px;
          background-repeat: no-repeat;
          padding-right: 34px;
        }

        textarea::placeholder,
        input::placeholder {
          color: var(--sms-panel-muted);
          opacity: 1;
        }

        select:focus,
        textarea:focus,
        input:focus {
          box-shadow: none;
        }

        textarea {
          min-height: 160px;
          resize: vertical;
        }

        button {
          appearance: none;
          border: 1px solid var(--sms-panel-control-border);
          border-radius: 999px;
          padding: 10px 18px;
          cursor: pointer;
          transition:
            transform 120ms ease,
            opacity 120ms ease,
            background 120ms ease,
            border-color 120ms ease,
            box-shadow 120ms ease;
          min-height: 42px;
        }

        button:hover {
          transform: translateY(-1px);
        }

        button:disabled {
          cursor: default;
          opacity: 0.55;
          transform: none;
        }

        .primary {
          background: linear-gradient(
            135deg,
            var(--sms-panel-accent-bright),
            var(--sms-panel-accent-deep)
          );
          color: var(--sms-panel-accent-contrast);
          font-weight: 600;
          border-color: color-mix(in srgb, var(--sms-panel-accent-deep) 78%, black 22%);
          text-shadow: 0 1px 0 rgba(0, 0, 0, 0.28);
          box-shadow:
            0 0 0 1px color-mix(in srgb, var(--sms-panel-accent) 42%, transparent),
            0 10px 22px color-mix(in srgb, var(--sms-panel-accent) 28%, transparent);
        }

        .primary:hover {
          box-shadow:
            0 0 0 1px color-mix(in srgb, var(--sms-panel-accent) 46%, transparent),
            0 14px 28px color-mix(in srgb, var(--sms-panel-accent) 32%, transparent);
        }

        .primary:disabled {
          background: color-mix(in srgb, var(--sms-panel-accent) 28%, var(--sms-panel-surface) 72%);
          color: color-mix(in srgb, var(--sms-panel-text) 58%, transparent);
          border-color: var(--sms-panel-border);
          box-shadow: none;
        }

        .secondary,
        .tab {
          color: var(--sms-panel-text);
          border: 1px solid var(--sms-panel-control-border);
          font-weight: 600;
        }

        .secondary {
          background: linear-gradient(
            180deg,
            color-mix(in srgb, var(--sms-panel-control-background) 92%, white 8%),
            color-mix(in srgb, var(--sms-panel-subtle-background) 88%, black 12%)
          );
          color: var(--sms-panel-text);
          border-color: var(--sms-panel-control-border);
          box-shadow:
            inset 0 1px 0 color-mix(in srgb, white 8%, transparent),
            0 0 0 1px var(--sms-panel-control-outline),
            0 2px 5px color-mix(in srgb, black 14%, transparent);
          min-width: 104px;
          border-radius: 12px;
        }

        .toolbar-button {
          min-width: 116px;
          min-height: 44px;
          padding-inline: 18px;
          font-weight: 700;
        }

        .tab {
          background: var(--sms-panel-subtle-background);
          box-shadow: 0 0 0 1px var(--sms-panel-control-outline);
        }

        .secondary.active,
        .tab.active {
          background: color-mix(in srgb, var(--sms-panel-accent) 18%, var(--sms-panel-surface-alt) 82%);
          border-color: var(--sms-panel-accent);
          color: var(--sms-panel-text);
        }

        .secondary:hover,
        .tab:hover,
        .message-item:hover {
          background: var(--sms-panel-surface-hover);
        }

        .stats {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
        }

        .stat {
          padding: 16px;
          border-radius: 14px;
          background: var(--sms-panel-subtle-background);
          border: 1px solid var(--sms-panel-card-border);
          box-shadow: inset 0 1px 0 color-mix(in srgb, white 6%, transparent);
        }

        .stat-label {
          color: var(--sms-panel-muted);
          font-size: 0.85rem;
          margin-bottom: 6px;
        }

        .stat-value {
          font-size: 1.7rem;
          font-weight: 700;
        }

        .banner {
          padding: 12px 14px;
          border-radius: 12px;
          font-size: 0.95rem;
        }

        .banner.error {
          background: color-mix(in srgb, var(--sms-panel-error) 14%, transparent);
          border: 1px solid color-mix(in srgb, var(--sms-panel-error) 48%, transparent);
        }

        .banner.notice {
          background: color-mix(in srgb, var(--sms-panel-success) 14%, transparent);
          border: 1px solid color-mix(in srgb, var(--sms-panel-success) 48%, transparent);
        }

        .workspace {
          display: grid;
          grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
          gap: 18px;
          align-items: start;
        }

        .list-pane,
        .detail-pane {
          padding: 18px;
          display: grid;
          gap: 14px;
          min-height: 520px;
        }

        .list-pane {
          background: var(--sms-panel-subtle-background);
          align-content: start;
        }

        .detail-pane {
          background: color-mix(in srgb, var(--sms-panel-card-background) 82%, var(--sms-panel-subtle-background) 18%);
        }

        .tabs {
          display: flex;
          gap: 10px;
        }

        .list-body {
          display: grid;
          gap: 14px;
          align-content: start;
          align-items: start;
          min-height: 0;
        }

        .messages {
          display: grid;
          gap: 10px;
          align-content: start;
          align-items: start;
          max-height: 560px;
          overflow: auto;
          padding-right: 4px;
          min-height: 0;
        }

        .message-item {
          width: 100%;
          text-align: left;
          padding: 11px 12px;
          border-radius: 14px;
          background: var(--sms-panel-card-background);
          border: 1px solid var(--sms-panel-control-border);
          box-shadow:
            inset 0 1px 0 color-mix(in srgb, white 6%, transparent),
            0 0 0 1px var(--sms-panel-control-outline),
            0 1px 2px color-mix(in srgb, black 10%, transparent);
        }

        .message-item.active {
          background: color-mix(in srgb, var(--sms-panel-accent-soft) 70%, var(--sms-panel-card-background) 30%);
          border-color: var(--sms-panel-accent);
          box-shadow:
            inset 0 1px 0 color-mix(in srgb, white 8%, transparent),
            0 0 0 1px var(--sms-panel-accent),
            0 0 0 3px color-mix(in srgb, var(--sms-panel-accent) 18%, transparent);
        }

        .message-row {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: start;
          margin-bottom: 5px;
        }

        .message-phone {
          display: grid;
          gap: 2px;
        }

        .message-phone strong {
          font-size: 0.98rem;
          line-height: 1.25;
        }

        .message-preview,
        .message-meta,
        .detail-label {
          color: var(--sms-panel-muted);
        }

        .message-preview {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          line-height: 1.32;
        }

        .message-meta {
          margin-top: 5px;
          font-size: 0.85rem;
        }

        .chip {
          border-radius: 999px;
          padding: 4px 10px;
          font-size: 0.75rem;
          letter-spacing: 0.03em;
          border: 1px solid var(--sms-panel-border);
          font-weight: 600;
        }

        .chip.unread {
          background: color-mix(in srgb, var(--sms-panel-warning) 20%, transparent);
        }

        .chip.muted {
          background: transparent;
        }

        .detail-card {
          display: grid;
          gap: 14px;
          align-content: start;
        }

        .detail-header {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: start;
        }

        .detail-header h2 {
          margin: 4px 0 0;
          font-size: 1.5rem;
          line-height: 1.15;
        }

        .detail-meta {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          padding: 12px 14px;
          border-radius: 12px;
          background: var(--sms-panel-subtle-background);
          border: 1px solid var(--sms-panel-card-border);
        }

        .detail-meta span {
          color: var(--sms-panel-muted);
        }

        .detail-body {
          padding: 18px;
          border-radius: 14px;
          background: var(--sms-panel-subtle-background);
          border: 1px solid var(--sms-panel-card-border);
          line-height: 1.6;
          min-height: 210px;
          white-space: normal;
          overflow-wrap: anywhere;
        }

        .composer {
          padding: 20px;
          display: grid;
          gap: 18px;
        }

        .composer-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 14px;
        }

        .phone-field {
          max-width: 340px;
        }

        .message-field textarea {
          min-height: 160px;
        }

        .composer-actions {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 14px;
          padding-top: 4px;
          border-top: 1px solid color-mix(in srgb, var(--sms-panel-border) 70%, transparent);
        }

        .empty {
          border: 1px dashed var(--sms-panel-control-outline);
          border-radius: 14px;
          padding: 20px;
          color: var(--sms-panel-muted);
          background: var(--sms-panel-subtle-background);
        }

        .detail-empty {
          min-height: 220px;
          display: grid;
          place-items: center;
        }

        .loading {
          color: var(--sms-panel-muted);
          font-size: 0.95rem;
        }

        @media (max-width: 980px) {
          :host {
            padding: 16px;
          }

          .hero-grid,
          .workspace,
          .composer-grid {
            grid-template-columns: 1fr;
          }

          .composer-actions {
            flex-direction: column;
            align-items: stretch;
          }

          .stats {
            grid-template-columns: 1fr;
          }
        }
      </style>
      <div class="shell">
        <section class="hero">
          <div class="hero-top">
            <div class="hero-copy">
              <div class="eyebrow">Cudy Router SMS</div>
              <h1>Inbox, outbox, and send tools in one place</h1>
              <div class="subtle">Device-page entities stay count-only. Use this panel for message bodies and sending.</div>
            </div>
            <button id="refresh-button" class="secondary toolbar-button" ${loading ? "disabled" : ""}>Refresh</button>
          </div>
          ${this._error ? `<div class="banner error">${this._escapeHtml(this._error)}</div>` : ""}
          ${this._notice ? `<div class="banner notice">${this._escapeHtml(this._notice)}</div>` : ""}
          <div class="hero-grid">
            <label>
              <div class="field-label">Router</div>
              <div class="control-shell">
                <select id="entry-select" ${this._entriesLoading || !this._entries.length ? "disabled" : ""}>
                  ${this._entries.length
                    ? this._entries
                        .map(
                          (entry) => `
                            <option value="${this._escapeHtml(entry.entry_id)}" ${entry.entry_id === this._selectedEntryId ? "selected" : ""}>
                              ${this._escapeHtml(entry.title)}${entry.model ? ` (${this._escapeHtml(entry.model)})` : ""}
                            </option>
                          `,
                        )
                        .join("")
                    : `<option value="">No SMS-capable routers available</option>`}
                </select>
              </div>
            </label>
            <div class="stats">
              <div class="stat">
                <div class="stat-label">Inbox</div>
                <div class="stat-value">${this._escapeHtml(counts.inbox)}</div>
              </div>
              <div class="stat">
                <div class="stat-label">Outbox</div>
                <div class="stat-value">${this._escapeHtml(counts.outbox)}</div>
              </div>
              <div class="stat">
                <div class="stat-label">Unread</div>
                <div class="stat-value">${this._escapeHtml(counts.unread)}</div>
              </div>
            </div>
          </div>
        </section>

        ${
          !this._entries.length
            ? `<section class="workspace"><div class="detail-pane"><div class="empty detail-empty">No SMS-capable Cudy Router entries are currently loaded.</div></div></section>`
            : `
              <section class="workspace">
                <div class="list-pane">
                  <div class="pane-header">
                    <div class="pane-title">
                      <div class="pane-kicker">Mailbox</div>
                      <h2>${this._selectedTab === "inbox" ? "Inbox" : "Outbox"}</h2>
                    </div>
                    <div class="tabs">
                      <button class="tab ${this._selectedTab === "inbox" ? "active" : ""}" data-tab="inbox">Inbox</button>
                      <button class="tab ${this._selectedTab === "outbox" ? "active" : ""}" data-tab="outbox">Outbox</button>
                    </div>
                  </div>
                  <div class="list-body">
                    ${loading ? `<div class="loading">Loading messages…</div>` : ""}
                    <div class="messages">${this._renderMessageList()}</div>
                  </div>
                </div>
                <div class="detail-pane">
                  <div class="pane-header">
                    <div class="pane-title">
                      <div class="pane-kicker">Reader</div>
                      <h2>${selectedMessage ? "Message details" : "Select a message"}</h2>
                    </div>
                    ${selectedMessage ? `<span class="subtle">${this._selectedTab === "inbox" ? "Inbox" : "Outbox"}</span>` : ""}
                  </div>
                  ${this._renderMessageDetail()}
                </div>
              </section>
            `
        }

        <section class="composer">
          <div class="pane-header">
            <div class="pane-title">
              <div class="eyebrow">Compose</div>
              <h2>Send SMS from Home Assistant</h2>
            </div>
            <div class="subtle">Use Reply on a selected message to prefill the recipient.</div>
          </div>
          <div class="composer-grid">
            <label class="phone-field">
              <div class="field-label">Phone number</div>
              <div class="control-shell">
                <input id="compose-phone" type="text" value="${this._escapeHtml(this._composePhone)}" placeholder="+441234567890" />
              </div>
            </label>
            <label class="message-field">
              <div class="field-label">Message</div>
              <div class="control-shell multiline">
                <textarea id="compose-message" placeholder="Write the SMS message here.">${this._escapeHtml(this._composeMessage)}</textarea>
              </div>
            </label>
          </div>
          <div class="composer-actions">
            <div class="subtle">Admins only. The router sends this message immediately through its modem.</div>
            <button id="send-button" class="primary" ${this._sendPending || !this._entries.length ? "disabled" : ""}>
              ${this._sendPending ? "Sending…" : "Send SMS"}
            </button>
          </div>
        </section>
      </div>
    `;

    this.shadowRoot.querySelector("#refresh-button")?.addEventListener("click", () => {
      this._loadEntries();
    });

    this.shadowRoot.querySelector("#entry-select")?.addEventListener("change", (event) => {
      this._selectedEntryId = event.target.value;
      this._selectedMessageKey = "";
      this._loadMessages();
    });

    this.shadowRoot.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => this._setSelectedTab(button.dataset.tab));
    });

    this.shadowRoot.querySelectorAll("[data-message-key]").forEach((button) => {
      button.addEventListener("click", () => {
        this._selectedMessageKey = button.dataset.messageKey || "";
        this._render();
      });
    });

    this.shadowRoot.querySelector("#reply-button")?.addEventListener("click", () => {
      this._replyToSelectedMessage();
    });

    this.shadowRoot.querySelector("#compose-phone")?.addEventListener("input", (event) => {
      this._composePhone = event.target.value;
    });

    this.shadowRoot.querySelector("#compose-message")?.addEventListener("input", (event) => {
      this._composeMessage = event.target.value;
    });

    this.shadowRoot.querySelector("#send-button")?.addEventListener("click", () => {
      this._sendSms();
    });
  }
}

customElements.define("cudy-router-sms-panel", CudyRouterSmsPanel);
