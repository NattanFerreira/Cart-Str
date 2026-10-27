"""
Cliente Simulador de Câmera Acoplada ao Cesto (Webcam / Câmera Virtual) - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Simula a visão do ESP32-CAM montado no carrinho, apontando para o interior do cesto.
Permite testar a entrada e saída de produtos em tempo real com teclas interativas:
  [1] Colocar / Retirar Garrafa de Água Mineral
  [2] Colocar / Retirar Copo / Caneca
  [3] Colocar Ambos no cesto
  [0] Esvaziar cesto (carrinho vazio)
  [Q] Encerrar simulador
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import cv2
import asyncio
import websockets
import time
import argparse
import sys
import numpy as np
import json

DEFAULT_SERVER_URL = "ws://localhost:8765/ws/camera"
TARGET_FPS = 25
FRAME_INTERVAL = 1.0 / TARGET_FPS

class CameraCestoClient:
    def __init__(self, server_url: str = DEFAULT_SERVER_URL, camera_id: int = 0,
                 use_virtual: bool = False, width: int = 320, height: int = 240,
                 show_preview: bool = True):
        self.server_url = server_url
        self.camera_id = camera_id
        self.use_virtual = use_virtual
        self.width = width
        self.height = height
        self.show_preview = show_preview
        self.cap = None
        self.running = True

        # Itens atualmente presentes no interior do cesto simulado:
        self.cesto_garrafa = True   # Inicia com garrafa no cesto
        self.cesto_copo = False     # Copo / Caneca
        self.cesto_celular = False  # Smartphone / Celular

        # Posição e dinâmica dos objetos no cesto
        self.pos_x_garrafa = 40
        self.pos_x_copo = 210
        self.pos_x_celular = 125
        self.dir_garrafa = 1
        self.dir_copo = -1
        self.dir_celular = 1

        # Notificação de feedback sonoro recebido do servidor
        self.ultimo_feedback = "Cesto pronto"
        self.tempo_feedback = time.time()

    def inicializar_dispositivo(self):
        if not self.use_virtual:
            print(f"[CAM-CESTO] Tentando abrir webcam de índice {self.camera_id}...")
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                print(f"[CAM-CESTO] AVISO: Webcam {self.camera_id} não encontrada.")
                print("[CAM-CESTO] Ativando automaticamente o MODO DE CESTO VIRTUAL INTELIGENTE!")
                self.use_virtual = True
            else:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                print(f"[CAM-CESTO] Webcam conectada ({self.width}x{self.height} @ {TARGET_FPS} FPS)!")

    def gerar_frame_cesto_virtual(self) -> np.ndarray:
        """
        Gera um frame realista visto do topo da barra do carrinho olhando para o interior do cesto metálico.
        """
        frame = np.full((self.height, self.width, 3), 32, dtype=np.uint8)

        # Fundo: Grelha metálica aramada do fundo e laterais do cesto
        for y in range(0, self.height, 24):
            cv2.line(frame, (0, y), (self.width, y), (50, 52, 54), 1)
        for x in range(0, self.width, 24):
            cv2.line(frame, (x, 0), (x, self.height), (50, 52, 54), 1)

        # Borda superior do cesto
        cv2.rectangle(frame, (2, 2), (self.width - 2, self.height - 2), (70, 75, 80), 2)

        # Animação sutil de movimento natural dentro do carrinho
        if self.cesto_garrafa:
            self.pos_x_garrafa += self.dir_garrafa
            if self.pos_x_garrafa > 105 or self.pos_x_garrafa < 35:
                self.dir_garrafa *= -1

            gx = self.pos_x_garrafa
            gy = int(self.height * 0.22)

            # Sombra no fundo do cesto
            cv2.ellipse(frame, (gx + 22, gy + 120), (28, 8), 0, 0, 360, (20, 20, 20), -1)

            # Corpo da Garrafa de Água Mineral (translúcido ciano/azul)
            cv2.rectangle(frame, (gx, gy), (gx + 46, gy + 115), (235, 215, 170), -1)
            # Tampa azul escura
            cv2.rectangle(frame, (gx + 12, gy - 12), (gx + 34, gy), (210, 60, 20), -1)
            # Rótulo azul com marca
            cv2.rectangle(frame, (gx, gy + 38), (gx + 46, gy + 75), (245, 130, 30), -1)
            cv2.putText(frame, "AGUA", (gx + 4, gy + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

        if self.cesto_copo:
            self.pos_x_copo += self.dir_copo
            if self.pos_x_copo > 235 or self.pos_x_copo < 155:
                self.dir_copo *= -1

            cx = self.pos_x_copo
            cy = int(self.height * 0.30)

            # Sombra no fundo do cesto
            cv2.ellipse(frame, (cx + 25, cy + 98), (26, 8), 0, 0, 360, (20, 20, 20), -1)

            # Copo / Caneca
            cv2.rectangle(frame, (cx, cy + 15), (cx + 50, cy + 95), (180, 180, 240), -1)
            # Asa da caneca
            cv2.ellipse(frame, (cx + 50, cy + 55), (14, 22), 0, -90, 90, (180, 180, 240), 4)
            # Borda superior
            cv2.ellipse(frame, (cx + 25, cy + 15), (25, 7), 0, 0, 360, (220, 220, 255), -1)
            cv2.putText(frame, "COPO", (cx + 5, cy + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (40, 40, 120), 1)

        if self.cesto_celular:
            px = self.pos_x_celular
            py = int(self.height * 0.35)

            # Sombra no fundo do cesto
            cv2.ellipse(frame, (px + 22, py + 75), (25, 7), 0, 0, 360, (18, 18, 18), -1)

            # Corpo do Celular (preto/cinza escuro)
            cv2.rectangle(frame, (px, py), (px + 44, py + 74), (25, 25, 25), -1)
            # Borda prateada
            cv2.rectangle(frame, (px, py), (px + 44, py + 74), (160, 160, 160), 1)
            # Tela AMOLED
            cv2.rectangle(frame, (px + 3, py + 4), (px + 41, py + 70), (75, 40, 20), -1)
            # Notch do topo
            cv2.circle(frame, (px + 22, py + 7), 2, (15, 15, 15), -1)
            cv2.putText(frame, "12:00", (px + 7, py + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (255, 255, 255), 1)
            cv2.putText(frame, "PHONE", (px + 5, py + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (0, 255, 120), 1)

        if not self.cesto_garrafa and not self.cesto_copo and not self.cesto_celular:
            cv2.putText(frame, "[CESTO VAZIO - NENHUM ITEM]", (24, int(self.height * 0.5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 120, 120), 1)

        # Barra de feedback sonoro do servidor
        if time.time() - self.tempo_feedback < 2.0:
            cv2.putText(frame, f">> {self.ultimo_feedback}", (10, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 180), 1)

        # Instruções de controle do simulador na parte inferior
        cv2.rectangle(frame, (0, self.height - 22), (self.width, self.height), (20, 20, 20), -1)
        cv2.putText(frame, "[1] Garrafa | [2] Copo | [3] Celular | [4] Todos | [0] Vazio | [Q] Sair",
                    (4, self.height - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (190, 190, 190), 1)

        return frame

    async def escutar_feedback_servidor(self, ws):
        """Escuta respostas do servidor STR indicando inclusão (1 beep) ou retirada (2 beeps)."""
        try:
            async for resposta in ws:
                dados = json.loads(resposta)
                evento = dados.get("evento")
                prod = dados.get("produto", "Item")
                if evento == "PRODUTO_REGISTRADO":
                    self.ultimo_feedback = f"BEEP 1x: '{prod}' COLOCADO NO CESTO!"
                    self.tempo_feedback = time.time()
                    print(f"[BORDA ESP32] >>> 🔔 BEEP 1x: Item colocado no carrinho -> {prod}")
                elif evento == "PRODUTO_REMOVIDO":
                    self.ultimo_feedback = f"BEEP 2x: '{prod}' RETIRADO DO CESTO!"
                    self.tempo_feedback = time.time()
                    print(f"[BORDA ESP32] <<< 🔔🔔 BEEP 2x: Item retirado do carrinho -> {prod}")
        except Exception:
            pass

    async def loop_captura_e_transmissao(self, ws):
        print("[CAM-CESTO] Streaming ao vivo iniciado a 25 FPS...")
        tarefa_feedback = asyncio.create_task(self.escutar_feedback_servidor(ws))

        try:
            while self.running:
                t_inicio = time.time()

                if self.use_virtual:
                    frame = self.gerar_frame_cesto_virtual()
                else:
                    ret, frame = self.cap.read()
                    if not ret:
                        print("[CAM-CESTO] Falha na captura da webcam. Alternando para cesto virtual.")
                        self.use_virtual = True
                        continue
                    frame = cv2.resize(frame, (self.width, self.height))

                # Codificação JPEG
                ret_enc, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if ret_enc:
                    await ws.send(buf.tobytes())

                # Exibição do preview local e controle de teclado
                if self.show_preview:
                    cv2.imshow("SmartCart STR - Visao do Cesto", frame)
                    key = cv2.waitKey(1) & 0xFF

                    if key == ord('q') or key == ord('Q') or key == 27:
                        self.running = False
                        break
                    elif key == ord('1'):
                        self.cesto_garrafa = not self.cesto_garrafa
                        print(f"[SIMULADOR] Garrafa no cesto: {self.cesto_garrafa}")
                    elif key == ord('2'):
                        self.cesto_copo = not self.cesto_copo
                        print(f"[SIMULADOR] Copo/Caneca no cesto: {self.cesto_copo}")
                    elif key == ord('3'):
                        self.cesto_celular = not self.cesto_celular
                        print(f"[SIMULADOR] Smartphone no cesto: {self.cesto_celular}")
                    elif key == ord('4'):
                        self.cesto_garrafa = True
                        self.cesto_copo = True
                        self.cesto_celular = True
                        print("[SIMULADOR] Todos os 3 produtos no cesto!")
                    elif key == ord('0'):
                        self.cesto_garrafa = False
                        self.cesto_copo = False
                        self.cesto_celular = False
                        print("[SIMULADOR] Cesto esvaziado!")

                tempo_gasto = time.time() - t_inicio
                espera = FRAME_INTERVAL - tempo_gasto
                if espera > 0:
                    await asyncio.sleep(espera)
                else:
                    await asyncio.sleep(0.001)

        finally:
            tarefa_feedback.cancel()
            if self.cap:
                self.cap.release()
            cv2.destroyAllWindows()

    async def executar(self):
        self.inicializar_dispositivo()
        while self.running:
            try:
                print(f"[CAM-CESTO] Conectando ao servidor STR em {self.server_url}...")
                async with websockets.connect(self.server_url, subprotocols=["arduino"]) as ws:
                    print("[CAM-CESTO] CONECTADO AO SERVIDOR STR!")
                    # Handshake de identificação de borda
                    await ws.send(json.dumps({"tipo": "DISPOSITIVO_BORDA", "id": "CESTO-SIMULADOR-01"}))
                    await self.loop_captura_e_transmissao(ws)
            except (ConnectionRefusedError, websockets.exceptions.ConnectionClosed):
                if not self.running:
                    break
                print("[CAM-CESTO] Servidor STR indisponivel. Tentando reconectar em 2s...")
                await asyncio.sleep(2.0)
            except Exception as e:
                if not self.running:
                    break
                print(f"[CAM-CESTO] Erro: {e}. Reconectando...")
                await asyncio.sleep(2.0)

def main():
    parser = argparse.ArgumentParser(description="Cliente Simulador de Câmera do Cesto - SmartCart STR")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="URL WebSocket do Servidor")
    parser.add_argument("--cam", type=int, default=0, help="Índice da Webcam física")
    parser.add_argument("--virtual", action="store_true", help="Forçar Cesto Virtual Sintético")
    parser.add_argument("--no-preview", action="store_true", help="Desativar janela de preview")
    args = parser.parse_args()

    cliente = CameraCestoClient(
        server_url=args.url,
        camera_id=args.cam,
        use_virtual=args.virtual,
        show_preview=not args.no_preview
    )

    try:
        asyncio.run(cliente.executar())
    except KeyboardInterrupt:
        print("\n[CAM-CESTO] Encerrado pelo usuário.")

if __name__ == "__main__":
    main()
