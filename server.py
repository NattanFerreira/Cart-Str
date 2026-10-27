"""
Servidor Central de Tempo Real (STR) - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Monitoramento Automático de Cesto: Gerencia adição e remoção contínua em tempo real
conforme os produtos entram e saem do campo de visão da câmera acoplada ao carrinho.
"""

import os
import sys
import time
import json
import base64
import asyncio
import cv2
import numpy as np
import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from config import (
    SERVER_HOST, SERVER_PORT, DEADLINE_MS,
    STATIC_DIR, CATALOGO_PRODUTOS
)
from cart_manager import GerenciadorCarrinhoAoVivo
from telemetry_str import TelemetriaSTR
from vision_pipeline import PipelineVisao

# Instâncias Centrais do Sistema STR
carrinho_mgr = GerenciadorCarrinhoAoVivo()
telemetria = TelemetriaSTR(deadline_ms=DEADLINE_MS)
pipeline_visao = PipelineVisao()

# Clientes conectados ao Dashboard
dashboard_clients = set()
ultimo_frame_b64 = None
deteccoes_recentes = []

# Cache MIME para arquivos estáticos do frontend
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon"
}

def obter_mime_type(caminho: str) -> str:
    _, ext = os.path.splitext(caminho)
    return MIME_TYPES.get(ext.lower(), "application/octet-stream")

async def processar_requisicao_http(conn, request):
    """
    Roteador HTTP para servir o Dashboard e APIs REST leves.
    Se for rota de WebSocket (/ws/*), retorna None para prosseguir com o handshake.
    """
    path = request.path.split('?')[0].rstrip('/')
    if not path:
        path = "/"

    # Rotas de WebSocket passam direto
    if path in ("/ws/camera", "/ws/dashboard"):
        conn.ws_path = path
        return None

    # Raiz -> index.html
    if path == "/" or path == "/index.html":
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "rb") as f:
                body = f.read()
            return Response(200, "OK", Headers([
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body)))
            ]), body)
        return Response(404, "Not Found", Headers(), b"index.html nao encontrado")

    # Arquivos Estáticos (/static/...)
    if path.startswith("/static/"):
        rel_path = path[len("/static/"):]
        file_path = os.path.join(STATIC_DIR, rel_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime = obter_mime_type(file_path)
            with open(file_path, "rb") as f:
                body = f.read()
            return Response(200, "OK", Headers([
                ("Content-Type", mime),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "public, max-age=3600")
            ]), body)
        return Response(404, "Not Found", Headers(), b"Arquivo nao encontrado")

    # Endpoint REST: Status do Carrinho
    if path == "/api/cart":
        data = json.dumps(carrinho_mgr.obter_resumo()).encode('utf-8')
        return Response(200, "OK", Headers([
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(data)))
        ]), data)

    # Endpoint REST: Métricas de Telemetria STR
    if path == "/api/telemetry":
        data = json.dumps(telemetria.obter_metricas_atuais()).encode('utf-8')
        return Response(200, "OK", Headers([
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(data)))
        ]), data)

    return Response(404, "Not Found", Headers(), b"Rota nao encontrada")

async def broadcast_dashboard(payload: dict):
    """Envia atualização em tempo real para todos os clientes do Dashboard conectados."""
    if not dashboard_clients:
        return
    msg = json.dumps(payload)
    desconectados = set()
    for client in dashboard_clients:
        try:
            await client.send(msg)
        except Exception:
            desconectados.add(client)
    for client in desconectados:
        dashboard_clients.discard(client)

