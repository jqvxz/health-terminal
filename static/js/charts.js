/* HealthTerminal V1 — Chart.js Configurations
   Dark theme charts with neon lime accents */

const CHART_COLORS = {
    accent: '#BFFF00',
    white: '#FFFFFF',
    grey: '#808080',
    border: '#1A1A1A',
    bg: '#080808',
    gridLine: 'rgba(255,255,255,0.05)',
    warning: '#FFB800',
    danger: '#FF4444',
};

// Returns theme-aware color set — white mode gets readable values, dark/oled unchanged
function getThemeColors() {
    const isWhite = document.body.getAttribute('data-theme') === 'white';
    if (!isWhite) {
        return {
            gridLine:        'rgba(255,255,255,0.05)',
            tickColor:       '#808080',
            tooltipBg:       '#1A1A1A',
            tooltipTitle:    '#FFFFFF',
            tooltipBody:     '#FFFFFF',
            tooltipBorder:   '#333333',
            doughnutBorder:  '#080808',
            radarGrid:       'rgba(255,255,255,0.3)',
            radarAngles:     'rgba(255,255,255,0.3)',
            radarLabels:     '#FFFFFF',
            // "white" substitute: used wherever CHART_COLORS.white was a bar/line colour
            altLine:         '#FFFFFF',
            altFill:         'rgba(255,255,255,0.05)',
        };
    }
    return {
        gridLine:       'rgba(0,0,0,0.07)',
        tickColor:      '#555555',
        tooltipBg:      '#FFFFFF',
        tooltipTitle:   '#121212',
        tooltipBody:    '#555555',
        tooltipBorder:  '#E0E0E0',
        doughnutBorder: '#FAFAFA',
        radarGrid:      'rgba(0,0,0,0.1)',
        radarAngles:    'rgba(0,0,0,0.1)',
        radarLabels:    '#555555',
        altLine:        '#333333',
        altFill:        'rgba(0,0,0,0.04)',
    };
}

// Returns a fully theme-aware CHART_DEFAULTS object — call at render time
function getChartDefaults() {
    const tc = getThemeColors();
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: tc.tooltipBg,
                titleColor:      tc.tooltipTitle,
                bodyColor:       tc.tooltipBody,
                borderColor:     tc.tooltipBorder,
                borderWidth: 1,
                padding: 10,
                titleFont: { family: "'Geist', sans-serif", size: 12 },
                bodyFont:  { family: "'Geist', sans-serif", size: 12 },
                cornerRadius: 4,
            },
        },
        scales: {
            x: {
                grid:   { color: tc.gridLine, drawBorder: false },
                ticks:  { color: tc.tickColor, font: { family: "'Geist', sans-serif", size: 11 } },
                border: { display: false },
            },
            y: {
                grid:   { color: tc.gridLine, drawBorder: false },
                ticks:  { color: tc.tickColor, font: { family: "'Geist', sans-serif", size: 11 } },
                border: { display: false },
            },
        },
    };
}

// Keep static CHART_DEFAULTS for any external references (not used internally below)
const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: '#1A1A1A',
            titleColor: '#FFFFFF',
            bodyColor: '#FFFFFF',
            borderColor: '#333333',
            borderWidth: 1,
            padding: 10,
            titleFont: { family: "'Geist', sans-serif", size: 12 },
            bodyFont: { family: "'Geist', sans-serif", size: 12 },
            cornerRadius: 4,
        },
    },
    scales: {
        x: {
            grid: { color: CHART_COLORS.gridLine, drawBorder: false },
            ticks: { color: CHART_COLORS.grey, font: { family: "'Geist', sans-serif", size: 11 } },
            border: { display: false },
        },
        y: {
            grid: { color: CHART_COLORS.gridLine, drawBorder: false },
            ticks: { color: CHART_COLORS.grey, font: { family: "'Geist', sans-serif", size: 11 } },
            border: { display: false },
        },
    },
};

