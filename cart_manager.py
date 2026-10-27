"""
Gerenciador de Carrinho Inteligente - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Monitoramento Automático de Cesto em Tempo Real (STR).
Rastreia a presença física dos produtos dentro do carrinho por visão computacional contínua.
Aplica histerese temporal: confirmação rápida de entrada (~100ms) e tolerância de ausência (~1.2s)
para prevenir instabilidades de amostragem e oclusões transitórias (ex: mão do consumidor).
"""

import time
from typing import Dict, Any, List, Tuple, Optional
from config import (
    CATALOGO_PRODUTOS, CONFIDENCE_THRESHOLD,
    PRESENCE_CONFIRM_FRAMES, ABSENCE_TIMEOUT_SEC
)

class GerenciadorCarrinhoAoVivo:
    def __init__(self,
                 confirm_frames: int = PRESENCE_CONFIRM_FRAMES,
                 absence_timeout: float = ABSENCE_TIMEOUT_SEC,
                 conf_min: float = CONFIDENCE_THRESHOLD):
        self.confirm_frames = confirm_frames
        self.absence_timeout = absence_timeout
        self.conf_min = conf_min

        # Itens confirmados no carrinho:
        # {prod_id: {"id": str, "nome": str, "categoria": str, "preco_unitario": float,
        #            "quantidade": int, "subtotal": float, "adicionado_em": str, "visivel_agora": bool}}
        self.itens: Dict[str, Dict[str, Any]] = {}

        # Rastreamento de Histerese Temporal por ID do produto:
        # {prod_id: {
        #     "contagem_atual_confirmada": int,
        #     "candidato_qtd": int,
        #     "frames_consecutivos": int,
        #     "timestamps_por_nivel": {1: float, 2: float, ...} # último momento em que cada quantidade foi vista
        # }}
        self.rastreamento: Dict[str, Dict[str, Any]] = {}

        # Histórico de eventos em ordem cronológica reversa
        self.historico_eventos: List[Dict[str, Any]] = []

    def resolver_produto(self, label: str) -> Optional[Dict[str, Any]]:
        """Resolve o rótulo detectado para um item cadastrado no catálogo oficial."""
        label_lower = label.lower().strip()
        if label_lower in CATALOGO_PRODUTOS:
            return CATALOGO_PRODUTOS[label_lower]

        for prod_key, info in CATALOGO_PRODUTOS.items():
            if label_lower in info.get("aliases", []):
                return info
        return None

    def atualizar_inventario_ao_vivo(self, deteccoes_frame: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Método central de processamento em tempo real (STR).
        Recebe a lista de detecções do quadro atual e atualiza o inventário do carrinho
        com base na presença física visível ao vivo.

        Retorna lista de eventos ocorridos no frame:
        [{"tipo": "REGISTRADO"|"REMOVIDO", "produto": dict, "quantidade": int, "mensagem": str}]
        """
        agora_s = time.time()
        eventos_gerados: List[Dict[str, Any]] = []

        # 1. Contagem instantânea de itens detectados no quadro atual com confiança válida
        contagem_frame: Dict[str, int] = {}
        info_produtos: Dict[str, Dict[str, Any]] = {}

        for det in deteccoes_frame:
            conf = det.get("conf", 0.0)
            if conf < self.conf_min:
                continue

            label = det.get("label", "")
            prod = self.resolver_produto(label)
            if not prod:
                continue

            prod_id = prod["id"]
            contagem_frame[prod_id] = contagem_frame.get(prod_id, 0) + 1
            info_produtos[prod_id] = prod

        # Todos os produtos conhecidos (ou já no carrinho, ou detectados agora)
        todos_ids = set(contagem_frame.keys()) | set(self.itens.keys()) | set(self.rastreamento.keys())

        for prod_id in todos_ids:
            # Garante inicialização do registro de rastreamento
            if prod_id not in self.rastreamento:
                self.rastreamento[prod_id] = {
                    "contagem_atual_confirmada": 0,
                    "candidato_qtd": 0,
                    "frames_consecutivos": 0,
                    "timestamps_por_nivel": {}
                }

            rastr = self.rastreamento[prod_id]
            qtd_vista = contagem_frame.get(prod_id, 0)
            qtd_confirmada = rastr["contagem_atual_confirmada"]

            # Atualiza os timestamps de presença para as instâncias visíveis
            for nivel in range(1, qtd_vista + 1):
                rastr["timestamps_por_nivel"][nivel] = agora_s

            # Obtém metadados do produto
            prod_meta = info_produtos.get(prod_id)
            if not prod_meta and prod_id in self.itens:
                prod_meta = {
                    "id": self.itens[prod_id]["id"],
                    "nome": self.itens[prod_id]["nome"],
                    "categoria": self.itens[prod_id]["categoria"],
                    "preco": self.itens[prod_id]["preco_unitario"]
                }
            if not prod_meta:
                continue

            # CASO A: Aumento de quantidade detectada no cesto (NOVO ITEM COLOCADO)
            if qtd_vista > qtd_confirmada:
                if rastr["candidato_qtd"] == qtd_vista:
                    rastr["frames_consecutivos"] += 1
                else:
                    rastr["candidato_qtd"] = qtd_vista
                    rastr["frames_consecutivos"] = 1

                # Confirmado após janela de histerese (evita falso positivo instantâneo)
                if rastr["frames_consecutivos"] >= self.confirm_frames:
                    qtd_adicionar = qtd_vista - qtd_confirmada
                    for _ in range(qtd_adicionar):
                        self._aplicar_adicao(prod_meta)
                    
                    rastr["contagem_atual_confirmada"] = qtd_vista
                    rastr["candidato_qtd"] = qtd_vista

                    msg = f"'{prod_meta['nome']}' inserido no cesto (Qtd: {qtd_vista})"
                    evento = {
                        "tipo": "REGISTRADO",
                        "produto": prod_meta,
                        "quantidade": qtd_vista,
                        "mensagem": msg
                    }
                    self._registrar_log_evento("ADICAO", prod_meta["nome"], qtd_vista, "Ao Vivo")
                    eventos_gerados.append(evento)

            # CASO B: Queda na quantidade detectada (ITEM RETIRADO DO CESTO)
            elif qtd_vista < qtd_confirmada:
                # Reseta candidato de aumento
                rastr["candidato_qtd"] = qtd_vista
                rastr["frames_consecutivos"] = 0

                # Verifica se as instâncias ausentes excederam o tempo de tolerância (ausência contínua)
                nova_qtd_confirmada = qtd_confirmada
                for nivel in range(qtd_confirmada, qtd_vista, -1):
                    ultimo_ts = rastr["timestamps_por_nivel"].get(nivel, 0.0)
                    if (agora_s - ultimo_ts) >= self.absence_timeout:
                        nova_qtd_confirmada = nivel - 1

                if nova_qtd_confirmada < qtd_confirmada:
                    qtd_remover = qtd_confirmada - nova_qtd_confirmada
                    for _ in range(qtd_remover):
                        self._aplicar_remocao(prod_id)

                    rastr["contagem_atual_confirmada"] = nova_qtd_confirmada
                    # Limpa níveis removidos
                    for nivel in range(nova_qtd_confirmada + 1, qtd_confirmada + 1):
                        rastr["timestamps_por_nivel"].pop(nivel, None)

                    msg = f"'{prod_meta['nome']}' retirado do cesto (Restam: {nova_qtd_confirmada})"
                    evento = {
                        "tipo": "REMOVIDO",
                        "produto": prod_meta,
                        "quantidade": nova_qtd_confirmada,
                        "mensagem": msg
                    }
                    self._registrar_log_evento("REMOCAO", prod_meta["nome"], nova_qtd_confirmada, "Ao Vivo")
                    eventos_gerados.append(evento)

            # CASO C: Quantidade estável visível
            else:
                rastr["candidato_qtd"] = qtd_vista
                rastr["frames_consecutivos"] = self.confirm_frames

        # Atualiza a flag visual de presença em tempo real nos itens do carrinho
        for prod_id, item_info in self.itens.items():
            item_info["visivel_ao_vivo"] = (contagem_frame.get(prod_id, 0) > 0)

        return eventos_gerados

    def _aplicar_adicao(self, prod_meta: Dict[str, Any]):
        """Adiciona 1 unidade do produto à lista de itens do carrinho."""
        prod_id = prod_meta["id"]
        if prod_id not in self.itens:
            self.itens[prod_id] = {
                "id": prod_id,
                "nome": prod_meta["nome"],
                "categoria": prod_meta["categoria"],
                "preco_unitario": prod_meta["preco"],
                "quantidade": 1,
                "subtotal": prod_meta["preco"],
                "adicionado_em": time.strftime("%H:%M:%S"),
                "visivel_ao_vivo": True
            }
        else:
            self.itens[prod_id]["quantidade"] += 1
            self.itens[prod_id]["subtotal"] = round(
                self.itens[prod_id]["quantidade"] * self.itens[prod_id]["preco_unitario"], 2
            )
            self.itens[prod_id]["visivel_ao_vivo"] = True

    def _aplicar_remocao(self, prod_id: str):
        """Remove 1 unidade do produto da lista de itens do carrinho."""
        if prod_id in self.itens:
            if self.itens[prod_id]["quantidade"] > 1:
                self.itens[prod_id]["quantidade"] -= 1
                self.itens[prod_id]["subtotal"] = round(
                    self.itens[prod_id]["quantidade"] * self.itens[prod_id]["preco_unitario"], 2
                )
            else:
                del self.itens[prod_id]

    def _registrar_log_evento(self, tipo: str, produto_nome: str, quantidade: int, origem: str):
        """Registra no log cronológico para exibição no Dashboard."""
        evento = {
            "timestamp": time.strftime("%H:%M:%S"),
            "tipo": tipo,
            "produto": produto_nome,
            "quantidade": quantidade,
            "origem": origem
        }
        self.historico_eventos.insert(0, evento)
        if len(self.historico_eventos) > 25:
            self.historico_eventos.pop()

    def adicionar_item_manual(self, prod_id: str) -> bool:
        """Adição manual via clique de botão no Dashboard."""
        for key, p in CATALOGO_PRODUTOS.items():
            if p["id"] == prod_id:
                self._aplicar_adicao(p)
                if prod_id in self.rastreamento:
                    self.rastreamento[prod_id]["contagem_atual_confirmada"] = self.itens[prod_id]["quantidade"]
                self._registrar_log_evento("ADICAO", p["nome"], self.itens[prod_id]["quantidade"], "Manual")
                return True
        return False

    def remover_item_manual(self, prod_id: str) -> bool:
        """Remoção manual via clique de botão no Dashboard."""
        if prod_id in self.itens:
            nome = self.itens[prod_id]["nome"]
            self._aplicar_remocao(prod_id)
            qtd_restante = self.itens[prod_id]["quantidade"] if prod_id in self.itens else 0
            if prod_id in self.rastreamento:
                self.rastreamento[prod_id]["contagem_atual_confirmada"] = qtd_restante
            self._registrar_log_evento("REMOCAO", nome, qtd_restante, "Manual")
            return True
        return False

    def limpar_carrinho(self):
        """Esvazia completamente o cesto e zera os rastreadores."""
        self.itens.clear()
        self.rastreamento.clear()
        self.historico_eventos.clear()
        self._registrar_log_evento("SISTEMA", "Cesto Esvaziado", 0, "Reset")

    def obter_resumo(self) -> Dict[str, Any]:
        """Gera resumo estruturado do carrinho para o Dashboard e API REST."""
        itens_lista = list(self.itens.values())
        total_itens = sum(item["quantidade"] for item in itens_lista)
        valor_total = round(sum(item["subtotal"] for item in itens_lista), 2)

        return {
            "itens": itens_lista,
            "total_itens": total_itens,
            "valor_total": valor_total,
            "status_cesto": "MONITORAMENTO_AO_VIVO",
            "eventos_recentes": self.historico_eventos[:12]
        }
