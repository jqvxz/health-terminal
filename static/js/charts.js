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

// Store chart instances for cleanup
const chartInstances = {};

function destroyChart(id) {
    if (chartInstances[id]) { chartInstances[id].destroy(); delete chartInstances[id]; }
}

/* ========== DASHBOARD CHARTS ========== */

function renderWeeklyChart(activities) {
    destroyChart('weeklyChart');
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
        options: { ...CHART_DEFAULTS, scales: { ...CHART_DEFAULTS.scales, y: { ...CHART_DEFAULTS.scales.y, beginAtZero: true, ticks: { ...CHART_DEFAULTS.scales.y.ticks, stepSize: 1 } } } },
    });
}

function renderTypeChart(activities) {
    destroyChart('typeChart');
    const types = {};
    activities.forEach(a => {
        const t = a.is_hevy ? 'Lifting' : (a.activity_type || 'Other');
        types[t] = (types[t] || 0) + 1;
    });
    const labels = Object.keys(types);
    const data = Object.values(types);
    const colors = labels.map((_, i) => i === 0 ? CHART_COLORS.accent : i === 1 ? CHART_COLORS.white : CHART_COLORS.warning);

    const ctx = document.getElementById('typeChart');
    if (!ctx) return;
    chartInstances['typeChart'] = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: CHART_COLORS.bg, borderWidth: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '70%', plugins: { legend: { display: true, position: 'bottom', labels: { color: CHART_COLORS.grey, font: { family: "'Geist',sans-serif", size: 11 }, padding: 16, usePointStyle: true, pointStyle: 'circle' } }, tooltip: CHART_DEFAULTS.plugins.tooltip } },
    });
}

/* ========== RUNNING CHARTS ========== */

function renderPaceTrend(runs) {
    destroyChart('paceTrendChart');
    const sorted = [...runs].filter(r => r.distance > 0 && r.moving_time > 0).sort((a,b) => a.start_date_local.localeCompare(b.start_date_local));
    const labels = sorted.map(r => r.start_date_local.substring(5,10));
    const data = sorted.map(r => (r.moving_time / 60) / (r.distance / 1000));

    const ctx = document.getElementById('paceTrendChart');
    if (!ctx) return;
    chartInstances['paceTrendChart'] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{ data, borderColor: CHART_COLORS.accent, backgroundColor: 'rgba(191,255,0,0.1)', fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: CHART_COLORS.accent, borderWidth: 2 }] },
        options: { ...CHART_DEFAULTS, scales: { ...CHART_DEFAULTS.scales, y: { ...CHART_DEFAULTS.scales.y, reverse: true, title: { display: true, text: 'min/km', color: CHART_COLORS.grey, font: { size: 11 } } } } },
    });
}

function renderDistanceOverTime(runs) {
    destroyChart('distanceChart');
    const sorted = [...runs].sort((a,b) => a.start_date_local.localeCompare(b.start_date_local));
    const labels = sorted.map(r => r.start_date_local.substring(5,10));
    const data = sorted.map(r => (r.distance || 0) / 1000);

    const ctx = document.getElementById('distanceChart');
    if (!ctx) return;
    chartInstances['distanceChart'] = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data, backgroundColor: CHART_COLORS.white, borderRadius: 2, barPercentage: 0.5 }] },
        options: { ...CHART_DEFAULTS, scales: { ...CHART_DEFAULTS.scales, y: { ...CHART_DEFAULTS.scales.y, beginAtZero: true, title: { display: true, text: 'km', color: CHART_COLORS.grey, font: { size: 11 } } } } },
    });
}

function renderHRZones(runs) {
    destroyChart('hrZoneChart');
    const zones = { 'Zone 1 (<120)': 0, 'Zone 2 (120-140)': 0, 'Zone 3 (140-160)': 0, 'Zone 4 (160-180)': 0, 'Zone 5 (180+)': 0 };
    runs.forEach(r => {
        const hr = r.average_heartrate;
        if (!hr) return;
        if (hr < 120) zones['Zone 1 (<120)']++;
        else if (hr < 140) zones['Zone 2 (120-140)']++;
        else if (hr < 160) zones['Zone 3 (140-160)']++;
        else if (hr < 180) zones['Zone 4 (160-180)']++;
        else zones['Zone 5 (180+)']++;
    });

    const ctx = document.getElementById('hrZoneChart');
    if (!ctx) return;
    chartInstances['hrZoneChart'] = new Chart(ctx, {
        type: 'bar',
        data: { labels: Object.keys(zones), datasets: [{ data: Object.values(zones), backgroundColor: ['#333', '#555', CHART_COLORS.accent, CHART_COLORS.warning, CHART_COLORS.danger], borderRadius: 2 }] },
        options: { ...CHART_DEFAULTS, indexAxis: 'y', scales: { x: { ...CHART_DEFAULTS.scales.x, beginAtZero: true }, y: CHART_DEFAULTS.scales.y } },
    });
}