// Immediately adjust static CHART_DEFAULTS if the current theme is white mode
(function() {
    const isWhite = document.body && document.body.getAttribute('data-theme') === 'white';
    if (isWhite) {
        const tc = getThemeColors();
        CHART_DEFAULTS.plugins.tooltip.backgroundColor = tc.tooltipBg;
        CHART_DEFAULTS.plugins.tooltip.titleColor = tc.tooltipTitle;
        CHART_DEFAULTS.plugins.tooltip.bodyColor = tc.tooltipBody;
        CHART_DEFAULTS.plugins.tooltip.borderColor = tc.tooltipBorder;
        CHART_DEFAULTS.scales.x.grid.color = tc.gridLine;
        CHART_DEFAULTS.scales.x.ticks.color = tc.tickColor;
        CHART_DEFAULTS.scales.y.grid.color = tc.gridLine;
        CHART_DEFAULTS.scales.y.ticks.color = tc.tickColor;
    }
})();


// Store chart instances for cleanup
const chartInstances = {};

function destroyChart(id) {
    if (chartInstances[id]) { chartInstances[id].destroy(); delete chartInstances[id]; }
}

/* ========== DASHBOARD CHARTS ========== */

function renderWeeklyChart(activities) {
    destroyChart('weeklyChart');
    const defaults = getChartDefaults();
    const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const now = new Date();
    const weekStart = new Date(now);
    const dayOfWeek = now.getDay();
    const diff = now.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1);
    weekStart.setDate(diff);
    weekStart.setHours(0,0,0,0);

    const counts = new Array(7).fill(0);
    activities.forEach(a => {
        const d = new Date(a.start_date_local);
        if (d >= weekStart) {
            const day = (d.getDay() + 6) % 7;
            counts[day]++;
        }
    });

    const ctx = document.getElementById('weeklyChart');
    if (!ctx) return;
    chartInstances['weeklyChart'] = new Chart(ctx, {
        type: 'bar',
        data: { labels: days, datasets: [{ data: counts, backgroundColor: CHART_COLORS.accent, borderRadius: 2, barPercentage: 0.6 }] },
        options: { ...defaults, scales: { ...defaults.scales, y: { ...defaults.scales.y, beginAtZero: true, ticks: { ...defaults.scales.y.ticks, stepSize: 1 } } } },
    });
}

function renderTypeChart(activities) {
    destroyChart('typeChart');
    const tc = getThemeColors();
    const defaults = getChartDefaults();
    const types = {};
    activities.forEach(a => {
        const t = a.is_hevy ? 'Lifting' : (a.activity_type || 'Other');
        types[t] = (types[t] || 0) + 1;
    });
    const labels = Object.keys(types);
    const data = Object.values(types);
    const colors = labels.map((_, i) => i === 0 ? CHART_COLORS.accent : i === 1 ? tc.altLine : CHART_COLORS.warning);

    const legendEl = document.getElementById('typeChartLegend');
    if (legendEl) {
        legendEl.innerHTML = labels.map((label, i) => {
            const count = data[i];
            const color = colors[i];
            return `<div class="legend-item">
                <span class="legend-dot" style="background-color: ${color}"></span>
                <span class="legend-text">${label} <span style="color: var(--text-muted); margin-left: 2px;">(${count})</span></span>
            </div>`;
        }).join('');
    }

    const ctx = document.getElementById('typeChart');
    if (!ctx) return;
    chartInstances['typeChart'] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors,
                borderColor: tc.doughnutBorder,
                borderWidth: 3,
                borderRadius: 4,
                spacing: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: defaults.plugins.tooltip
            }
        },
    });
}

/* ========== RUNNING CHARTS ========== */

