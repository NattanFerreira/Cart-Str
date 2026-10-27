/**
 * SmartCart STR - Frontend Real-Time Logic & Monitoramento de Cesto
 * PET2245 - Sistemas em Tempo Real | Prof. Dr. Petrucio Ricardo Tavares de Medeiros
 * Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva
 */

let ws = null;
let historicoLatencia = [];
const DEADLINE_LIMIT = 3000.0; // 3000 ms (3 segundos)

// Web Audio API para simulação de feedback sonoro no navegador
let audioCtx = null;

function emitirBeep(freq = 880, duracaoMs = 70) {
    try {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + (duracaoMs / 1000));
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + (duracaoMs / 1000));
    } catch (e) {
        // Áudio bloqueado pelo navegador até interação do usuário
    }
}

function tocarBeepAdicao() {
    emitirBeep(980, 80); // 1 Beep agudo: Adicionado ao cesto
}

function tocarBeepRemocao() {
    emitirBeep(520, 60); // 2 Beeps graves: Retirado do cesto
    setTimeout(() => emitirBeep(440, 60), 90);
}

function conectarWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("[SmartCart-STR] Conectado ao Servidor STR!");
        const statusEl = document.getElementById("systemStatus");
        statusEl.className = "status-pill connected";
        document.getElementById("statusText").innerText = "SISTEMA ATIVO";
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            processarMensagemDashboard(data);
        } catch (err) {
            console.error("[SmartCart-STR] Erro ao processar payload:", err);
        }
    };

    ws.onclose = () => {
        console.warn("[SmartCart-STR] Conexão encerrada. Reconectando em 2s...");
        const statusEl = document.getElementById("systemStatus");
        statusEl.className = "status-pill";
        statusEl.style.borderColor = "var(--danger)";
        statusEl.style.color = "var(--danger)";
        document.getElementById("statusText").innerText = "RECONECTANDO...";
        setTimeout(conectarWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error("[SmartCart-STR] Erro no socket:", err);
    };
}

let ultimoTotalItens = 0;

function processarMensagemDashboard(data) {
    // 1. Atualização do Frame de Vídeo
    const videoFeed = document.getElementById("videoFeed");
    const placeholder = document.getElementById("videoPlaceholder");

    if (data.frame_b64) {
        videoFeed.src = `data:image/jpeg;base64,${data.frame_b64}`;
        videoFeed.style.display = "block";
        placeholder.style.display = "none";
    }

    // 2. Telemetria de Tempo Real (STR)
    if (data.telemetria) {
        document.getElementById("streamFps").innerText = `${data.telemetria.fps} FPS`;

        // Latência
        const lat = data.telemetria.latencia;
        document.getElementById("latAtual").innerText = lat.atual.toFixed(1);
        document.getElementById("latMedia").innerText = `${lat.media.toFixed(2)} ms`;
        document.getElementById("latDesvio").innerText = `${lat.desvio.toFixed(2)} ms`;
        document.getElementById("latWcet").innerText = `${lat.wcet.toFixed(2)} ms`;

        // Jitter
        const jit = data.telemetria.jitter;
        document.getElementById("jitAtual").innerText = jit.atual.toFixed(1);
        document.getElementById("jitMedia").innerText = `${jit.media.toFixed(2)} ms`;
        document.getElementById("jitDesvio").innerText = `${jit.desvio.toFixed(2)} ms`;
        document.getElementById("jitMax").innerText = `${jit.max.toFixed(2)} ms`;

        // Previsibilidade e Slack Time
        document.getElementById("slackTime").innerText = data.telemetria.slack_time_ms.toFixed(1);
        document.getElementById("totalAmostras").innerText = data.telemetria.total_amostras;

        const violEl = document.getElementById("violacoesCount");
        violEl.innerText = `${data.telemetria.violacoes} (${data.telemetria.taxa_violacao_pct}%)`;
        if (data.telemetria.violacoes > 0) {
            violEl.className = "sub-val text-warning";
        } else {
            violEl.className = "sub-val text-success";
        }

        // Histórico para o gráfico
        if (data.telemetria.historico_latencia) {
            historicoLatencia = data.telemetria.historico_latencia;
            desenharGraficoLatencia();
        }
    }

    // 3. Status de Detecção no Cesto
    if (data.deteccoes) {
        const hudDet = document.getElementById("hudDetection");
        if (data.deteccoes.length > 0) {
            const resumoDets = data.deteccoes.map(d => `${d.label.toUpperCase()} (${(d.conf*100).toFixed(0)}%)`).join(', ');
            hudDet.innerText = `${data.deteccoes.length} item(ns): ${resumoDets}`;
            hudDet.style.color = "var(--success)";
        } else {
            hudDet.innerText = "Nenhum item no cesto";
            hudDet.style.color = "var(--text-muted)";
        }
    }

    // 4. Carrinho de Compras
    if (data.carrinho) {
        const novoTotal = data.carrinho.total_itens;
        if (novoTotal > ultimoTotalItens) {
            tocarBeepAdicao();
        } else if (novoTotal < ultimoTotalItens) {
            tocarBeepRemocao();
        }
        ultimoTotalItens = novoTotal;

        atualizarTabelaCarrinho(data.carrinho);
    }
}

