"""
Benchmark Automatizado de Sistemas em Tempo Real (STR) - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Mede e gera relatório estatístico de desempenho da esteira de visão do cesto:
- Latência Média, Mínima e WCET (Pior Caso)
- Jitter Médio e Máximo
- Previsibilidade e Slack Time
- Conformidade estrita com o Deadline (D = 3000 ms)
"""

import asyncio
import websockets
import time
import json
import cv2
import numpy as np

SERVER_URL = "ws://localhost:8765/ws/camera"
NUMERO_QUADROS = 100
INTERVALO_NOMINAL_S = 0.05  # 50 ms = 20 FPS nominal

def gerar_quadro_cesto():
    """Gera quadro sintético simulando interior do cesto com produtos."""
    frame = np.full((240, 320, 3), 35, dtype=np.uint8)
    # Grelha do cesto
    for y in range(0, 240, 30):
        cv2.line(frame, (0, y), (320, y), (55, 55, 55), 1)
    for x in range(0, 320, 30):
        cv2.line(frame, (x, 0), (x, 240), (55, 55, 55), 1)
    # Garrafa de água
    cv2.rectangle(frame, (80, 60), (130, 180), (220, 200, 160), -1)
    # Copo
    cv2.rectangle(frame, (190, 80), (240, 165), (170, 170, 230), -1)
    ret, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    return buf.tobytes()

async def executar_benchmark():
    print("=" * 70)
    print("  BENCHMARK DE TEMPO REAL (STR) - SMARTCART STR")
    print("  Disciplina: PET2245 - Sistemas em Tempo Real")
    print("  Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros")
    print("  Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva")
    print(f"  Amostras a transmitir: {NUMERO_QUADROS} quadros @ 20 FPS nominais")
    print("=" * 70)

    buffer_jpeg = gerar_quadro_cesto()
    tempos_rtt = []

    try:
        async with websockets.connect(SERVER_URL, subprotocols=["arduino"]) as ws:
            # Handshake
            await ws.send(json.dumps({"tipo": "DISPOSITIVO_BORDA", "id": "BENCHMARK-STR"}))
            print("[BENCHMARK] Conectado ao servidor STR. Disparando amostragem...")

            for i in range(NUMERO_QUADROS):
                t_envio = time.perf_counter_ns()
                await ws.send(buffer_jpeg)

                # Aguarda confirmação periódica ou continua em regime contínuo
                t_chegada = time.perf_counter_ns()
                rtt_ms = (t_chegada - t_envio) / 1_000_000.0
                tempos_rtt.append(rtt_ms)

                await asyncio.sleep(INTERVALO_NOMINAL_S)
                if (i + 1) % 25 == 0:
                    print(f"  -> Progresso: {i + 1}/{NUMERO_QUADROS} quadros enviados...")

    except Exception as e:
        print(f"[BENCHMARK] Erro durante benchmark: {e}")
        return

    # Consulta métricas consolidadas pelo servidor
    async with websockets.connect("ws://localhost:8765/ws/dashboard") as ws_dash:
        msg = await ws_dash.recv()
        dados = json.loads(msg)
        tele = dados.get("telemetria", {})

    print("\n" + "=" * 65)
    print("  RELATÓRIO DE DESEMPENHO EM TEMPO REAL (STR) - RESULTADOS")
    print("=" * 65)
    lat = tele.get("latencia", {})
    jit = tele.get("jitter", {})
    deadline = tele.get("deadline_ms", 3000.0)

    print(f"  • Total de Amostras Processadas: {tele.get('total_amostras', 0)}")
    print(f"  • Taxa de Quadros Nominal (FPS): {tele.get('fps', 0)} FPS")
    print(f"  • Deadline Estipulado (D):       {deadline:.1f} ms")
    print(f"  • Latência Média:                 {lat.get('media', 0):.2f} ms")
    print(f"  • Latência Mínima:                {lat.get('min', 0):.2f} ms")
    print(f"  • WCET (Pior Caso Medido):        {lat.get('wcet', 0):.2f} ms")
    print(f"  • Desvio Padrão da Latência:      {lat.get('desvio', 0):.2f} ms")
    print(f"  • Jitter Médio:                   {jit.get('media', 0):.2f} ms")
    print(f"  • Jitter Máximo:                  {jit.get('max', 0):.2f} ms")
    print(f"  • Slack Time Disponível:          {tele.get('slack_time_ms', 0):.2f} ms")
    print(f"  • Violações de Deadline:          {tele.get('violacoes', 0)} ({tele.get('taxa_violacao_pct', 0):.2f}%)")
    print("=" * 65)

    if tele.get("violacoes", 0) == 0:
        print("  CLASSIFICAÇÃO STR: PREVISÍVEL (SOFT REAL-TIME GARANTIDO) ✅")
    else:
        print("  CLASSIFICAÇÃO STR: DEGRADAÇÃO DETECTADA COM VIOLAÇÕES ⚠️")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(executar_benchmark())
