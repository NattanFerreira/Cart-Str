"""
Pipeline de Visão Computacional de Alta Precisão e Baixa Latência (STR) - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Especializado para visão interna do cesto: monitora múltiplos produtos simultaneamente
(Garrafas de Água Mineral, Copos/Canecas e Smartphones) garantindo inferência acelerada (<35ms).
"""

import os
import cv2
import numpy as np
import time
from typing import List, Dict, Any, Tuple
from config import CONFIDENCE_THRESHOLD, CATALOGO_PRODUTOS

try:
    import torch
    torch.set_num_threads(4)
except Exception:
    pass

# Classes COCO Mapeadas para o MVP:
# 39: bottle (Garrafa de Água Mineral)
# 67: cell phone (Smartphone / Celular)
# 41: cup (Copo, Caneca, Xícara - mantido para retrocompatibilidade)
# 40: wine glass (Taça, Copo de Vidro)
# 73: book (Livro / Caderno)
CLASSES_ALVO = [39, 67, 41, 40, 73]

def calcular_iou(box1, box2):
    """Calcula a Interseção sobre União (IoU) entre duas caixas delimitadoras."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h
    area1 = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    area2 = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area
    return inter_area / union_area if union_area > 0 else 0

class PipelineVisao:
    def __init__(self, conf_threshold: float = CONFIDENCE_THRESHOLD):
        self.conf_threshold = conf_threshold
        self.modelo_tipo = "NENHUM"
        self.modelo_yolo = None
        self._inicializar_modelo()

    def _inicializar_modelo(self):
        """
        Carrega e aquece o modelo YOLOv8n para detecção nativa no interior do carrinho.
        """
        try:
            from ultralytics import YOLO

            base_dir = os.path.dirname(os.path.abspath(__file__))
            caminho_local = os.path.join(base_dir, "yolov8n.pt")

            if os.path.exists(caminho_local):
                caminho_modelo = caminho_local
            else:
                caminho_modelo = "yolov8n.pt"

            print(f"[VISÃO-STR] Carregando modelo YOLOv8n ({caminho_modelo})...")
            self.modelo_yolo = YOLO(caminho_modelo)
            self.modelo_tipo = "YOLOv8n"

            # Warmup prévio com imgsz=320 para eliminar atraso no primeiro frame
            dummy = np.zeros((240, 320, 3), dtype=np.uint8)
            with torch.inference_mode():
                _ = self.modelo_yolo(dummy, imgsz=320, verbose=False, classes=CLASSES_ALVO)
                _ = self.modelo_yolo(dummy, imgsz=320, verbose=False, classes=CLASSES_ALVO)
            print("[VISÃO-STR] Modelo YOLOv8n aquecido e pronto para monitoramento ao vivo do cesto!")
        except Exception as e:
            print(f"[VISÃO-STR] Ultralytics YOLO não disponível ({e}). Utilizando Fallback OpenCV.")
            self.modelo_tipo = "OPENCV_FALLBACK"

    def detectar_produtos(self, frame_bgr: np.ndarray) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        """
        Executa inferência em tempo real e retorna:
        - Lista de objetos detectados no cesto com boxes e confianças.
        - Frame anotado com HUD visual para streaming no Dashboard.
        """
        h_frame, w_frame, _ = frame_bgr.shape
        area_total = h_frame * w_frame
        deteccoes_brutas = []
        frame_anotado = frame_bgr.copy()

        if self.modelo_tipo == "YOLOv8n" and self.modelo_yolo is not None:
            try:
                with torch.inference_mode():
                    resultados = self.modelo_yolo(
                        frame_bgr,
                        imgsz=320,
                        verbose=False,
                        conf=self.conf_threshold,
                        classes=CLASSES_ALVO
                    )
                for r in resultados:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = r.names[cls_id].lower()
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                        # Descarta ruídos muito minúsculos (< 2% da área do frame)
                        box_area = (x2 - x1) * (y2 - y1)
                        if box_area < (area_total * 0.02):
                            continue

                        # Mapeamento para as classes do catálogo do MVP (3 Produtos)
                        if cls_name == "bottle":
                            label_unificado = "bottle"
                            tag_produto = "GARRAFA DE AGUA"
                        elif cls_name in ("cup", "wine glass"):
                            label_unificado = "cup"
                            tag_produto = "COPO / CANECA"
                        elif cls_name in ("cell phone", "phone", "cellphone"):
                            label_unificado = "cell phone"
                            tag_produto = "SMARTPHONE"
                        elif cls_name in ("book", "laptop"):
                            label_unificado = "cup"
                            tag_produto = "COPO / CANECA"
                        else:
                            continue

                        deteccoes_brutas.append({
                            "label": label_unificado,
                            "tag": tag_produto,
                            "raw_label": cls_name,
                            "conf": conf,
                            "box": (x1, y1, x2, y2)
                        })
            except Exception as err:
                print(f"[VISÃO-STR] Erro na inferência YOLO: {err}")

        # Ordena da maior confiança para a menor
        deteccoes_brutas.sort(key=lambda d: d["conf"], reverse=True)

        # NMS entre caixas sobrepostas: impede contar o mesmo objeto duas vezes
        deteccoes_filtradas = []
        for det in deteccoes_brutas:
            sobreposto = False
            for aceito in deteccoes_filtradas:
                if calcular_iou(det["box"], aceito["box"]) > 0.40:
                    sobreposto = True
                    break
            if not sobreposto:
                deteccoes_filtradas.append(det)

        # Fallback se necessário
        if not deteccoes_filtradas and self.modelo_tipo == "OPENCV_FALLBACK":
            deteccoes_filtradas = self._detector_heuristico(frame_bgr)

        # Desenha anotações no frame (HUD de Cesto Inteligente)
        # Moldura sutil do cesto
        cv2.rectangle(frame_anotado, (4, 4), (w_frame - 4, h_frame - 4), (0, 200, 100), 1)
        cv2.putText(frame_anotado, "CESTO [MONITORAMENTO AO VIVO]", (10, 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 120), 1, cv2.LINE_AA)

        for det in deteccoes_filtradas:
            x1, y1, x2, y2 = det["box"]
            label = det["label"]
            conf = det["conf"]

            if label == "bottle":
                nome_exibicao = "GARRAFA 500ML"
                cor = (0, 220, 255)  # Dourado / Ciano para Garrafa
            elif label == "cup":
                nome_exibicao = "COPO / CANECA"
                cor = (255, 120, 0)  # Azul Royal para Copo
            elif label == "cell phone":
                nome_exibicao = "SMARTPHONE"
                cor = (0, 255, 130)  # Verde Neon para Celular
            else:
                nome_exibicao = label.upper()
                cor = (0, 255, 0)

            # Caixa delimitadora destacada
            cv2.rectangle(frame_anotado, (x1, y1), (x2, y2), cor, 2)

            # Badge de identificação com "NO CESTO"
            texto = f"{nome_exibicao} ({conf*100:.0f}%) [NO CESTO]"
            (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            cv2.rectangle(frame_anotado, (x1, max(0, y1 - 22)), (x1 + tw + 8, max(0, y1)), cor, -1)
            cv2.putText(frame_anotado, texto, (x1 + 4, max(15, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)

        return deteccoes_filtradas, frame_anotado

    def _detector_heuristico(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """Detector básico de contornos para testes caso a biblioteca ultralytics falhe."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        h, w = frame_bgr.shape[:2]
        deteccoes = []

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contornos, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contornos:
            area = cv2.contourArea(c)
            if area > (h * w * 0.05):
                x, y, bw, bh = cv2.boundingRect(c)
                razao_aspecto = float(bh) / bw if bw > 0 else 0

                if 1.5 <= razao_aspecto <= 4.0:
                    deteccoes.append({
                        "label": "bottle",
                        "conf": 0.82,
                        "box": (x, y, x + bw, y + bh)
                    })
                    break
                elif 0.7 <= razao_aspecto < 1.5:
                    deteccoes.append({
                        "label": "cup",
                        "conf": 0.80,
                        "box": (x, y, x + bw, y + bh)
                    })
                    break

        return deteccoes