function renderPaceTrend(runs) {
    destroyChart('paceTrendChart');
    const defaults = getChartDefaults();
    const sorted = [...runs].filter(r => r.distance > 0 && r.moving_time > 0).sort((a,b) => a.start_date_local.localeCompare(b.start_date_local));
    const labels = sorted.map(r => r.start_date_local.substring(5,10));
    const data = sorted.map(r => (r.moving_time / 60) / (r.distance / 1000));

    const ctx = document.getElementById('paceTrendChart');
    if (!ctx) return;
    chartInstances['paceTrendChart'] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{ data, borderColor: CHART_COLORS.accent, backgroundColor: 'rgba(191,255,0,0.1)', fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: CHART_COLORS.accent, borderWidth: 2 }] },
        options: { ...defaults, scales: { ...defaults.scales, y: { ...defaults.scales.y, reverse: true, title: { display: true, text: 'min/km', color: defaults.scales.y.ticks.color, font: { size: 11 } } } } },
    });
}

function renderWeeklyMileage(runs) {
    destroyChart('weeklyMileageChart');
    if (!runs || !runs.length) return;
    const tc = getThemeColors();
    const defaults = getChartDefaults();

    const weeks = {};
    const runsPerWeek = {};
    runs.forEach(r => {
        if (!r.distance) return;
        const d = new Date(r.start_date_local);
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1);
        const mon = new Date(d.setDate(diff));
        const weekStr = mon.toISOString().substring(0, 10);
        weeks[weekStr] = (weeks[weekStr] || 0) + (r.distance / 1000);
        runsPerWeek[weekStr] = (runsPerWeek[weekStr] || 0) + 1;
    });

    const sortedWeeks = Object.keys(weeks).sort();
    const labels = sortedWeeks;
    const data = sortedWeeks.map(w => weeks[w]);

    const ctx = document.getElementById('weeklyMileageChart');
    if (!ctx) return;

    chartInstances['weeklyMileageChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: tc.altLine,
                borderRadius: 4,
                barPercentage: 0.6,
                hoverBackgroundColor: CHART_COLORS.accent
            }]
        },
        options: {
            ...defaults,
            scales: {
                ...defaults.scales,
                y: {
                    ...defaults.scales.y,
                    beginAtZero: true,
                    title: { display: true, text: 'km', color: defaults.scales.y.ticks.color, font: { size: 10, family: "'Geist', sans-serif" } }
                }
            },
            plugins: {
                ...defaults.plugins,
                tooltip: {
                    ...defaults.plugins.tooltip,
                    callbacks: {
                        label: function(context) {
                            const val = context.raw.toFixed(2);
                            const count = runsPerWeek[context.label];
                            return ` ${val} km (${count} run${count > 1 ? 's' : ''})`;
                        }
                    }
                }
            }
        },
    });
}

