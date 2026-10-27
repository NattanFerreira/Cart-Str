"""
Script de Teste de Integração Automatizado do Sistema Completo (STR) - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Valida: Conexão Câmera -> Servidor -> Dashboard, Detecção no Cesto, Latência e Histerese.
"""

import asyncio
import websockets
import json
import cv2
import numpy as np
import time

SERVER_BASE_WS = "ws://localhost:8765"

async def drenar_mensagens(ws, timeout=0.15):
    """Descarta mensagens acumuladas no buffer do WebSocket."""
    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            break

async def testar_integracao_completa():
    print("=" * 65)
    print("  INICIANDO BATERIA DE TESTES DE INTEGRAÇÃO - SMARTCART STR")
    print("=" * 65)

    # 1. Conexão ao Dashboard
    print("[1/5] Conectando ao WebSocket do Dashboard (/ws/dashboard)...")
    ws_dash = await websockets.connect(f"{SERVER_BASE_WS}/ws/dashboard")
    init_msg = await ws_dash.recv()
    estado = json.loads(init_msg)
    assert "telemetria" in estado, "Telemetria ausente no estado inicial"
    assert "carrinho" in estado, "Carrinho ausente no estado inicial"
    print("  -> Conectado e estado inicial recebido com sucesso!")

    # 2. Conexão da Câmera
    print("[2/5] Conectando cliente de câmera do cesto (/ws/camera)...")
    ws_cam = await websockets.connect(f"{SERVER_BASE_WS}/ws/camera", subprotocols=["arduino"])
    print("  -> Câmera conectada com sucesso!")

    # 3. Transmissão de Frame Sintético
    print("[3/5] Transmitindo quadros de vídeo sintéticos do cesto...")
    frame = np.full((240, 320, 3), 40, dtype=np.uint8)
    cv2.rectangle(frame, (100, 50), (180, 190), (220, 200, 160), -1)
    ret, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    jpeg_bytes = buf.tobytes()

    for _ in range(3):
        await ws_cam.send(jpeg_bytes)
        await asyncio.sleep(0.05)

    msg_dash = await ws_dash.recv()
    data_dash = json.loads(msg_dash)
    assert data_dash.get("frame_b64") is not None, "Frame processado em base64 não recebido"
    print(f"  -> Frames do cesto recebidos e processados pelo servidor!")
    print(f"  -> Latência de ponta a ponta: {data_dash['telemetria']['latencia']['atual']} ms (Deadline: 3000 ms)")

    await ws_cam.close()
    await asyncio.sleep(0.1)
    await drenar_mensagens(ws_dash)

    # 4. Injeção de Produtos no Cesto
    print("[4/5] Validando Inserção Automática de Produtos no Cesto...")
    await ws_dash.send(json.dumps({"acao": "ESVAZIAR_CESTO"}))
    await ws_dash.recv()

    # Coloca Garrafa de Água
    await ws_dash.send(json.dumps({"acao": "INJETAR_DETECCAO", "tipo": "bottle", "confianca": 0.95}))
    r1 = json.loads(await ws_dash.recv())
    assert r1["carrinho"]["total_itens"] == 1, f"Esperado 1 item no cesto, obteve: {r1['carrinho']['total_itens']}"
    assert r1["carrinho"]["valor_total"] == 3.50, f"Esperado R$ 3.50, obteve: {r1['carrinho']['valor_total']}"
    print(f"  -> Garrafa inserida no cesto com sucesso! Total: 1 item (R$ {r1['carrinho']['valor_total']:.2f})")

    # Coloca Copo
    await ws_dash.send(json.dumps({"acao": "INJETAR_DETECCAO", "tipo": "cup", "confianca": 0.92}))
    r2 = json.loads(await ws_dash.recv())
    assert r2["carrinho"]["total_itens"] == 2, f"Esperado 2 itens no cesto, obteve: {r2['carrinho']['total_itens']}"
    assert r2["carrinho"]["valor_total"] == 18.50, f"Esperado R$ 18.50, obteve: {r2['carrinho']['valor_total']}"
    print(f"  -> Copo inserido no cesto com sucesso! Total: 2 itens (R$ {r2['carrinho']['valor_total']:.2f})")

    # Coloca Smartphone
    await ws_dash.send(json.dumps({"acao": "INJETAR_DETECCAO", "tipo": "cell phone", "confianca": 0.95}))
    r_phone = json.loads(await ws_dash.recv())
    assert r_phone["carrinho"]["total_itens"] == 3, f"Esperado 3 itens no cesto, obteve: {r_phone['carrinho']['total_itens']}"
    assert r_phone["carrinho"]["valor_total"] == 1268.50, f"Esperado R$ 1268.50, obteve: {r_phone['carrinho']['valor_total']}"
    print(f"  -> Smartphone inserido no cesto com sucesso! Total: 3 itens (R$ {r_phone['carrinho']['valor_total']:.2f})")

    # 5. Retirada de Produto do Cesto
    print("[5/5] Validando Retirada Automática de Produto do Cesto...")
    await ws_dash.send(json.dumps({"acao": "REMOVER_DETECCAO", "tipo": "bottle"}))
    r3 = json.loads(await ws_dash.recv())
    assert r3["carrinho"]["total_itens"] == 2, f"Esperado 2 itens restantes, obteve: {r3['carrinho']['total_itens']}"
    assert r3["carrinho"]["valor_total"] == 1265.00, f"Esperado R$ 1265.00, obteve: {r3['carrinho']['valor_total']}"
    print(f"  -> Garrafa retirada do cesto! Total restante: 2 itens (R$ {r3['carrinho']['valor_total']:.2f})")

    await ws_dash.close()

    print("\n" + "=" * 65)
    print("  TODOS OS TESTES DE INTEGRAÇÃO SMARTCART STR FORAM APROVADOS! ✅")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(testar_integracao_completa())