async def lidar_com_camera(ws):
    """
    Manipula o fluxo contínuo de quadros do ESP32-CAM ou do cliente PC.
    Aplica medição monotônica de alta precisão (ns) para garantia do deadline STR (<150ms).
    """
    global ultimo_frame_b64, deteccoes_recentes
    print("[SERVER-STR] Câmera acoplada ao cesto conectada com sucesso!")

    try:
        async for mensagem in ws:
            # Medição Monotônica de Alta Precisão ponta a ponta
            t_inicio_ns = time.perf_counter_ns()

            # Mensagens de texto (handshake / status do cliente)
            if isinstance(mensagem, str):
                try:
                    cmd_cam = json.loads(mensagem)
                    if cmd_cam.get("tipo") == "DISPOSITIVO_BORDA":
                        print(f"[BORDA] Identificação recebida: {cmd_cam.get('id')}")
                except Exception:
                    pass
                continue

            # Quadros binários JPEG
            np_arr = np.frombuffer(mensagem, dtype=np.uint8)
            frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame_bgr is None:
                continue

            # 1. Inferência de Visão Computacional no cesto
            deteccoes, frame_anotado = pipeline_visao.detectar_produtos(frame_bgr)
            deteccoes_recentes = deteccoes

            # 2. Atualização automática do inventário ao vivo
            eventos_cesto = carrinho_mgr.atualizar_inventario_ao_vivo(deteccoes)

            # 3. Notificação sonora e de status para a borda (ESP32-CAM)
            for ev in eventos_cesto:
                if ev["tipo"] == "REGISTRADO":
                    # 1 BEEP no ESP32: item colocado no cesto
                    await ws.send(json.dumps({
                        "evento": "PRODUTO_REGISTRADO",
                        "produto": ev["produto"]["nome"],
                        "quantidade": ev["quantidade"]
                    }))
                elif ev["tipo"] == "REMOVIDO":
                    # 2 BEEPS no ESP32: item retirado do cesto
                    await ws.send(json.dumps({
                        "evento": "PRODUTO_REMOVIDO",
                        "produto": ev["produto"]["nome"],
                        "quantidade": ev["quantidade"]
                    }))

            # 4. Codificação e Telemetria STR
            _, buffer_jpeg = cv2.imencode('.jpg', frame_anotado, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            ultimo_frame_b64 = base64.b64encode(buffer_jpeg).decode('utf-8')

            t_fim_ns = time.perf_counter_ns()
            metricas_str = telemetria.registrar_amostra(t_inicio_ns, t_fim_ns)

            # 5. Broadcast para o Dashboard Web
            await broadcast_dashboard({
                "frame_b64": ultimo_frame_b64,
                "telemetria": metricas_str,
                "carrinho": carrinho_mgr.obter_resumo(),
                "deteccoes": deteccoes
            })

    except websockets.exceptions.ConnectionClosed:
        print("[SERVER-STR] Conexão com a câmera do cesto encerrada.")
    except Exception as e:
        print(f"[SERVER-STR] Erro no processamento da câmera: {e}")

async def lidar_com_dashboard(ws):
    """
    Gerencia conexão do Dashboard Web com suporte a ações interativas em tempo real.
    """
    dashboard_clients.add(ws)
    print(f"[DASHBOARD] Cliente conectado. Total ativos: {len(dashboard_clients)}")

    try:
        # Envia estado inicial imediato
        await ws.send(json.dumps({
            "carrinho": carrinho_mgr.obter_resumo(),
            "telemetria": telemetria.obter_metricas_atuais(),
            "frame_b64": ultimo_frame_b64,
            "deteccoes": deteccoes_recentes
        }))

        async for mensagem in ws:
            dados = json.loads(mensagem)
            acao = dados.get("acao")

            if acao == "INJETAR_DETECCAO":
                # Simula presença física de um produto colocado no cesto
                tipo = dados.get("tipo", "bottle")
                conf = dados.get("confianca", 0.95)
                det_sintetica = [{
                    "label": tipo,
                    "tag": tipo.upper(),
                    "conf": conf,
                    "box": (50, 50, 180, 200)
                }]
                eventos = carrinho_mgr.atualizar_inventario_ao_vivo(det_sintetica)
                # Força confirmação direta na injeção sintética
                prod_meta = carrinho_mgr.resolver_produto(tipo)
                if prod_meta:
                    carrinho_mgr._aplicar_adicao(prod_meta)
                    carrinho_mgr._registrar_log_evento("ADICAO", prod_meta["nome"], carrinho_mgr.itens[prod_meta["id"]]["quantidade"], "Injeção Simulador")

            elif acao == "REMOVER_DETECCAO":
                # Simula retirada de um produto do cesto
                tipo = dados.get("tipo", "bottle")
                prod_meta = carrinho_mgr.resolver_produto(tipo)
                if prod_meta and prod_meta["id"] in carrinho_mgr.itens:
                    carrinho_mgr._aplicar_remocao(prod_meta["id"])
                    qtd_restante = carrinho_mgr.itens[prod_meta["id"]]["quantidade"] if prod_meta["id"] in carrinho_mgr.itens else 0
                    carrinho_mgr._registrar_log_evento("REMOCAO", prod_meta["nome"], qtd_restante, "Injeção Simulador")

            elif acao == "LIMPAR_CARRINHO" or acao == "ESVAZIAR_CESTO":
                carrinho_mgr.limpar_carrinho()

            elif acao == "ADICIONAR_ITEM":
                prod_id = dados.get("id")
                carrinho_mgr.adicionar_item_manual(prod_id)

            elif acao == "REMOVER_ITEM":
                prod_id = dados.get("id")
                carrinho_mgr.remover_item_manual(prod_id)

            # Broadcast das alterações imediatas
            await broadcast_dashboard({
                "carrinho": carrinho_mgr.obter_resumo(),
                "telemetria": telemetria.obter_metricas_atuais(),
                "frame_b64": ultimo_frame_b64,
                "deteccoes": deteccoes_recentes
            })

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        dashboard_clients.discard(ws)
        print(f"[DASHBOARD] Cliente desconectado. Total ativos: {len(dashboard_clients)}")

async def despachante_websocket(ws):
    """Roteador para conexões WebSocket com suporte a rotas e subprotocolos."""
    raw_path = getattr(ws, "ws_path", ws.request.path if hasattr(ws, "request") else ws.path)
    path = raw_path.split('?')[0].rstrip('/')
    if not path:
        path = "/"

    if path == "/ws/camera":
        await lidar_com_camera(ws)
    elif path == "/ws/dashboard":
        await lidar_com_dashboard(ws)
    else:
        print(f"[WS] Rota desconhecida rejeitada: {path}")
        await ws.close()

def selecionar_subprotocolo(*args, **kwargs):
    """
    Garante compatibilidade de handshake para clientes ESP32-CAM (Arduino WebSockets)
    independentemente da versão da biblioteca websockets.
    """
    subprotocols = None
    for arg in args:
        if isinstance(arg, (list, tuple, set)):
            subprotocols = arg
            break
    if subprotocols is None:
        subprotocols = kwargs.get("subprotocols", [])

    if "arduino" in subprotocols:
        return "arduino"
    return None

async def main():
    print("=" * 70)
    print("  SMARTCART STR - SISTEMA DE CARRINHO INTELIGENTE EM TEMPO REAL")
    print("  Disciplina: PET2245 - Sistemas em Tempo Real")
    print("  Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros")
    print("  Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva")
    print("=" * 70)
    print("  Monitoramento Automático de Cesto por Visão Computacional de Borda")
    print(f"[STR] Servidor Unificado rodando em http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"[STR] Endpoint Câmera ESP32-CAM: ws://{SERVER_HOST}:{SERVER_PORT}/ws/camera")
    print(f"[STR] Endpoint Dashboard Web:    ws://{SERVER_HOST}:{SERVER_PORT}/ws/dashboard")
    print(f"[STR] Requisito Deadline:        D = {DEADLINE_MS} ms")
    print("=" * 70)

    async with websockets.serve(
        despachante_websocket,
        SERVER_HOST,
        SERVER_PORT,
        process_request=processar_requisicao_http,
        select_subprotocol=selecionar_subprotocolo,
        max_size=10 * 1024 * 1024
    ):
        await asyncio.Future()  # Mantém o loop executando indefinidamente

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SERVER-STR] Encerrado pelo operador.")
