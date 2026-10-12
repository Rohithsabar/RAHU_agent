const messages = document.getElementById('messages');
const welcome = document.getElementById('welcome');
const input = document.getElementById('commandInput');
const sendButton = document.getElementById('sendButton');

function addMessage(role, text, error = false) {
  welcome.hidden = true;
  const message = document.createElement('div');
  message.className = `message ${role}${error ? ' error' : ''}`;
  message.textContent = text;
  messages.append(message);
  message.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : { error: 'The local app returned an unexpected response. Refresh RAHU and try again.' };
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  if (!contentType.includes('application/json')) throw new Error(payload.error);
  return payload;
}

async function refreshStatus() {
  const light = document.getElementById('serviceLight');
  try {
    const data = await fetchJson('/api/status');
    light.classList.add('ready');
    document.getElementById('serviceStatus').textContent = data.running ? 'Assistant ready on this computer' : 'Assistant is stopping';
    document.getElementById('onlineModel').textContent = data.ai.online_configured ? data.ai.online_model : 'Set RAHU_AI_API_KEY to enable';
    if (document.activeElement !== document.getElementById('onlineUrl')) document.getElementById('onlineUrl').value = data.ai.online_url;
    if (document.activeElement !== document.getElementById('onlineModelInput')) document.getElementById('onlineModelInput').value = data.ai.online_model;
    if (document.activeElement !== document.getElementById('localUrl')) document.getElementById('localUrl').value = data.ai.local_url;
    if (document.activeElement !== document.getElementById('localModelInput')) document.getElementById('localModelInput').value = data.ai.local_model;
    document.getElementById('onlineState').textContent = data.ai.online_configured ? 'READY' : 'OFF';
    document.getElementById('onlineState').classList.toggle('on', data.ai.online_configured);
    document.getElementById('localModel').textContent = `Ollama · ${data.ai.local_model}`;
    document.getElementById('aiBadge').textContent = data.ai.online_configured
      ? (data.ai.local_available ? 'HYBRID' : 'ONLINE AI')
      : (data.ai.local_available ? 'OFFLINE AI' : 'LOCAL TOOLS');
    document.getElementById('localState').textContent = data.ai.local_available ? 'READY' : 'NOT RUNNING';
    document.getElementById('localState').classList.toggle('on', data.ai.local_available);
    document.getElementById('voiceStatus').textContent = data.voice_enabled ? 'Enabled' : 'Disabled';
    document.getElementById('voiceToggle').classList.toggle('enabled', data.voice_enabled);
  } catch (error) {
    light.classList.remove('ready');
    document.getElementById('serviceStatus').textContent = 'Cannot reach local assistant';
  }
}

async function sendRequest(text = input.value) {
  const command = text.trim();
  if (!command) return;
  addMessage('user', command);
  input.value = '';
  sendButton.disabled = true;
  sendButton.querySelector('span').textContent = 'Working...';
  try {
    const data = await fetchJson('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: command }),
    });
    addMessage('assistant', data.response);
  } catch (error) {
    addMessage('assistant', error.message, true);
  } finally {
    sendButton.disabled = false;
    sendButton.querySelector('span').textContent = 'Send request';
    input.focus();
    refreshStatus();
  }
}

document.getElementById('commandForm').addEventListener('submit', (event) => {
  event.preventDefault();
  sendRequest();
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendRequest();
  }
});

document.querySelectorAll('[data-prompt]').forEach((button) => {
  button.addEventListener('click', () => {
    input.value = button.dataset.prompt;
    input.focus();
  });
});

document.querySelectorAll('[data-action="help"]').forEach((button) => {
  button.addEventListener('click', () => sendRequest('help'));
});

document.querySelectorAll('[data-api]').forEach((button) => {
  button.addEventListener('click', async () => {
    try {
      const data = await fetchJson(button.dataset.api, { method: 'POST' });
      addMessage('assistant', data.response);
    } catch (error) {
      addMessage('assistant', error.message, true);
    }
  });
});

document.getElementById('savePayment').addEventListener('click', async () => {
  try {
    const data = await fetchJson('/api/payment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        schedule: document.getElementById('paymentSchedule').value || 'daily',
        method: document.getElementById('paymentMethod').value || 'Bank transfer',
      }),
    });
    addMessage('assistant', data.response);
  } catch (error) {
    addMessage('assistant', error.message, true);
  }
});

document.getElementById('refreshStatus').addEventListener('click', refreshStatus);
document.getElementById('geminiPreset').addEventListener('click', () => {
  document.getElementById('onlineUrl').value = 'https://generativelanguage.googleapis.com/v1beta/openai';
  document.getElementById('onlineModelInput').value = 'gemini-3.8-flash';
  document.getElementById('onlineApiKey').focus();
});
document.getElementById('saveAiSettings').addEventListener('click', async () => {
  const status = document.getElementById('aiSaveStatus');
  status.textContent = 'Saving...';
  try {
    const result = await fetchJson('/api/ai/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        online_url: document.getElementById('onlineUrl').value,
        online_model: document.getElementById('onlineModelInput').value,
        api_key: document.getElementById('onlineApiKey').value,
        local_url: document.getElementById('localUrl').value,
        local_model: document.getElementById('localModelInput').value,
      }),
    });
    document.getElementById('onlineApiKey').value = '';
    status.textContent = result.message;
    await refreshStatus();
  } catch (error) {
    status.textContent = error.message;
  }
});

document.getElementById('clearAiKey').addEventListener('click', async () => {
  const status = document.getElementById('aiSaveStatus');
  try {
    const result = await fetchJson('/api/ai/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clear_api_key: true }),
    });
    status.textContent = result.message;
    await refreshStatus();
  } catch (error) {
    status.textContent = error.message;
  }
});
document.getElementById('voiceButton').addEventListener('click', async () => {
  try {
    const enabling = !document.getElementById('voiceToggle').classList.contains('enabled');
    if (enabling) {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone permission is not available in this browser.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
    }
    const data = await fetchJson('/api/voice/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: enabling }),
    });
    document.getElementById('voiceStatus').textContent = data.enabled ? 'Enabled' : 'Disabled';
    document.getElementById('voiceToggle').classList.toggle('enabled', data.enabled);
  } catch (error) {
    addMessage('assistant', error.message, true);
  }
});

refreshStatus();
setInterval(refreshStatus, 15000);
input.focus();