function renderElevation(runs) {
    destroyChart('elevationChart');
    const sorted = [...runs].filter(r => r.total_elevation_gain > 0).sort((a,b) => a.start_date_local.localeCompare(b.start_date_local));
    const labels = sorted.map(r => r.start_date_local.substring(5,10));
    const data = sorted.map(r => r.total_elevation_gain);

    const ctx = document.getElementById('elevationChart');
    if (!ctx) return;
    chartInstances['elevationChart'] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{ data, borderColor: CHART_COLORS.white, backgroundColor: 'rgba(255,255,255,0.05)', fill: true, tension: 0.3, pointRadius: 2, borderWidth: 2 }] },
        options: { ...CHART_DEFAULTS, scales: { ...CHART_DEFAULTS.scales, y: { ...CHART_DEFAULTS.scales.y, beginAtZero: true, title: { display: true, text: 'meters', color: CHART_COLORS.grey, font: { size: 11 } } } } },
    });
}

/* ========== LIFTING CHARTS ========== */

function renderVolumeOverTime(details) {
    destroyChart('volumeChart');
    const sessData = details.filter(d => d.lifting_details && d.lifting_details.length).map(d => {
        const vol = d.lifting_details.filter(l => !l.is_warmup).reduce((s,l) => s + (l.weight||0) * (l.reps||0), 0);
        return { date: (d.start_date_local||'').substring(5,10), volume: vol };
    }).sort((a,b) => a.date.localeCompare(b.date));

    const ctx = document.getElementById('volumeChart');
    if (!ctx) return;
    chartInstances['volumeChart'] = new Chart(ctx, {
        type: 'bar',
        data: { labels: sessData.map(s=>s.date), datasets: [{ data: sessData.map(s=>s.volume), backgroundColor: CHART_COLORS.accent, borderRadius: 2, barPercentage: 0.6 }] },
        options: { ...CHART_DEFAULTS, scales: { ...CHART_DEFAULTS.scales, y: { ...CHART_DEFAULTS.scales.y, beginAtZero: true, title: { display: true, text: 'kg', color: CHART_COLORS.grey, font: { size: 11 } } } } },
    });
}

function renderMuscleRadar(muscles) {
    destroyChart('muscleChart');
    if (!muscles.length) return;

    const ctx = document.getElementById('muscleChart');
    if (!ctx) return;
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
            scales: { r: { grid: { color: CHART_COLORS.gridLine }, angleLines: { color: CHART_COLORS.gridLine }, pointLabels: { color: CHART_COLORS.grey, font: { family: "'Geist',sans-serif", size: 11 } }, ticks: { display: false }, beginAtZero: true } },
            plugins: { legend: { display: false }, tooltip: CHART_DEFAULTS.plugins.tooltip },
        },
    });
}

/* ========== PROGRESS CHARTS ========== */

function renderWeeklyTrends(weeks) {
    destroyChart('weeklyTrendChart');
    destroyChart('volumeTrendChart');

    const labels = weeks.map(w => w.week_start ? w.week_start.substring(5) : '');
    const distData = weeks.map(w => (w.running?.total_distance || 0) / 1000);
    const volData = weeks.map(w => w.total_volume || 0);

    const ctx1 = document.getElementById('weeklyTrendChart');
    if (ctx1) {
        chartInstances['weeklyTrendChart'] = new Chart(ctx1, {
            type: 'line',
            data: { labels, datasets: [{ data: distData, borderColor: CHART_COLORS.accent, backgroundColor: 'rgba(191,255,0,0.1)', fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: CHART_COLORS.accent, borderWidth: 2 }] },
            options: { ...CHART_DEFAULTS, scales: { ...CHART_DEFAULTS.scales, y: { ...CHART_DEFAULTS.scales.y, beginAtZero: true, title: { display: true, text: 'km', color: CHART_COLORS.grey } } } },
        });
    }

    const ctx2 = document.getElementById('volumeTrendChart');
    if (ctx2) {
        chartInstances['volumeTrendChart'] = new Chart(ctx2, {
            type: 'line',
            data: { labels, datasets: [{ data: volData, borderColor: CHART_COLORS.white, backgroundColor: 'rgba(255,255,255,0.05)', fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: CHART_COLORS.white, borderWidth: 2 }] },
            options: { ...CHART_DEFAULTS, scales: { ...CHART_DEFAULTS.scales, y: { ...CHART_DEFAULTS.scales.y, beginAtZero: true, title: { display: true, text: 'kg', color: CHART_COLORS.grey } } } },
        });
    }
}
