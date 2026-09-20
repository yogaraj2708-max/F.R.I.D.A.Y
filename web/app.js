/**
 * AURA — Thoughtful AI Assistant Web Interface
 * Interactive Client Logic & Editorial UX Flows
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const chatForm = document.getElementById('chatForm');
  const promptInput = document.getElementById('promptInput');
  const sendBtn = document.getElementById('sendBtn');
  const dynamicMessages = document.getElementById('dynamicMessages');
  const thinkingIndicator = document.getElementById('thinkingIndicator');
  const thinkingStatus = document.getElementById('thinkingStatus');
  const chatViewport = document.getElementById('chatViewport');
  const clearChatBtn = document.getElementById('clearChatBtn');
  const exportBtn = document.getElementById('exportBtn');
  const fileInput = document.getElementById('fileInput');
  const attachBtn = document.getElementById('attachBtn');
  const attachmentsTray = document.getElementById('attachmentsTray');
  const chipFilename = document.getElementById('chipFilename');
  const removeAttachmentBtn = document.getElementById('removeAttachmentBtn');
  const voiceBtn = document.getElementById('voiceBtn');
  const deepResearchBtn = document.getElementById('deepResearchBtn');
  const contextIndicator = document.getElementById('contextIndicator');
  const toneToggleBtn = document.getElementById('toneToggleBtn');
  const suggestionCards = document.querySelectorAll('.suggestion-card');
  const themeToggleBtn = document.getElementById('themeToggleBtn');
  const themeIcon = document.getElementById('themeIcon');
  const themeLabel = document.getElementById('themeLabel');

  // ── THEME TOGGLE (LIGHT / DARK) ──
  function initTheme() {
    const savedTheme = localStorage.getItem('aura_theme') || 
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    setTheme(savedTheme);
  }

  function setTheme(theme) {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      if (themeIcon) themeIcon.textContent = '☀️';
      if (themeLabel) themeLabel.textContent = 'Light';
      if (themeToggleBtn) themeToggleBtn.setAttribute('title', 'Switch to Light Mode (Cream)');
      localStorage.setItem('aura_theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
      if (themeIcon) themeIcon.textContent = '🌙';
      if (themeLabel) themeLabel.textContent = 'Dark';
      if (themeToggleBtn) themeToggleBtn.setAttribute('title', 'Switch to Dark Mode (Obsidian)');
      localStorage.setItem('aura_theme', 'light');
    }
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      setTheme(current === 'dark' ? 'light' : 'dark');
    });
  }

  initTheme();

  // State
  let isGenerating = false;
  let attachedFile = null;
  let isRecording = false;
  let deepResearchActive = false;
  let currentTone = 'Thoughtful & Balanced';

  const tones = [
    'Thoughtful & Balanced',
    'Concise & Direct',
    'Deeply Exploratory',
    'Archival & Philosophical'
  ];

  // ── AUTO-RESIZING TEXTAREA ──
  function autoResizeTextarea() {
    promptInput.style.height = 'auto';
    const newHeight = Math.min(promptInput.scrollHeight, 200);
    promptInput.style.height = `${newHeight}px`;
  }

  promptInput.addEventListener('input', autoResizeTextarea);

  // ── KEYBOARD SHORTCUTS ──
  promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isGenerating && promptInput.value.trim().length > 0) {
        handleUserSubmit();
      }
    }
  });

  // Global Ctrl+L to clear chat
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
      e.preventDefault();
      clearChat();
    }
  });

  // ── FORM SUBMISSION ──
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!isGenerating && promptInput.value.trim().length > 0) {
      handleUserSubmit();
    }
  });

  function handleUserSubmit() {
    const text = promptInput.value.trim();
    if (!text) return;

    // Capture attachment details if present
    const attachment = attachedFile ? { ...attachedFile } : null;

    // Clear input & reset attachment
    promptInput.value = '';
    autoResizeTextarea();
    clearAttachment();

    // Render User Message
    renderUserMessage(text, attachment);

    // Trigger AI Generation Flow
    simulateAIResponse(text, attachment);
  }

  // ── RENDER USER MESSAGE ──
  function renderUserMessage(text, attachment) {
    const timeStr = formatCurrentTime();
    const row = document.createElement('article');
    row.className = 'message-row user-row';
    row.setAttribute('aria-label', 'Message from You');

    let attachmentHtml = '';
    if (attachment) {
      attachmentHtml = `
        <div style="margin-bottom: 8px; display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; background: rgba(253, 251, 247, 0.15); border-radius: 9999px; font-size: 0.775rem; color: #FDFBF7;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
          <span>${escapeHtml(attachment.name)}</span>
        </div>
      `;
    }

    row.innerHTML = `
      <div class="message-meta">
        <span class="sender-name">You</span>
        <time class="timestamp">${timeStr}</time>
      </div>
      <div class="bubble user-bubble">
        ${attachmentHtml}
        <p>${escapeHtml(text)}</p>
      </div>
    `;

    dynamicMessages.appendChild(row);
    scrollToBottom();
  }

  // ── SIMULATED EDITORIAL AI RESPONSE ──
  async function simulateAIResponse(userPrompt, attachment) {
    isGenerating = true;
    sendBtn.disabled = true;

    // Show Organic Thinking Spinner
    thinkingIndicator.style.display = 'flex';
    scrollToBottom();

    // Subtle phased status messages for organic feel
    const statuses = deepResearchActive ? [
      "Consulting verified archival sources...",
      "Corroborating multi-source findings...",
      "Synthesizing an authoritative dossier..."
    ] : [
      "Reflecting on the core premise...",
      "Formulating a nuanced perspective...",
      "Structuring thoughtful prose..."
    ];

    let statusIndex = 0;
    thinkingStatus.textContent = statuses[0];
    const statusInterval = setInterval(() => {
      statusIndex = (statusIndex + 1) % statuses.length;
      thinkingStatus.textContent = statuses[statusIndex];
    }, 900);

    // Artificial deliberate delay to simulate thoughtful depth (1.8s)
    await new Promise(r => setTimeout(r, 1800));
    clearInterval(statusInterval);

    // Hide thinking indicator
    thinkingIndicator.style.display = 'none';

    // Generate response content
    const responsePayload = generateEditorialContent(userPrompt, deepResearchActive, attachment);

    // Render Assistant Message with streaming effect
    await renderAssistantStreaming(responsePayload);

    isGenerating = false;
    sendBtn.disabled = false;
    promptInput.focus();
  }

  // ── STREAMING ASSISTANT MESSAGE ──
  async function renderAssistantStreaming(payload) {
    const timeStr = formatCurrentTime();
    const row = document.createElement('article');
    row.className = 'message-row assistant-row';
    row.setAttribute('aria-label', 'Message from Aura');

    row.innerHTML = `
      <div class="message-meta">
        <div class="assistant-ident">
          <span class="mini-avatar">A</span>
          <span class="sender-name">Aura</span>
        </div>
        <time class="timestamp">${timeStr}</time>
      </div>
      <div class="bubble assistant-bubble">
        <div class="prose" id="proseTarget"></div>
        <div class="bubble-actions" style="opacity: 0; transition: opacity 0.3s ease;">
          <button class="bubble-action-btn copy-btn" title="Copy response" aria-label="Copy message text">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
            <span>Copy</span>
          </button>
          <button class="bubble-action-btn speak-btn" title="Listen aloud" aria-label="Read message aloud">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
            <span>Read</span>
          </button>
          <span class="model-badge">Aura 2.0 • Editorial Mode</span>
        </div>
      </div>
    `;

    dynamicMessages.appendChild(row);
    const proseTarget = row.querySelector('#proseTarget');
    const actionsBar = row.querySelector('.bubble-actions');

    // Simulate word-by-word streaming for natural pacing
    const tokens = payload.html.split(' ');
    let currentHtml = '';

    for (let i = 0; i < tokens.length; i++) {
      currentHtml += (i === 0 ? '' : ' ') + tokens[i];
      proseTarget.innerHTML = currentHtml;
      scrollToBottom();
      await new Promise(r => setTimeout(r, 18));
    }

    // Reveal actions
    actionsBar.style.opacity = '1';

    // Attach copy & TTS listeners to new bubble
    attachBubbleActionListeners(row, payload.rawText);
  }

  // ── EDITORIAL CONTENT GENERATOR ──
  function generateEditorialContent(prompt, isDeep, attachment) {
    const lower = prompt.toLowerCase();

    if (lower.includes('architecture') || lower.includes('monolith') || lower.includes('microservice')) {
      return {
        rawText: "The debate between monolithic and microservices architectures is often framed as a technical dispute, but at its foundation, it is an organizational and cognitive question.",
        html: `
          <p>
            The debate between monolithic and microservices architectures is often framed as a technical dispute, but at its foundation, it is an organizational and cognitive question.
          </p>
          <blockquote>
            "Complexity is the silent tax on developer momentum. Systems should be as simple as the problem allows, and no simpler."
          </blockquote>
          <p>A balanced synthesis of the trade-offs reveals three fundamental insights:</p>
          <ul>
            <li><strong>Cognitive Density:</strong> Well-structured modular monoliths allow single engineers to hold the entire domain model in memory, drastically accelerating initial velocity.</li>
            <li><strong>Distributed Overhead:</strong> Microservices do not eliminate complexity; they relocate it from application memory into the network layer, introducing distributed tracing, eventual consistency, and operational friction.</li>
            <li><strong>Evolutionary Decoupling:</strong> The most resilient teams begin with strict modular boundaries inside a unified codebase, splitting out discrete services only when independent deployment cadences become an acute organizational requirement.</li>
          </ul>
        `
      };
    }

    if (lower.includes('email') || lower.includes('decline') || lower.includes('invitation')) {
      return {
        rawText: "Here is a thoughtful draft crafted to decline with warmth while keeping the relationship solid.",
        html: `
          <p>Here is an editorial draft crafted to decline the invitation with genuine warmth while leaving the doorway open for future collaboration:</p>
          
          <pre><code>Subject: Warm thanks & a note on [Event/Project Name]

Dear [Name],

Thank you sincerely for inviting me to participate in [Event/Project]. It is rare to see an initiative approached with such clear intentionality, and I am grateful you thought of me.

Regrettably, due to existing commitments requiring my undivided focus over the coming months, I will not be able to join you this time. I want to ensure I only step into projects where I can contribute at the depth they deserve.

I look forward to watching this unfold and would welcome the chance to connect again down the road. Wishing you every success with the launch.

With warm regards,
[Your Name]</code></pre>

          <p><em>Key nuance:</em> By articulating that you decline to protect the depth of your contribution, you honor both your own boundaries and the value of their project.</p>
        `
      };
    }

    if (lower.includes('scandinavian') || lower.includes('interior') || lower.includes('design') || lower.includes('minimal')) {
      return {
        rawText: "Scandinavian design is fundamentally an exploration of light, warmth, and unhurried space.",
        html: `
          <p>
            Scandinavian design is fundamentally an exploration of light, warmth, and unhurried space. In Nordic climates where winter daylight is scarce, interiors must act as reflective vessels that preserve peace.
          </p>
          <blockquote>
            "Lagom—not too little, not too much. Just enough to let the mind breathe."
          </blockquote>
          <ul>
            <li><strong>Material Honesty:</strong> Untreated birch, linen, and chalky plaster reflect light softly rather than creating harsh specular glare.</li>
            <li><strong>Functional Negative Space:</strong> Empty corners are not viewed as vacancies waiting to be decorated; they are visual pauses that lower cognitive arousal.</li>
            <li><strong>Warm Earth Pigments:</strong> Terracotta, muted ochre, and sage ground the cool Nordic light, transforming functional minimalism into restorative sanctuary.</li>
          </ul>
        `
      };
    }

    // Default deep editorial response
    const deepPrefix = isDeep ? `<p><strong>◈ Deep Research Directive:</strong> Synthesizing curated historical, physiological, and technical telemetry on <em>"${escapeHtml(prompt)}"</em>.</p>` : '';
    const fileNote = attachment ? `<p><em>Reflecting upon attached source: <code>${escapeHtml(attachment.name)}</code></em></p>` : '';

    return {
      rawText: `Reflections on: ${prompt}. A deliberate, high-legibility perspective synthesizing core principles.`,
      html: `
        ${deepPrefix}
        ${fileNote}
        <p>
          When examining <strong>${escapeHtml(prompt)}</strong>, the most insightful approach is to strip away ephemeral trends and inspect the underlying first principles.
        </p>
        <blockquote>
          "Clarity is not born from adding information, but from discerning the signal that truly warrants attention."
        </blockquote>
        <p>Three core considerations emerge from this inquiry:</p>
        <ul>
          <li><strong>Intentional Foundations:</strong> High-leverage outcomes are consistently driven by deep, focused alignment rather than rapid, reactive iteration.</li>
          <li><strong>Sustainable Constraints:</strong> Imposing strict boundaries—whether in visual palettes, technical dependencies, or scope—cultivates enduring resilience.</li>
          <li><strong>Human Equilibrium:</strong> Any tool, system, or writing piece must ultimately respect human cognitive limits and leave the reader calmer than it found them.</li>
        </ul>
        <p>If you would like to explore any specific facet further, we can examine the strategic implications or draft an actionable summary.</p>
      `
    };
  }

  // ── ATTACHMENT HANDLING ──
  attachBtn.addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      attachedFile = {
        name: file.name,
        size: file.size,
        type: file.type
      };
      chipFilename.textContent = file.name;
      attachmentsTray.style.display = 'flex';
    }
  });

  removeAttachmentBtn.addEventListener('click', clearAttachment);

  function clearAttachment() {
    attachedFile = null;
    fileInput.value = '';
    attachmentsTray.style.display = 'none';
  }

  // ── VOICE DICTATION SIMULATION ──
  voiceBtn.addEventListener('click', () => {
    isRecording = !isRecording;
    if (isRecording) {
      voiceBtn.classList.add('active-state');
      voiceBtn.setAttribute('title', 'Listening... Click to stop');
      promptInput.placeholder = 'Listening attentively to your thoughts...';
      
      // Simulate speech input after a pause
      setTimeout(() => {
        if (isRecording) {
          promptInput.value = "How does intentional whitespace improve reading comprehension in long-form essays?";
          autoResizeTextarea();
          voiceBtn.classList.remove('active-state');
          voiceBtn.setAttribute('title', 'Speak your thought (Hold or Click)');
          promptInput.placeholder = 'Ask anything, reflect on an idea, or paste thoughts...';
          isRecording = false;
        }
      }, 2500);
    } else {
      voiceBtn.classList.remove('active-state');
      voiceBtn.setAttribute('title', 'Speak your thought (Hold or Click)');
      promptInput.placeholder = 'Ask anything, reflect on an idea, or paste thoughts...';
    }
  });

  // ── DEEP RESEARCH TOGGLE ──
  deepResearchBtn.addEventListener('click', () => {
    deepResearchActive = !deepResearchActive;
    deepResearchBtn.setAttribute('aria-pressed', deepResearchActive ? 'true' : 'false');
  });

  // ── TONE SELECTOR CYCLING ──
  toneToggleBtn.addEventListener('click', () => {
    const currentIndex = tones.indexOf(currentTone);
    const nextIndex = (currentIndex + 1) % tones.length;
    currentTone = tones[nextIndex];
    contextIndicator.querySelector('.pill-text').textContent = `Tone: ${currentTone}`;
  });

  // ── SUGGESTION CARDS ──
  suggestionCards.forEach(card => {
    card.addEventListener('click', () => {
      const prompt = card.getAttribute('data-prompt');
      if (prompt) {
        promptInput.value = prompt;
        autoResizeTextarea();
        handleUserSubmit();
      }
    });
  });

  // ── COPY & TTS ACTIONS ──
  function attachBubbleActionListeners(container, textToCopy) {
    const copyBtn = container.querySelector('.copy-btn');
    const speakBtn = container.querySelector('.speak-btn');

    if (copyBtn) {
      copyBtn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(textToCopy);
          const span = copyBtn.querySelector('span');
          const originalText = span.textContent;
          span.textContent = 'Copied!';
          copyBtn.style.borderColor = 'var(--accent-sage)';
          copyBtn.style.color = 'var(--accent-sage)';
          setTimeout(() => {
            span.textContent = originalText;
            copyBtn.style.borderColor = '';
            copyBtn.style.color = '';
          }, 1800);
        } catch (err) {
          console.error('Clipboard copy failed:', err);
        }
      });
    }

    if (speakBtn) {
      speakBtn.addEventListener('click', () => {
        if ('speechSynthesis' in window) {
          if (window.speechSynthesis.speaking) {
            window.speechSynthesis.cancel();
            speakBtn.classList.remove('active-state');
            return;
          }

          const utterance = new SpeechSynthesisUtterance(textToCopy);
          utterance.rate = 0.95; // Calm, measured pacing
          utterance.pitch = 1.0;
          
          speakBtn.classList.add('active-state');
          utterance.onend = () => speakBtn.classList.remove('active-state');
          utterance.onerror = () => speakBtn.classList.remove('active-state');

          window.speechSynthesis.speak(utterance);
        }
      });
    }
  }

  // Attach to initial seed assistant bubble
  const initialAssistantBubble = document.querySelector('.assistant-row .assistant-bubble');
  if (initialAssistantBubble) {
    const initialText = initialAssistantBubble.querySelector('.prose').innerText;
    attachBubbleActionListeners(initialAssistantBubble.parentElement, initialText);
  }

  // ── CLEAR CHAT ──
  clearChatBtn.addEventListener('click', clearChat);

  function clearChat() {
    dynamicMessages.innerHTML = '';
    promptInput.value = '';
    autoResizeTextarea();
    clearAttachment();
    scrollToTop();
  }

  // ── EXPORT CHAT ──
  exportBtn.addEventListener('click', () => {
    const rows = document.querySelectorAll('.message-row');
    let md = `# Dialogue with Aura — ${new Date().toLocaleDateString()}\n\n`;

    rows.forEach(row => {
      const sender = row.querySelector('.sender-name')?.innerText || 'Unknown';
      const time = row.querySelector('.timestamp')?.innerText || '';
      const text = row.querySelector('.bubble')?.innerText.trim() || '';

      md += `### ${sender} (${time})\n\n${text}\n\n---\n\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aura-dialogue-${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  // ── UTILITIES ──
  function scrollToBottom() {
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: 'smooth'
    });
  }

  function scrollToTop() {
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    });
  }

  function formatCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
});
