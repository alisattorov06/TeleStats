let userToken = "";
let currentChatId = null;
let charts = {};

async function authenticate() {
    const token = document.getElementById('admin-token').value;
    if (!token) return alert("Please enter a token");
    
    // Test auth with a simple API call
    try {
        const response = await fetch('/api/chats', {
            headers: { 'x-token': token }
        });
        if (response.ok) {
            userToken = token;
            localStorage.setItem('telestats_token', token);
            document.getElementById('auth-modal').classList.add('hidden');
            document.getElementById('sidebar').classList.remove('hidden');
            document.getElementById('main-content').classList.remove('hidden');
            loadChats();
            initWebSocket();
        } else {
            alert("Invalid Token");
        }
    } catch (e) {
        alert("Connection Error. Is the backend running?");
    }
}

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stats?token=${userToken}`;
    const socket = new WebSocket(wsUrl);

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "stats_update" && data.chat_id === currentChatId) {
            updateSummaryFromWS(data);
        }
    };

    socket.onclose = () => {
        console.log("WebSocket connection closed. Retrying in 5 seconds...");
        setTimeout(initWebSocket, 5000);
    };
}

function updateSummaryFromWS(data) {
    const membersElem = document.getElementById('stat-members');
    const oldMembers = parseInt(membersElem.innerText.replace(/,/g, '')) || 0;
    
    membersElem.innerText = data.members.toLocaleString();
    
    // Animate change if members increased
    if (data.members > oldMembers) {
        membersElem.classList.add('text-green-500', 'scale-110');
        setTimeout(() => membersElem.classList.remove('text-green-500', 'scale-110'), 1000);
    }
}

// Auto-login from storage
window.onload = () => {
    const saved = localStorage.getItem('telestats_token');
    if (saved) {
        document.getElementById('admin-token').value = saved;
        authenticate();
    }
};

async function loadChats() {
    const response = await fetch('/api/chats', {
        headers: { 'x-token': userToken }
    });
    const chats = await response.json();
    const list = document.getElementById('chat-list');
    list.innerHTML = "";
    
    chats.forEach(chat => {
        const item = document.createElement('div');
        item.className = "px-6 py-3 cursor-pointer hover:bg-slate-800 transition-all flex items-center gap-3 text-slate-400";
        item.innerHTML = `
            <i class="fa-solid ${chat.type === 'channel' ? 'fa-bullhorn' : 'fa-users-rectangle'}"></i>
            <span class="truncate">${chat.title}</span>
        `;
        item.onclick = () => selectChat(chat);
        list.appendChild(item);
    });
}

async function selectChat(chat) {
    currentChatId = chat.id;
    document.getElementById('current-chat-title').innerText = chat.title;
    document.getElementById('cleanup-toggle').checked = chat.cleanup;
    
    // Highlight active item
    const items = document.querySelectorAll('#chat-list div');
    items.forEach(i => i.classList.remove('text-blue-500', 'bg-slate-800'));
    event.currentTarget.classList.add('text-blue-500', 'bg-slate-800');

    const response = await fetch(`/api/stats/${chat.id}`, {
        headers: { 'x-token': userToken }
    });
    const data = await response.json();
    
    updateSummary(data);
    renderCharts(data);
    updateAdders(data.top_adders);
}

function updateSummary(data) {
    if (!data.history.length) return;
    const latest = data.history[data.history.length - 1];
    const previous = data.history.length > 1 ? data.history[data.history.length - 2] : latest;
    
    document.getElementById('stat-members').innerText = latest.members.toLocaleString();
    
    const growth = latest.members - previous.members;
    const growthPercent = previous.members > 0 ? ((growth / previous.members) * 100).toFixed(1) : 0;
    
    const growthElem = document.getElementById('stat-growth');
    growthElem.innerText = (growth >= 0 ? "+" : "") + growthPercent + "%";
    growthElem.className = growth >= 0 ? "text-2xl font-bold mt-1 text-green-500" : "text-2xl font-bold mt-1 text-red-500";
    
    document.getElementById('stat-views').innerText = latest.posts > 0 ? (latest.posts * 42).toLocaleString() : "0"; // Simulated views for demo
}

function renderCharts(data) {
    const ctxHistory = document.getElementById('growthChart').getContext('2d');
    const ctxForecast = document.getElementById('forecastChart').getContext('2d');

    // Destroy existing charts if any
    if (charts.history) charts.history.destroy();
    if (charts.forecast) charts.forecast.destroy();

    const labels = data.history.map(h => h.date);
    const members = data.history.map(h => h.members);

    charts.history = new Chart(ctxHistory, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Subscribers',
                data: members,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            plugins: { legend: { display: false } },
            scales: { y: { grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } }
        }
    });

    const forecastLabels = data.forecast.map(f => f.date);
    const forecastMembers = data.forecast.map(f => f.members);

    charts.forecast = new Chart(ctxForecast, {
        type: 'bar',
        data: {
            labels: forecastLabels,
            datasets: [{
                label: 'Projected Members',
                data: forecastMembers,
                backgroundColor: '#10b981'
            }]
        },
        options: {
            plugins: { legend: { display: false } },
            scales: { y: { grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } }
        }
    });
}

function updateAdders(adders) {
    const body = document.getElementById('top-adders-body');
    body.innerHTML = "";
    adders.forEach(a => {
        const row = document.createElement('tr');
        row.className = "border-b border-slate-800 last:border-0";
        row.innerHTML = `
            <td class="py-4 text-sm">${a.user_id}</td>
            <td class="py-4 font-medium">${a.count}</td>
            <td class="py-4">
                <div class="w-24 bg-slate-700 h-2 rounded-full">
                    <div class="bg-blue-500 h-2 rounded-full" style="width: ${Math.min(a.count * 5, 100)}%"></div>
                </div>
            </td>
        `;
        body.appendChild(row);
    });
}

async function toggleCleanup() {
    if (!currentChatId) return;
    const cleanup = document.getElementById('cleanup-toggle').checked;
    await fetch(`/api/settings/${currentChatId}`, {
        method: 'POST',
        headers: { 
            'x-token': userToken,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ cleanup })
    });
}
