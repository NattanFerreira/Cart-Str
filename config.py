"""
Configurações Globais do Sistema Carrinho Inteligente - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Arquitetura: Monitoramento Automático de Cesto em Tempo Real (Edge AI).
A câmera ESP32-CAM fica acoplada apontando para o interior do carrinho.
Produtos são adicionados ao entrar na visão e removidos ao saírem.
"""

import os

# Configurações de Rede e Servidor
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8765
DASHBOARD_PORT = 8765

# Requisitos de Sistemas em Tempo Real (STR)
DEADLINE_MS = 3000.0         # Deadline estipulado estendido para 3000 ms para garantia estrita de STR
TARGET_FPS = 20              # Taxa de amostragem nominal: 20 FPS (período nominal T = 50 ms)
NOMINAL_PERIOD_MS = 1000.0 / TARGET_FPS
CONFIDENCE_THRESHOLD = 0.40  # Limiar calibrado: 40% de confiança para classes YOLO

# Parâmetros de Estabilidade e Histerese Temporal do Cesto (Anti-Flicker)
# Evita falsas adições por ruído e falsas remoções por oclusão momentânea da mão
PRESENCE_CONFIRM_FRAMES = 2  # Número de quadros consecutivos necessários para confirmar entrada (~100 ms)
ABSENCE_TIMEOUT_SEC = 1.2    # Tempo de ausência contínua antes de confirmar retirada do cesto (1.2 s)

# Catálogo de Produtos do MVP: Garrafa de Água, Copo / Caneca e Smartphone / Celular (Classes Nativas COCO)
CATALOGO_PRODUTOS = {
    # Produto 1: Garrafa de Água Mineral (Classe COCO: bottle - ID 39)
    "garrafa_agua": {
        "id": "PROD-001",
        "nome": "Garrafa de Água Mineral 500ml",
        "categoria": "Bebidas",
        "preco": 3.50,
        "aliases": ["bottle", "water bottle", "garrafa", "garrafa de agua", "agua"]
    },
    # Produto 2: Copo / Caneca (Classe COCO: cup / wine glass - IDs 41, 40)
    "copo": {
        "id": "PROD-002",
        "nome": "Copo / Caneca de Vidro",
        "categoria": "Utilidades",
        "preco": 15.00,
        "aliases": ["cup", "copo", "caneca", "xicara", "mug", "wine glass", "taca"]
    },
    # Produto 3: Smartphone / Celular (Classe COCO: cell phone - ID 67)
    "celular": {
        "id": "PROD-003",
        "nome": "Smartphone Galaxy / iPhone",
        "categoria": "Eletrônicos",
        "preco": 1250.00,
        "aliases": ["cell phone", "cellphone", "celular", "telefone", "phone", "smartphone", "mobile phone"]
    }
}

# Diretórios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
