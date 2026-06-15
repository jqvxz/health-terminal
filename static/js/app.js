/* HealthTerminal V1 — Core App JavaScript */

// Sidebar toggle
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    sidebar.classList.toggle('open');
    overlay.style.display = sidebar.classList.contains('open') ? 'block' : 'none';
}

// Toast notifications
function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success'
        ? '<svg width="16" height="16" fill="none" stroke="var(--accent)" stroke-width="2" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>'
        : '<svg width="16" height="16" fill="none" stroke="var(--danger)" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>';
    toast.innerHTML = `${icon}<span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(20px)'; setTimeout(() => toast.remove(), 300); }, 4000);
}

// Animated counter for stat values
function animateValue(el, end, duration = 600, suffix = '') {
    if (!el || isNaN(end)) { el.textContent = end + suffix; return; }
    const start = 0;
    const range = end - start;
    const startTime = performance.now();
    el.classList.add('stat-animated');

    function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        const current = Math.round(start + range * eased);
        el.textContent = current.toLocaleString() + suffix;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// Animate a decimal value
function animateDecimal(el, end, decimals = 1, duration = 600, suffix = '') {
    if (!el || isNaN(end)) { el.textContent = end + suffix; return; }
    const startTime = performance.now();
    el.classList.add('stat-animated');

    function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = (end * eased).toFixed(decimals);
        el.textContent = current + suffix;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// Format relative time
function timeAgo(dateStr) {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    return date.toLocaleDateString();
}

// Markdown-lite renderer for AI responses
function formatAI(text) {
    if (!text) return '';

    // Extract <think>...</think> blocks (reasoning model output)
    let thinkingHtml = '';
    const thinkMatch = text.match(/<think>([\s\S]*?)<\/think>/i);
    if (thinkMatch) {
        const thinkContent = thinkMatch[1].trim();
        text = text.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
        if (thinkContent) {
            thinkingHtml = `<details class="ai-thinking"><summary class="ai-thinking-toggle"><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 2l4 4-4 4"/></svg>Thinking</summary><div class="ai-thinking-content">${thinkContent.replace(/\n/g, '<br>')}</div></details>`;
        }
    }
    // Strip emojis (Unicode emoji ranges)
    text = text.replace(/[\u{1F600}-\u{1F64F}]/gu, '')   // emoticons
               .replace(/[\u{1F300}-\u{1F5FF}]/gu, '')   // symbols & pictographs
               .replace(/[\u{1F680}-\u{1F6FF}]/gu, '')   // transport & map
               .replace(/[\u{1F1E0}-\u{1F1FF}]/gu, '')   // flags
               .replace(/[\u{2600}-\u{26FF}]/gu, '')      // misc symbols
               .replace(/[\u{2700}-\u{27BF}]/gu, '')      // dingbats
               .replace(/[\u{FE00}-\u{FE0F}]/gu, '')      // variation selectors
               .replace(/[\u{1F900}-\u{1F9FF}]/gu, '')   // supplemental
               .replace(/[\u{1FA00}-\u{1FA6F}]/gu, '')   // chess symbols
               .replace(/[\u{1FA70}-\u{1FAFF}]/gu, '')   // symbols extended
               .replace(/[\u{200D}]/gu, '')               // zero width joiner
               .replace(/[\u{20E3}]/gu, '')               // combining enclosing keycap
               .replace(/[\u{E0020}-\u{E007F}]/gu, '');   // tags

    // Clean up LaTeX artifacts
    text = text.replace(/\\\[[\s\S]*?\\\]/g, '')            // remove \[...\] blocks
               .replace(/\$\$[\s\S]*?\$\$/g, '')           // remove $$...$$ blocks
               .replace(/\\text\{([^}]*)\}/g, '$1')        // \text{kcal} → kcal
               .replace(/\\frac\{([^}]*)\}\{([^}]*)\}/g, '($1 / $2)') // \frac{a}{b} → (a / b)
               .replace(/\\times/g, 'x')                   // \times → x
               .replace(/\\approx/g, '≈')                  // \approx → ≈
               .replace(/\\(?:left|right)[()[\]{}]/g, '')  // \left( \right) etc
               .replace(/\\\\/g, '')                        // stray backslashes

    // First pass: convert pipe tables to HTML
    const lines = text.split('\n');
    const result = [];
    let inTable = false;
    let tableRows = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        // Detect table row (starts and contains multiple |)
        if (line.startsWith('|') && line.endsWith('|') && (line.match(/\|/g) || []).length >= 3) {
            // Skip separator rows (|---|---|---|)
            if (/^\|[\s\-:]+\|/.test(line) && !line.replace(/[\s\-:|]/g, '').length) {
                if (!inTable) inTable = true;
                continue;
            }
            if (!inTable) inTable = true;
            const cells = line.split('|').filter((c, idx, arr) => idx > 0 && idx < arr.length - 1).map(c => c.trim());
            tableRows.push(cells);
        } else {
            if (inTable && tableRows.length) {
                // Flush table
                let html = '<table style="width:100%;margin:12px 0;border:1px solid var(--border);border-radius:4px;border-collapse:collapse;font-size:0.8125rem;">';
                tableRows.forEach((row, ri) => {
                    const tag = ri === 0 ? 'th' : 'td';
                    const bgStyle = ri === 0 ? 'background:var(--bg-l2);' : '';
                    html += '<tr>';
                    row.forEach(cell => {
                        // Apply inline markdown to cell content
                        let cellHtml = cell
                            .replace(/\*\*(.*?)\*\*/g, '<strong style="color:var(--accent);">$1</strong>')
                            .replace(/\*(.*?)\*/g, '<em>$1</em>');
                        html += `<${tag} style="${bgStyle}padding:8px 12px;border-bottom:1px solid var(--border);text-align:left;color:${ri===0?'var(--text-secondary)':'var(--text-primary)'};">${cellHtml}</${tag}>`;
                    });
                    html += '</tr>';
                });
                html += '</table>';
                result.push(html);
                tableRows = [];
                inTable = false;
            }
            result.push(line);
        }
    }
    // Flush any trailing table
    if (tableRows.length) {
        let html = '<table style="width:100%;margin:12px 0;border:1px solid var(--border);border-radius:4px;border-collapse:collapse;font-size:0.8125rem;">';
        tableRows.forEach((row, ri) => {
            const tag = ri === 0 ? 'th' : 'td';
            const bgStyle = ri === 0 ? 'background:var(--bg-l2);' : '';
            html += '<tr>';
            row.forEach(cell => {
                let cellHtml = cell
                    .replace(/\*\*(.*?)\*\*/g, '<strong style="color:var(--accent);">$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em>$1</em>');
                html += `<${tag} style="${bgStyle}padding:8px 12px;border-bottom:1px solid var(--border);text-align:left;">${cellHtml}</${tag}>`;
            });
            html += '</tr>';
        });
        html += '</table>';
        result.push(html);
    }

    const formatted = result.join('\n')
        .replace(/### (.*)/g, '<h4 style="margin:16px 0 8px;color:var(--accent);">$1</h4>')
        .replace(/## (.*)/g, '<h3 style="margin:20px 0 8px;">$1</h3>')
        .replace(/# (.*)/g, '<h2 style="margin:24px 0 12px;">$1</h2>')
        .replace(/\*\*(.*?)\*\*/g, '<strong style="color:var(--accent);">$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code style="background:var(--bg-l2);padding:2px 6px;border-radius:2px;font-size:0.85em;">$1</code>')
        .replace(/^- (.*)/gm, '<li style="margin-left:16px;margin-bottom:4px;">$1</li>')
        .replace(/^(\d+)\. (.*)/gm, '<li style="margin-left:16px;margin-bottom:4px;">$2</li>')
        .replace(/^---$/gm, '<hr style="border:none;border-top:1px solid var(--border);margin:16px 0;">')
        .replace(/\n\n/g, '</p><p style="margin:8px 0;">')
        .replace(/\n/g, '<br>');

    return thinkingHtml + formatted;
}

// Close sidebar on navigation (mobile)
document.addEventListener('click', (e) => {
    if (e.target.closest('.nav-item') && window.innerWidth <= 768) {
        document.getElementById('sidebar').classList.remove('open');
        document.getElementById('sidebarOverlay').style.display = 'none';
    }
});

// Close modals on escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    }
});