function renderHRZones(runs) {
    destroyChart('hrZoneChart');
    const tc = getThemeColors();
    const defaults = getChartDefaults();
    const zones = { 'Z1 Recovery': 0, 'Z2 Aerobic': 0, 'Z3 Tempo': 0, 'Z4 Threshold': 0, 'Z5 Anaerobic': 0 };
    let hasHR = false;
    runs.forEach(r => {
        const hr = r.average_heartrate;
        if (!hr) return;
        hasHR = true;
        if (hr < 120) zones['Z1 Recovery']++;
        else if (hr < 140) zones['Z2 Aerobic']++;
        else if (hr < 160) zones['Z3 Tempo']++;
        else if (hr < 180) zones['Z4 Threshold']++;
        else zones['Z5 Anaerobic']++;
    });

    const wrap = document.getElementById('hrZoneWrap');
    const legendEl = document.getElementById('hrZoneChartLegendDetail');
    const empty = document.getElementById('hrZoneEmpty');

    if (!hasHR) {
        if (wrap) wrap.classList.add('hidden');
        if (legendEl) legendEl.classList.add('hidden');
        if (empty) empty.classList.remove('hidden');
        return;
    } else {
        if (wrap) wrap.classList.remove('hidden');
        if (legendEl) legendEl.classList.remove('hidden');
        if (empty) empty.classList.add('hidden');
    }

    const ctx = document.getElementById('hrZoneChart');
    if (!ctx) return;

    const labels = Object.keys(zones);
    const data = Object.values(zones);
    const total = data.reduce((s, v) => s + v, 0);
    const colors = ['#475569', '#00D2FF', '#BFFF00', '#FF9F00', '#FF4444'];

    const detailEl = document.getElementById('hrZoneChartLegendDetail');
    if (detailEl) {
        detailEl.innerHTML = labels.map((label, i) => {
            const count = data[i];
            const pct = total > 0 ? Math.round((count / total) * 100) : 0;
            const color = colors[i];
            return `
                <div style="display:flex; flex-direction:column; gap:4px; width:100%;">
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-secondary);">
                        <span style="display:flex; align-items:center; gap:6px;">
                            <span style="width:8px; height:8px; border-radius:50%; background-color:${color};"></span>
                            ${label}
                        </span>
                        <span class="data-mono">${count} runs (${pct}%)</span>
                    </div>
                    <div class="progress-bar" style="height:6px; background:var(--bg-l2);">
                        <div class="progress-fill" style="width:${pct}%; background-color:${color};"></div>
                    </div>
                </div>
            `;
        }).join('');
    }

    chartInstances['hrZoneChart'] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors,
                borderColor: tc.doughnutBorder,
                borderWidth: 3,
                borderRadius: 4,
                spacing: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...defaults.plugins.tooltip,
                    callbacks: {
                        label: function(context) {
                            const val = context.raw || 0;
                            const pct = total > 0 ? Math.round((val / total) * 100) : 0;
                            return ` ${context.label}: ${val} runs (${pct}%)`;
                        }
                    }
                }
            }
        },
    });
}

function renderElevation(runs) {
    destroyChart('elevationChart');
    const tc = getThemeColors();
    const defaults = getChartDefaults();
    const sorted = [...runs].filter(r => r.total_elevation_gain > 0).sort((a,b) => a.start_date_local.localeCompare(b.start_date_local));
    const labels = sorted.map(r => r.start_date_local.substring(5,10));
    const data = sorted.map(r => r.total_elevation_gain);

    const ctx = document.getElementById('elevationChart');
    if (!ctx) return;
    chartInstances['elevationChart'] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{ data, borderColor: tc.altLine, backgroundColor: tc.altFill, fill: true, tension: 0.3, pointRadius: 2, borderWidth: 2 }] },
        options: { ...defaults, scales: { ...defaults.scales, y: { ...defaults.scales.y, beginAtZero: true, title: { display: true, text: 'meters', color: defaults.scales.y.ticks.color, font: { size: 11 } } } } },
    });
}



/* ========== LIFTING CHARTS ========== */

function renderVolumeOverTime(details) {
    destroyChart('volumeChart');
    const defaults = getChartDefaults();
    const sessData = details.filter(d => d.lifting_details && d.lifting_details.length).map(d => {
        const vol = d.lifting_details.filter(l => !l.is_warmup).reduce((s,l) => s + (l.weight||0) * (l.reps||0), 0);
        return { date: (d.start_date_local||'').substring(5,10), volume: vol };
    }).sort((a,b) => a.date.localeCompare(b.date));

    const ctx = document.getElementById('volumeChart');
    if (!ctx) return;
    chartInstances['volumeChart'] = new Chart(ctx, {
        type: 'bar',
        data: { labels: sessData.map(s=>s.date), datasets: [{ data: sessData.map(s=>s.volume), backgroundColor: CHART_COLORS.accent, borderRadius: 2, barPercentage: 0.6 }] },
        options: { ...defaults, scales: { ...defaults.scales, y: { ...defaults.scales.y, beginAtZero: true, title: { display: true, text: 'kg', color: defaults.scales.y.ticks.color, font: { size: 11 } } } } },
    });
}

