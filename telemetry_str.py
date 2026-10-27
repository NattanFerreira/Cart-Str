"""
Módulo de Telemetria e Instrumentação de Tempo Real (STR) - SmartCart STR
Disciplina: PET2245 - Sistemas em Tempo Real
Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva

Mede com precisão monotônica de nanossegundos: Latência E2E, Jitter, WCET,
Desvio Padrão, Taxa de Violações de Deadline (< 3000ms) e Taxa de Quadros (FPS).
"""

import time
import math
from collections import deque
from typing import Dict, Any, List

class TelemetriaSTR:
    def __init__(self, deadline_ms: float = 3000.0, historico_max: int = 100):
        self.deadline_ms = deadline_ms
        self.historico_max = historico_max

        # Histórico de latências e jitters (em ms)
        self.latencias: deque = deque(maxlen=historico_max)
        self.jitters: deque = deque(maxlen=historico_max)

        # Métricas acumuladas globais
        self.total_amostras: int = 0
        self.soma_latencias: float = 0.0
        self.soma_latencias_quad: float = 0.0
        self.latencia_min: float = float('inf')
        self.latencia_wcet: float = 0.0  # Pior Caso de Execução (Worst-Case Execution Time)

        self.soma_jitters: float = 0.0
        self.soma_jitters_quad: float = 0.0
        self.jitter_min: float = float('inf')
        self.jitter_max: float = 0.0

        self.violacoes_deadline: int = 0

        # Rastreamento de FPS
        self.ultimo_timestamp_quadro_ns: int = 0
        self.fps_instantaneo: float = 0.0

        # Última latência para cálculo de jitter (|L_i - L_{i-1}|)
        self.ultima_latencia_ms: float = 0.0

    def registrar_amostra(self, t_inicio_ns: int, t_fim_ns: int) -> Dict[str, Any]:
        """
        Registra uma amostra de latência medida com timers monotônicos de alta precisão.
        """
        agora_ns = t_fim_ns
        latencia_ms = (t_fim_ns - t_inicio_ns) / 1_000_000.0

        # FPS
        if self.ultimo_timestamp_quadro_ns > 0:
            delta_quadro_s = (agora_ns - self.ultimo_timestamp_quadro_ns) / 1_000_000_000.0
            if delta_quadro_s > 0:
                self.fps_instantaneo = 1.0 / delta_quadro_s
        self.ultimo_timestamp_quadro_ns = agora_ns

        # Jitter
        if self.total_amostras > 0:
            jitter_ms = abs(latencia_ms - self.ultima_latencia_ms)
        else:
            jitter_ms = 0.0
        self.ultima_latencia_ms = latencia_ms

        # Atualizações acumuladas de Latência
        self.total_amostras += 1
        self.latencias.append(latencia_ms)
        self.soma_latencias += latencia_ms
        self.soma_latencias_quad += (latencia_ms ** 2)

        if latencia_ms < self.latencia_min:
            self.latencia_min = latencia_ms
        if latencia_ms > self.latencia_wcet:
            self.latencia_wcet = latencia_ms

        if latencia_ms > self.deadline_ms:
            self.violacoes_deadline += 1

        # Atualizações acumuladas de Jitter
        if self.total_amostras > 1:
            self.jitters.append(jitter_ms)
            self.soma_jitters += jitter_ms
            self.soma_jitters_quad += (jitter_ms ** 2)
            if jitter_ms < self.jitter_min:
                self.jitter_min = jitter_ms
            if jitter_ms > self.jitter_max:
                self.jitter_max = jitter_ms

        return self.obter_metricas_atuais(latencia_ms, jitter_ms)

    def obter_metricas_atuais(self, latencia_atual_ms: float = 0.0, jitter_atual_ms: float = 0.0) -> Dict[str, Any]:
        """
        Calcula média e desvio padrão acumulados e retorna resumo estruturado.
        """
        n = self.total_amostras
        if n == 0:
            return {
                "total_amostras": 0,
                "fps": 0.0,
                "deadline_ms": self.deadline_ms,
                "latencia": {"atual": 0.0, "media": 0.0, "desvio": 0.0, "min": 0.0, "wcet": 0.0},
                "jitter": {"atual": 0.0, "media": 0.0, "desvio": 0.0, "min": 0.0, "max": 0.0},
                "violacoes": 0,
                "taxa_violacao_pct": 0.0,
                "slack_time_ms": self.deadline_ms,
                "historico_latencia": []
            }

        lat_media = self.soma_latencias / n
        var_lat = max(0.0, (self.soma_latencias_quad / n) - (lat_media ** 2))
        lat_desvio = math.sqrt(var_lat)

        if n > 1:
            m = n - 1
            jit_media = self.soma_jitters / m
            var_jit = max(0.0, (self.soma_jitters_quad / m) - (jit_media ** 2))
            jit_desvio = math.sqrt(var_jit)
            jit_min = self.jitter_min
            jit_max = self.jitter_max
        else:
            jit_media = jitter_atual_ms
            jit_desvio = 0.0
            jit_min = 0.0
            jit_max = 0.0

        taxa_violacao = (self.violacoes_deadline / n) * 100.0
        lat_recente = latencia_atual_ms if latencia_atual_ms > 0 else (self.latencias[-1] if self.latencias else 0.0)
        jit_recente = jitter_atual_ms if jitter_atual_ms > 0 else (self.jitters[-1] if self.jitters else 0.0)
        slack_time = max(0.0, self.deadline_ms - lat_recente)

        return {
            "total_amostras": n,
            "fps": round(self.fps_instantaneo, 1),
            "deadline_ms": self.deadline_ms,
            "latencia": {
                "atual": round(lat_recente, 2),
                "media": round(lat_media, 2),
                "desvio": round(lat_desvio, 2),
                "min": round(self.latencia_min if self.latencia_min != float('inf') else 0.0, 2),
                "wcet": round(self.latencia_wcet, 2)
            },
            "jitter": {
                "atual": round(jit_recente, 2),
                "media": round(jit_media, 2),
                "desvio": round(jit_desvio, 2),
                "min": round(jit_min if jit_min != float('inf') else 0.0, 2),
                "max": round(jit_max, 2)
            },
            "violacoes": self.violacoes_deadline,
            "taxa_violacao_pct": round(taxa_violacao, 2),
            "slack_time_ms": round(slack_time, 2),
            "historico_latencia": list(self.latencias)
        }