function atualizarTabelaCarrinho(carrinho) {
    const tbody = document.getElementById("cartTableBody");
    const countBadge = document.getElementById("cartCountBadge");
    const totalVal = document.getElementById("cartTotalValue");

    countBadge.innerText = `${carrinho.total_itens} ${carrinho.total_itens === 1 ? 'item' : 'itens'}`;
    totalVal.innerText = `R$ ${carrinho.valor_total.toFixed(2).replace('.', ',')}`;

    if (!carrinho.itens || carrinho.itens.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="6">
                    <div class="empty-state">
                        <span class="empty-icon">🛒</span>
                        <p>O cesto do carrinho está vazio.</p>
                        <small>Coloque um produto dentro do carrinho para adicionar automaticamente ao inventário.</small>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    let html = "";
    carrinho.itens.forEach(item => {
        const liveTag = item.visivel_ao_vivo
            ? `<span class="tag-live">🟢 NO CESTO</span>`
            : `<span class="tag-absent">⏳ SAINDO...</span>`;

        html += `
            <tr>
                <td>
                    <div class="item-name">
                        ${item.nome}
                        ${liveTag}
                    </div>
                </td>
                <td><span class="item-badge">${item.categoria}</span></td>
                <td style="font-family: var(--font-mono);">R$ ${item.preco_unitario.toFixed(2).replace('.', ',')}</td>
                <td>
                    <div class="qty-control">
                        <button class="btn-icon" onclick="removerItem('${item.id}')" title="Diminuir quantidade">−</button>
                        <span>${item.quantidade}x</span>
                        <button class="btn-icon" onclick="adicionarItem('${item.id}')" title="Aumentar quantidade">+</button>
                    </div>
                </td>
                <td style="font-family: var(--font-mono); font-weight: 700; color: var(--primary);">
                    R$ ${item.subtotal.toFixed(2).replace('.', ',')}
                </td>
                <td>
                    <button class="btn-icon" onclick="removerItem('${item.id}')" title="Remover item do cesto">🗑️</button>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;

    // Atualiza log de eventos
    if (carrinho.eventos_recentes && carrinho.eventos_recentes.length > 0) {
        const auditList = document.getElementById("auditList");
        auditList.innerHTML = carrinho.eventos_recentes.map(ev => {
            const classeTipo = ev.tipo === "ADICAO" ? "added" : (ev.tipo === "REMOCAO" ? "removed" : "system");
            const icone = ev.tipo === "ADICAO" ? "🟢 [+]" : (ev.tipo === "REMOCAO" ? "🔴 [−]" : "ℹ️ [*]");
            return `
                <div class="audit-item ${classeTipo}">
                    [${ev.timestamp}] ${icone} ${ev.produto} (Qtd: ${ev.quantidade}) • Origem: ${ev.origem || 'Cesto'}
                </div>
            `;
        }).join('');
    }
}

function desenharGraficoLatencia() {
    const canvas = document.getElementById("latencyCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    // Linha de Deadline (3000 ms)
    const maxEscala = 3500.0;
    const yDeadline = h - (DEADLINE_LIMIT / maxEscala) * h;

    ctx.strokeStyle = "rgba(255, 61, 113, 0.85)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(0, yDeadline);
    ctx.lineTo(w, yDeadline);
    ctx.stroke();
    ctx.setLineDash([]);

    // Linha de grade 1000ms (1 segundo)
    const y1000 = h - (1000.0 / maxEscala) * h;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.beginPath();
    ctx.moveTo(0, y1000);
    ctx.lineTo(w, y1000);
    ctx.stroke();

    if (historicoLatencia.length < 2) return;

    // Plota curva de latência
    const passoX = w / (historicoLatencia.length - 1);
    ctx.beginPath();
    ctx.strokeStyle = "#00d2ff";
    ctx.lineWidth = 2;

    historicoLatencia.forEach((lat, i) => {
        const x = i * passoX;
        const y = h - (Math.min(lat, maxEscala) / maxEscala) * h;
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.stroke();

    // Área sob a curva
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.fillStyle = "rgba(0, 210, 255, 0.08)";
    ctx.fill();
}

// Funções de Controle / Simulação do Cesto
function injetarProduto(tipo) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            acao: "INJETAR_DETECCAO",
            tipo: tipo,
            confianca: 0.94
        }));
    }
}

function retirarProduto(tipo) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            acao: "REMOVER_DETECCAO",
            tipo: tipo
        }));
    }
}

function adicionarItem(id) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            acao: "ADICIONAR_ITEM",
            id: id
        }));
    }
}

function removerItem(id) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            acao: "REMOVER_ITEM",
            id: id
        }));
    }
}

function limparCarrinho() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            acao: "ESVAZIAR_CESTO"
        }));
    }
}

// Inicializa WebSocket ao carregar a página
window.addEventListener("DOMContentLoaded", () => {
    conectarWebSocket();
    desenharGraficoLatencia();
});
