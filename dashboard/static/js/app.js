/* Dashboard client-side logic */

function setStatus(msg, type) {
    const el = document.getElementById('action-status');
    el.textContent = msg;
    el.className = 'action-status ' + type;
}

function withSection(url) {
    const sec = window.__SECTION;
    if (!sec) return url;
    return url + (url.includes('?') ? '&' : '?') + 'section=' + encodeURIComponent(sec);
}

async function apiCall(url, method = 'POST', body = null) {
    const opts = { method };
    if (body) {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(withSection(url), opts);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
}

async function transcribe(rowId) {
    const btn = document.querySelector('[onclick*="transcribe"]');
    if (btn) { btn.classList.add('loading'); btn.textContent = 'Transcribing...'; }
    setStatus('Extracting audio and running Whisper transcription... This may take a minute.', 'loading');

    try {
        const data = await apiCall(`/api/transcribe/${rowId}`);
        document.getElementById('transcription-persian').textContent = data.transcription_persian || '—';
        document.getElementById('transcription-english').textContent = data.transcription_english || '—';
        setStatus('Transcription complete!', 'success');
    } catch (e) {
        setStatus('Transcription failed: ' + e.message, 'error');
    } finally {
        if (btn) { btn.classList.remove('loading'); btn.textContent = 'Transcribe Audio'; }
    }
}

async function runOCR(rowId) {
    const btn = document.querySelector('[onclick*="runOCR"]');
    if (btn) { btn.classList.add('loading'); btn.textContent = 'Running OCR...'; }
    setStatus('Running OCR with Claude Vision (Persian + English)... This may take a moment.', 'loading');

    try {
        const data = await apiCall(`/api/ocr/${rowId}`);
        document.getElementById('ocr-persian').value = data.ocr_persian || '';
        document.getElementById('ocr-english').value = data.ocr_english || '';
        setStatus('OCR complete!', 'success');
    } catch (e) {
        setStatus('OCR failed: ' + e.message, 'error');
    } finally {
        if (btn) { btn.classList.remove('loading'); btn.textContent = 'OCR Screen Text'; }
    }
}

async function takeScreenshots(rowId) {
    const btn = document.querySelector('[onclick*="takeScreenshots"]');
    if (btn) { btn.classList.add('loading'); btn.textContent = 'Capturing...'; }
    setStatus('Extracting 3 screenshots (beginning, middle, end)...', 'loading');

    try {
        const data = await apiCall(`/api/screenshots/${rowId}`);
        setStatus(`Captured ${data.count} screenshots! Reloading...`, 'success');
        setTimeout(() => location.reload(), 1500);
    } catch (e) {
        setStatus('Screenshot capture failed: ' + e.message, 'error');
    } finally {
        if (btn) { btn.classList.remove('loading'); btn.textContent = 'Take Screenshots'; }
    }
}

async function saveKeywords(rowId) {
    const input = document.getElementById('keywords-input');
    try {
        await apiCall(`/api/keywords/${rowId}`, 'POST', { keywords: input.value });
        setStatus('Keywords saved!', 'success');
    } catch (e) {
        setStatus('Failed to save keywords: ' + e.message, 'error');
    }
}

async function saveOCR(rowId) {
    const persian = document.getElementById('ocr-persian');
    const english = document.getElementById('ocr-english');
    const status = document.getElementById('save-ocr-status');
    status.textContent = 'Saving...';
    status.style.color = '#f0c040';

    try {
        await apiCall(`/api/save-ocr/${rowId}`, 'POST', {
            ocr_text_persian: persian.value,
            ocr_text_english: english.value,
        });
        status.textContent = 'Saved!';
        status.style.color = '#4caf50';
    } catch (e) {
        status.textContent = 'Failed: ' + e.message;
        status.style.color = '#f44336';
    }
}

async function saveTranscription(rowId) {
    const persianV2 = document.getElementById('transcription-persian-v2');
    const english = document.getElementById('transcription-english');
    const status = document.getElementById('save-transcription-status');
    status.textContent = 'Saving...';
    status.style.color = '#f0c040';

    try {
        await apiCall(`/api/save-transcription/${rowId}`, 'POST', {
            audio_transcription_persian_v2: persianV2.value,
            audio_transcription_english: english.value,
        });
        status.textContent = 'Saved!';
        status.style.color = '#4caf50';
    } catch (e) {
        status.textContent = 'Failed: ' + e.message;
        status.style.color = '#f44336';
    }
}

async function saveTheme(rowId) {
    const input = document.getElementById('theme-input');
    try {
        await apiCall(`/api/theme/${rowId}`, 'POST', { theme: input.value });
        setStatus('Theme saved!', 'success');
    } catch (e) {
        setStatus('Failed to save theme: ' + e.message, 'error');
    }
}

// Commit every hand-coding field in one go, then jump to the next row still in
// the active queue. Once the theme is set the row drops out of the `unlabelled`
// filter, so there is no way back to a row you have already coded.
async function saveAllAndNext(rowId, nextUrl) {
    const theme = document.getElementById('theme-input');
    if (theme && !theme.value) {
        setStatus('Pick a theme before moving on.', 'error');
        return;
    }
    try {
        setStatus('Saving...', 'loading');
        await apiCall(`/api/theme/${rowId}`, 'POST', { theme: theme.value });

        for (const field of ['theme2', 'theme3', 'theme4']) {
            const el = document.getElementById(field + '-input');
            if (el) {
                await apiCall(`/api/theme-extra/${rowId}`, 'POST',
                              { field: field, value: el.value });
            }
        }
        const kw = document.getElementById('keywords-input');
        if (kw) await apiCall(`/api/keywords/${rowId}`, 'POST', { keywords: kw.value });

        const person = document.getElementById('person-input');
        if (person) await apiCall(`/api/person/${rowId}`, 'POST', { include_person: person.value });

        const ai = document.getElementById('ai-generated-input');
        if (ai) await apiCall(`/api/ai-generated/${rowId}`, 'POST', { AI_generated: ai.value });

        setStatus('Saved — moving on...', 'success');
        window.location.href = nextUrl;
    } catch (e) {
        setStatus('Save failed, staying put: ' + e.message, 'error');
    }
}

async function saveThemeExtra(rowId, field) {
    const input = document.getElementById(field + '-input');
    try {
        await apiCall(`/api/theme-extra/${rowId}`, 'POST', { field: field, value: input.value });
        setStatus(field + ' saved!', 'success');
    } catch (e) {
        setStatus('Failed to save ' + field + ': ' + e.message, 'error');
    }
}

async function savePerson(rowId) {
    const input = document.getElementById('person-input');
    try {
        await apiCall(`/api/person/${rowId}`, 'POST', { include_person: input.value });
        setStatus('Person saved!', 'success');
    } catch (e) {
        setStatus('Failed to save person: ' + e.message, 'error');
    }
}

async function saveAIGenerated(rowId) {
    const input = document.getElementById('ai-generated-input');
    try {
        await apiCall(`/api/ai-generated/${rowId}`, 'POST', { AI_generated: input.value });
        setStatus('AI Generated saved!', 'success');
    } catch (e) {
        setStatus('Failed to save: ' + e.message, 'error');
    }
}

async function autoKeywords(rowId) {
    const btn = document.querySelector('[onclick*="autoKeywords"]');
    if (btn) { btn.classList.add('loading'); btn.textContent = 'Generating...'; }
    setStatus('Generating keywords with Claude...', 'loading');

    try {
        const data = await apiCall(`/api/auto-keywords/${rowId}`);
        document.getElementById('keywords-input').value = data.keywords;
        setStatus('Keywords generated!', 'success');
    } catch (e) {
        setStatus('Keyword generation failed: ' + e.message, 'error');
    } finally {
        if (btn) { btn.classList.remove('loading'); btn.textContent = 'Auto-Generate Keywords'; }
    }
}