// Close modals on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
    }
});

// URL param flash messages
(function() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('success') === 'connected') showToast('Strava connected successfully!', 'success');
    if (params.get('success') === 'disconnected') showToast('Strava disconnected', 'success');
    if (params.get('error') === 'oauth_failed') showToast('Strava connection failed', 'error');
    if (params.get('error') || params.get('success')) {
        const cleaned = window.location.pathname;
        window.history.replaceState({}, '', cleaned);
    }
})();

// Generate share image on Canvas
function generateShareImage(data) {
    const W = 1080;
    const H = 1350;
    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');

    // — Palette —
    const bg      = '#0A0A0A';
    const cardBg  = '#111111';
    const accent   = '#BFFF00';
    const white    = '#FFFFFF';
    const grey     = '#888888';
    const dimGrey  = '#555555';
    const border   = '#1E1E1E';
    const pad      = 64;    // outer padding
    const innerPad = 48;    // card inner padding

    // — Full background —
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // — Main card (rounded rect with subtle border) —
    const cardX = pad;
    const cardY = pad;
    const cardW = W - pad * 2;
    const cardH = H - pad * 2;
    const r = 24;

    ctx.fillStyle = cardBg;
    ctx.beginPath();
    ctx.roundRect(cardX, cardY, cardW, cardH, r);
    ctx.fill();
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.stroke();

    // — Accent top stripe —
    ctx.save();
    ctx.beginPath();
    ctx.roundRect(cardX, cardY, cardW, 6, [r, r, 0, 0]);
    ctx.clip();
    ctx.fillStyle = accent;
    ctx.fillRect(cardX, cardY, cardW, 6);
    ctx.restore();

    // — Content area —
    const cx = cardX + innerPad;
    const cw = cardW - innerPad * 2;
    let y = cardY + 80;

    // — Logo / Header —
    ctx.fillStyle = white;
    ctx.font = 'bold 42px Geist, system-ui, sans-serif';
    ctx.fillText('Health', cx, y);
    const healthW = ctx.measureText('Health').width;
    ctx.fillStyle = accent;
    ctx.fillText('Terminal', cx + healthW + 4, y);
    y += 28;

    ctx.fillStyle = dimGrey;
    ctx.font = '500 16px Geist, system-ui, sans-serif';
    ctx.letterSpacing = '2px';
    const titleText = (data.customTitle || 'PERFORMANCE SUMMARY').toUpperCase();
    ctx.fillText(titleText, cx, y);
    ctx.letterSpacing = '0px';

    // — Divider helper —
    function drawDivider(yPos) {
        ctx.strokeStyle = border;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx, yPos);
        ctx.lineTo(cx + cw, yPos);
        ctx.stroke();
    }

    // — Stats grid (2x2) —
    y += 32;
    drawDivider(y);
    y += 40;

    const stats = [
        { label: 'TOTAL ACTIVITIES', value: String(data.total_activities || 0) },
        { label: 'RUNNING DISTANCE', value: (data.total_distance_km || 0) + ' km' },
        { label: 'LIFTING SESSIONS', value: String(data.lifting_sessions || 0) },
        { label: 'VOLUME LIFTED', value: (data.total_volume_kg || 0).toLocaleString() + ' kg' },
    ];

    const colW = cw / 2;
    stats.forEach((s, i) => {
        const col = i % 2;
        const row = Math.floor(i / 2);
        const sx = cx + col * colW;
        const sy = y + row * 100;

        ctx.fillStyle = grey;
        ctx.font = '600 14px Geist, system-ui, sans-serif';
        ctx.letterSpacing = '1.5px';
        ctx.fillText(s.label, sx, sy);
        ctx.letterSpacing = '0px';

        ctx.fillStyle = white;
        ctx.font = 'bold 44px Geist, system-ui, sans-serif';
        ctx.fillText(s.value, sx, sy + 48);
    });

    // — This Week —
    y += 240;
    drawDivider(y);
    y += 36;
    ctx.fillStyle = accent;
    ctx.font = '600 14px Geist, system-ui, sans-serif';
    ctx.letterSpacing = '1.5px';
    ctx.fillText('THIS WEEK', cx, y);
    ctx.letterSpacing = '0px';
    y += 34;
    ctx.fillStyle = white;
    ctx.font = '500 22px Geist, system-ui, sans-serif';
    const weekLine = `${data.week?.sessions || 0} sessions  ·  ${data.week?.running_km || 0} km  ·  ${(data.week?.volume || 0).toLocaleString()} kg volume`;
    ctx.fillText(weekLine, cx, y);

    // — Top Exercises —
    if (data.top_exercises && data.top_exercises.length) {
        y += 52;
        drawDivider(y);
        y += 36;
        ctx.fillStyle = accent;
        ctx.font = '600 14px Geist, system-ui, sans-serif';
        ctx.letterSpacing = '1.5px';
        ctx.fillText('TOP EXERCISES', cx, y);
        ctx.letterSpacing = '0px';
        y += 32;

        data.top_exercises.slice(0, 5).forEach((ex, i) => {
            // Rank
            ctx.fillStyle = dimGrey;
            ctx.font = '500 18px Geist, system-ui, sans-serif';
            ctx.fillText(`${i + 1}.`, cx, y);

            // Name
            ctx.fillStyle = white;
            ctx.font = '500 18px Geist, system-ui, sans-serif';
            ctx.fillText(ex.exercise_name, cx + 36, y);

            // Stats (right-aligned)
            const statText = `${Math.round(ex.volume).toLocaleString()} kg vol · ${ex.max_weight} kg max`;
            ctx.fillStyle = grey;
            ctx.font = '400 16px Geist, system-ui, sans-serif';
            const stw = ctx.measureText(statText).width;
            ctx.fillText(statText, cx + cw - stw, y);

            y += 36;
        });
    }

    // — Personal Bests —
    if (data.personal_bests && data.personal_bests.length) {
        y += 16;
        drawDivider(y);
        y += 36;
        ctx.fillStyle = accent;
        ctx.font = '600 14px Geist, system-ui, sans-serif';
        ctx.letterSpacing = '1.5px';
        ctx.fillText('PERSONAL BESTS', cx, y);
        ctx.letterSpacing = '0px';
        y += 32;

        data.personal_bests.slice(0, 5).forEach((pb) => {
            // Name
            ctx.fillStyle = white;
            ctx.font = '500 18px Geist, system-ui, sans-serif';
            ctx.fillText(pb.exercise_name, cx, y);

            // Weight (accent)
            ctx.fillStyle = accent;
            ctx.font = 'bold 18px Geist, system-ui, sans-serif';
            const weightText = `${pb.max_weight} kg`;
            ctx.fillText(weightText, cx + cw * 0.65, y);

            // Muscle group
            ctx.fillStyle = dimGrey;
            ctx.font = '400 15px Geist, system-ui, sans-serif';
            const mgText = pb.muscle_group || '';
            const mgW = ctx.measureText(mgText).width;
            ctx.fillText(mgText, cx + cw - mgW, y);

            y += 34;
        });
    }

    // — Footer —
    const footerY = cardY + cardH - 28;
    ctx.fillStyle = dimGrey;
    ctx.font = '400 13px Geist, system-ui, sans-serif';
    ctx.fillText('Generated by HealthTerminal V1', cx, footerY);
    const footerRightText = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    const frw = ctx.measureText(footerRightText).width;
    ctx.fillText(footerRightText, cx + cw - frw, footerY);

    return canvas;
}

// Download canvas as PNG
function downloadCanvas(canvas, filename = 'healthterminal-stats.png') {
    const link = document.createElement('a');
    link.download = filename;
    link.href = canvas.toDataURL('image/png');
    link.click();
}