function renderMuscleRadar(muscles) {
    destroyChart('muscleChart');
    if (!muscles.length) return;
    const tc = getThemeColors();
    const defaults = getChartDefaults();

    const ctx = document.getElementById('muscleChart');
    if (!ctx) return;

    const maxVal = Math.max(...muscles.map(m => m.total_volume), 1);

    chartInstances['muscleChart'] = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: muscles.map(m => m.muscle_group),
            datasets: [{
                data: muscles.map(m => m.total_volume),
                borderColor: CHART_COLORS.accent,
                backgroundColor: 'rgba(191,255,0,0.15)',
                pointBackgroundColor: CHART_COLORS.accent,
                pointRadius: 0, borderWidth: 2,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                r: {
                    grid:        { color: tc.radarGrid },
                    angleLines:  { color: tc.radarAngles },
                    pointLabels: {
                        color: tc.radarLabels,
                        font: { family: "'Geist',sans-serif", size: 12, weight: '500' },
                        padding: 10
                    },
                    ticks: { display: false },
                    beginAtZero: true,
                    max: maxVal * 1.1
                }
            },
            plugins: { legend: { display: false }, tooltip: defaults.plugins.tooltip },
        },
    });
}

function renderMuscleHeatmap(muscles) {
    const container = document.getElementById('muscleHeatmap');
    if (!container) return;

    if (!muscles || !muscles.length) {
        container.innerHTML = '<div class="empty-state" style="grid-column: 1 / -1; padding: 24px 0;"><p>No muscle data available</p></div>';
        return;
    }

    const maxVal = Math.max(...muscles.map(m => m.total_volume), 1);

    const sortedMuscles = [...muscles].sort((a, b) => b.total_volume - a.total_volume);

    container.innerHTML = sortedMuscles.map(m => {
        const pct = m.total_volume / maxVal;
        let heat = 0;
        if (pct > 0.8) heat = 4;
        else if (pct > 0.6) heat = 3;
        else if (pct > 0.3) heat = 2;
        else if (pct > 0) heat = 1;

        return `<div class="muscle-cell heat-${heat}">
            <div style="margin-bottom: 4px;">${m.muscle_group || 'Unknown'}</div>
            <div class="data-mono" style="font-size: 0.6875rem; opacity: 0.8; letter-spacing: -0.02em; text-transform: none;">${Math.round(m.total_volume).toLocaleString()}kg</div>
        </div>`;
    }).join('');
}

/* ========== PROGRESS CHARTS ========== */

function renderWeeklyTrends(weeks) {
    destroyChart('weeklyTrendChart');
    destroyChart('volumeTrendChart');
    const tc = getThemeColors();
    const defaults = getChartDefaults();

    const labels = weeks.map(w => w.week_start ? w.week_start.substring(5) : '');
    const distData = weeks.map(w => (w.running?.total_distance || 0) / 1000);
    const volData = weeks.map(w => w.total_volume || 0);

    const ctx1 = document.getElementById('weeklyTrendChart');
    if (ctx1) {
        chartInstances['weeklyTrendChart'] = new Chart(ctx1, {
            type: 'line',
            data: { labels, datasets: [{ data: distData, borderColor: CHART_COLORS.accent, backgroundColor: 'rgba(191,255,0,0.1)', fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: CHART_COLORS.accent, borderWidth: 2 }] },
            options: { ...defaults, scales: { ...defaults.scales, y: { ...defaults.scales.y, beginAtZero: true, title: { display: true, text: 'km', color: defaults.scales.y.ticks.color } } } },
        });
    }

    const ctx2 = document.getElementById('volumeTrendChart');
    if (ctx2) {
        chartInstances['volumeTrendChart'] = new Chart(ctx2, {
            type: 'line',
            data: { labels, datasets: [{ data: volData, borderColor: tc.altLine, backgroundColor: tc.altFill, fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: tc.altLine, borderWidth: 2 }] },
            options: { ...defaults, scales: { ...defaults.scales, y: { ...defaults.scales.y, beginAtZero: true, title: { display: true, text: 'kg', color: defaults.scales.y.ticks.color } } } },
        });
    }
}
