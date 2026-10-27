# 🛒 SmartCart STR — Carrinho de Supermercado Inteligente em Tempo Real

> **Projeto Final de Engenharia / Sistemas em Tempo Real**  
> **Disciplina:** PET2245 – Sistemas em Tempo Real  
> **Docente:** Prof. Dr. Petrucio Ricardo Tavares de Medeiros  
> **Autores / Desenvolvedores:**  
> - **Nattan Ferreira Lopes**  
> - **Anderson Esmael Da Silva**  

---

## 📋 Sumário
1. [Visão Geral do Projeto](#-1-visão-geral-do-projeto)
2. [Fundamentação em Sistemas em Tempo Real (STR)](#-2-fundamentação-em-sistemas-em-tempo-real-str)
3. [Arquitetura do Sistema](#-3-arquitetura-do-sistema)
4. [Mecanismo de Histerese Temporal Anti-Flicker](#-4-mecanismo-de-histerese-temporal-anti-flicker)
5. [Catálogo de Produtos do MVP](#-5-catálogo-de-produtos-do-mvp)
6. [Estrutura de Arquivos](#-6-estrutura-de-arquivos)
7. [Guia de Instalação e Execução](#-7-guia-de-instalação-e-execução)
8. [Configuração do Firmware ESP32-CAM](#-8-configuração-do-firmware-esp32-cam)
9. [Bateria de Testes e Validação Automatizada](#-9-bateria-de-testes-e-validação-automatizada)
10. [Resultados Experimentais de Desempenho STR](#-10-resultados-experimentais-de-desempenho-str)

---

##  1. Visão Geral do Projeto

### Contextualização e Motivação
No varejo presencial contemporâneo (supermercados, atacadistas e lojas de conveniência), o gargalo mais crítico na experiência do consumidor reside no processo de **checkout**. As filas nos caixas tradicionais aumentam o tempo de permanência, sobrecarregam operadores humanos e geram fricção. Paralelamente, leitores manuais de código de barras estão sujeitos a erros operacionais de leitura ou fraudes por esquecimento de itens.

### Solução Proposta: SmartCart STR
O **SmartCart STR** é um sistema distribuído ciberfísico de alta previsibilidade temporal que converte um carrinho de compras comum em uma estação inteligente autônoma. Através de um sensor de visão acoplado diretamente à borda superior do carrinho e direcionado para o interior do cesto, o sistema audita de forma ininterrupta o inventário de compras.

###  Invariante Central: Presença Física no Cesto = Inventário Digital Atualizado
Ao contrário de soluções que exigem intervenção humana ativa (como pressionar botões de "Adicionar" ou "Retirar"), o SmartCart STR atua de maneira 100% autônoma e contínua:
* **Entrada Automática:** No momento em que o consumidor deposita um item dentro do cesto, o produto é capturado pelo sensor de visão, identificado pelo modelo neural e registrado instantaneamente no subtotal da compra. O nó de borda emite **1 BEEP curto** de confirmação.
* **Retirada Automática:** Se o consumidor se arrepende e remove o item do carrinho, a ausência visual permanente do produto é detectada pela máquina de estados, que abate o produto do inventário e decrementa o valor total. O nó de borda emite **2 BEEPS** de confirmação de estorno.
* **Feedback Temporal Imediato:** O consumidor acompanha em tempo real cada item, quantidade, preço unitário, subtotal e métricas de telemetria através do Dashboard Web integrado.

---

##  2. Fundamentação em Sistemas em Tempo Real (STR)

### 2.1. Classificação de Criticidade Temporal
* **Soft Real-Time (na Interação com o Consumidor):** O sistema deve fornecer feedback auditivo e visual dentro de uma janela temporal imperceptível para a dinâmica humana de compras ($D = 3000\text{ ms}$). A eventual perda esporádica de um prazo não acarreta falha catastrófica nem risco à vida, mas degradaria a fluidez perceptiva e a confiança do usuário.
* **Firm Real-Time (na Camada de Ingestão de Quadros de Vídeo):** No pipeline de processamento de imagem, a utilidade de um quadro de vídeo vencido cai imediatamente a zero. O sistema adota a política de descarte *drop-tail* (buffer depth = 1), assegurando que o classificador neural processe sempre o frame mais recente (`CAMERA_GRAB_LATEST`), prevenindo saturação de fila (*bufferbloat*) e acúmulo de atraso em cascata.

### 2.2. Decomposição do Pior Tempo de Execução (WCET)
A latência de ponta a ponta ($T_{\text{total}}$) de cada ciclo do sistema é modelada pela soma do tempo de execução de suas tarefas constituintes:

$$T_{\text{total\_WCET}} = T_{\text{captura}} + T_{\text{envio}} + T_{\text{inferência}} + T_{\text{registro}} + T_{\text{retorno}} \le D$$

| Componente da Tarefa | Notação | Estimativa / Pior Caso | Descrição |
| :--- | :---: | :---: | :--- |
| **Aquisição do Frame** | $\tau_1$ ($T_{\text{captura}}$) | $15{,}0\text{ ms}$ | Amostragem no sensor OV2640 e codificação JPEG via hardware |
| **Transmissão de Rede** | $\tau_2$ ($T_{\text{envio}}$) | $0{,}5 \text{ a } 3{,}0\text{ ms}$ | Segmentação TCP/WebSocket com flag `TCP_NODELAY` ativada |
| **Inferência Neural** | $\tau_3$ ($T_{\text{inferência}}$) | $2{,}0 \text{ a } 20{,}0\text{ ms}$ | Decodificação de imagem, feedforward YOLOv8n e Non-Maximum Suppression |
| **Máquina de Estados** | $\tau_4$ ($T_{\text{registro}}$) | $0{,}1\text{ ms}$ | Verificação de histerese temporal e atualização do inventário |
| **Retorno / Telemetria** | $\tau_5$ ($T_{\text{retorno}}$) | $0{,}2\text{ ms}$ | Transmissão de broadcast para o Dashboard e comando do buzzer |

### 2.3. Admissibilidade Temporal e Slack Time
* **Prazo Limite (Deadline $D$):** $3000\text{ ms}$ (3 segundos).
* **Pior Caso de Execução Medido (WCET):** $\approx 4\text{ a } 50\text{ ms}$ (dependendo do hardware host).
* **Folga Temporal (Slack Time):**
  $$\text{Slack Time} = D - \text{WCET} = 3000\text{ ms} - 50\text{ ms} = 2950\text{ ms} \quad (\approx 98{,}3\% \text{ de margem})$$
* **Fator de Utilização Temporal ($U$):**
  $$U = \frac{\text{WCET}}{D} \times 100\% < 2\%$$
Garante estabilidade absoluta e $0\%$ de violações de deadline, absorvendo com folga oscilações de radiofrequência da rede Wi-Fi local.

---

##  3. Arquitetura do Sistema

O sistema adota uma arquitetura distribuída cliente-servidor orientada a eventos assíncronos e streaming contínuo sobre WebSockets:

```mermaid
flowchart TD
    subgraph Borda ["Borda Física (No Embarcado - ESP32-CAM)"]
        A[Sensor OV2640 / Borda do Cesto] -->|Captura QVGA / JPEG| B[Buffer Duplo em PSRAM]
        B -->|Drenagem CAMERA_GRAB_LATEST| C[Cliente WebSocket TCP_NODELAY]
        H[Buzzer Piezoeletrico GPIO 13] <--|1 Beep Adicao / 2 Beeps Remocao| C
    end

    subgraph Rede ["Canal de Transporte Local"]
        C -->|Frames Binarios JPEG ~50KB| D[Canal WebSocket /ws/camera]
        D -->|ACKs e Comandos Sonoros| C
    end

    subgraph Servidor ["Servidor Central STR (Python Backend)"]
        D --> E[Recepcao Assincrona - server.py]
        E --> F[Pipeline Visao YOLOv8n / NMS]
        F --> G[Gerenciador de Cesto com Histerese]
        G --> I[Modulo Telemetria STR Monotonica]
        I --> J[Broadcaster WebSocket /ws/dashboard]
    end

    subgraph Dashboard ["Interface Homem-Maquina (Frontend)"]
        J --> K[Dashboard Web / Canvas STR]
        K -->|Exibicao em Tempo Real| L[Stream de Video, HUD, Tabela de Carrinho e Grafico de Latencia]
    end
```

### Componentes Principais:
1. **Nó de Borda (ESP32-CAM AI-Thinker):**
   - Microcontrolador ESP32 Dual-Core @ 240MHz com 4MB de PSRAM externa.
   - Sensor de imagem OV2640 operando em resolução QVGA ($320 \times 240$) com taxa de amostragem nominal de 20 FPS ($T = 50\text{ ms}$).
   - Inicialização com sensor inativo até o handshake de rede estar consolidado, prevenindo *Frame-Buffer Overflow* (`FB-OVF`).
   - Buzzer piezoelétrico conectado ao GPIO 13 com sinalização sonora diferenciada.
2. **Canal de Comunicação (WebSocket sobre TCP):**
   - Transmissão ponto a ponto em conformidade com a RFC 6455.
   - Flag de socket `TCP_NODELAY` ativada, desativando o algoritmo de Nagle para despacho instantâneo dos frames sem agrupamento de pacotes.
3. **Servidor Central de Inferência e Lógica:**
   - Loop de eventos assíncrono em `asyncio` e servidor HTTP/WS unificado na porta 8765.
   - Modelo de visão computacional YOLOv8n com aquecimento prévio (*warm-up*) para evitar atrasos na primeira inferência.
   - Algoritmo de supressão de não-máximos (NMS) com limiar IoU = 0.40 para evitar contagens duplicadas de um mesmo objeto no cesto.
4. **Instrumentação e Telemetria de Tempo Real:**
   - Relógio monotônico de alta resolução (`time.perf_counter_ns`).
   - Medições ao vivo de latência média, desvio padrão, pior caso (WCET), jitter instantâneo, jitter médio, slack time e contagem de violações.
5. **Dashboard Web Interativo:**
   - Interface com tema escuro (Dark Glassmorphism) responsivo.
   - Gráfico dinâmico em HTML5 Canvas comparando a latência de cada frame contra a linha vermelha do deadline ($D = 3000\text{ ms}$).
   - Web Audio API para reprodução dos beeps sincronizados diretamente no navegador.

---

##  4. Mecanismo de Histerese Temporal Anti-Flicker

Em sistemas de visão contínua aplicados a cestos de compras, oscilações rápidas de iluminação ou a passagem passageira da mão do cliente sobre um produto poderiam gerar oclusões momentâneas (falsas retiradas seguidas de falsas adições).

Para garantir **estabilidade determinística**, o módulo `cart_manager.py` implementa dois limiares temporais de histerese:

```
[Produto Detectado pela 1ª vez] 
             │
             ▼
   Frame 1: Pendente (Histerese de Entrada)
             │
             ▼ (Detectado novamente no próximo frame ~100ms)
   Frame 2: CONFIRMADO NO CARRINHO (Emite 1 BEEP)
             │
   ============================== [ PRODUTO NO CESTO ]
             │
   (Mão do usuário oclui o item ou ruído pontual de 1-2 quadros)
             │
             ▼
   Ausência transitória (< 1.2s): ITEM MANTIDO NO CARRINHO (Sem oscilação)
             │
             ▼ (Ausência contínua ultrapassa ABSENCE_TIMEOUT_SEC = 1.2s)
   CONFIRMADA A RETIRADA DO PRODUTO (Subtotal decrementado, Emite 2 BEEPS)
```

1. **Janela de Confirmação de Entrada (`PRESENCE_CONFIRM_FRAMES = 2`):**
   Exige que o produto seja detectado por pelo menos 2 quadros consecutivos antes de ser contabilizado, descartando reflexos ou falsos positivos breves.
2. **Tolerância de Ausência Contínua (`ABSENCE_TIMEOUT_SEC = 1.2 s`):**
   Se o produto sumir do campo de visão por intervalos menores que 1.2 segundos, ele permanece intacto no carrinho, absorvendo oclusões normais de manuseio.

---

##  5. Catálogo de Produtos do MVP

O sistema utiliza classes nativas pré-treinadas da arquitetura YOLOv8n (Dataset COCO), dispensando treinamento adicional e garantindo alta capacidade de generalização:

| Código | Produto | Classe COCO (ID) | Preço Unitário | Sinalização Sonora |
| :---: | :--- | :---: | :---: | :---: |
| `PROD-001` | **Garrafa de Água Mineral 500ml** | `bottle` (ID 39) | R$ 3,50 | 1 Beep na entrada / 2 Beeps na saída |
| `PROD-002` | **Copo / Caneca de Vidro** | `cup` / `wine glass` (IDs 41, 40) | R$ 15,00 | 1 Beep na entrada / 2 Beeps na saída |
| `PROD-003` | **Smartphone Galaxy / iPhone** | `cell phone` (ID 67) | R$ 1.250,00 | 1 Beep na entrada / 2 Beeps na saída |

---

##  6. Estrutura de Arquivos

```plaintext
smartcart-str/
├── config.py                 # Parâmetros de STR, rede, histerese e catálogo de produtos
├── cart_manager.py           # Máquina de estados do cesto com histerese temporal e inventário
├── vision_pipeline.py        # Pipeline de Visão Computacional com YOLOv8n e NMS
├── server.py                 # Servidor Central HTTP e WebSocket (/ws/camera e /ws/dashboard)
├── camera_pc_client.py       # Emulador interativo de visão do cesto via Webcam / Câmera Virtual
├── telemetry_str.py          # Instrumentação de tempo real de alta precisão (ns)
├── benchmark_str.py          # Script de medição estatística de latência, jitter e WCET
├── test_add_remove_flow.py   # Teste unitário da histerese de entrada, permanência e saída
├── test_system.py            # Teste automatizado de integração ponta a ponta
├── avaliacao.txt             # Relatório técnico formal de respostas da disciplina STR
├── yolov8n.pt                # Pesos neurais pré-treinados do modelo YOLOv8n
├── static/                   # Frontend do Dashboard Web
│   ├── index.html            # Estrutura visual, identificação acadêmica, vídeo e HUD
│   ├── app.js                # Lógica WebSocket, gráfico de latência e áudio Web Audio API
│   └── style.css             # Tema escuro moderno com glassmorphism e badges acadêmicas
└── firmware_esp32_cam/       # Código-fonte e documentação para o microcontrolador
    ├── README_ESP32.md       # Guia de ligação e gravação do nó embarcado
    └── carrinho_esp32_cam/
        └── carrinho_esp32_cam.ino # Firmware C++ para Arduino IDE (AI-Thinker ESP32-CAM)
```

---

## 7. Guia de Instalação e Execução

### 7.1. Pré-requisitos
* Sistema Operacional: Linux (Fedora, Ubuntu, Debian), macOS ou Windows.
* Python: versão 3.10 ou superior.
* Arduino IDE (caso vá gravar o firmware no módulo físico ESP32-CAM).

### 7.2. Configuração do Ambiente Python
Recomenda-se a criação de um ambiente virtual para o isolamento dos pacotes:

```bash
# 1. Navegue até o diretório raiz do projeto
cd /caminho/do/projeto/smartcart-str  # Ou sua pasta clonada localmente

# 2. Crie e ative o ambiente virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instale as dependências requeridas
pip install websockets opencv-python numpy ultralytics torch
```

---

### 7.3. Passo 1: Iniciar o Servidor Central STR
Em um terminal dedicado, execute:
```bash
python3 server.py
```
O servidor inicializará exibindo o banner formal da disciplina:
```text
======================================================================
  SMARTCART STR - SISTEMA DE CARRINHO INTELIGENTE EM TEMPO REAL
  Disciplina: PET2245 - Sistemas em Tempo Real
  Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
  Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva
======================================================================
  Monitoramento Automático de Cesto por Visão Computacional de Borda
[STR] Servidor Unificado rodando em http://0.0.0.0:8765
[STR] Endpoint Câmera ESP32-CAM: ws://0.0.0.0:8765/ws/camera
[STR] Endpoint Dashboard Web:    ws://0.0.0.0:8765/ws/dashboard
[STR] Requisito Deadline:        D = 3000.0 ms
======================================================================
```

---

### 7.4. Passo 2: Acessar o Dashboard Web
Abra o navegador de sua preferência no endereço:
```
http://localhost:8765
```
Você verá o Dashboard com as informações formais da disciplina (PET2245, Prof. Dr. Petrucio Ricardo Tavares de Medeiros, Nattan Ferreira Lopes e Anderson Esmael Da Silva), os cards de telemetria STR, o monitor de vídeo e a tabela do carrinho.

---

### 7.5. Passo 3: Conectar a Fonte de Vídeo

Você pode alimentar o sistema com o **nó físico ESP32-CAM** ou com o **emulador/cliente de PC**:

#### Opção A: Executar com o Emulador / Câmera de PC
Em um segundo terminal, execute:
```bash
python3 camera_pc_client.py
```
*(Se preferir forçar a geração de imagens virtuais sem acessar webcam, adicione `--virtual`)*.

Uma janela de visualização do cesto será aberta. Utilize o teclado interativo:
* Pressione `[1]`: Coloca / Retira a **Garrafa de Água** no cesto.
* Pressione `[2]`: Coloca / Retira o **Copo de Vidro** no cesto.
* Pressione `[3]`: Coloca **ambos** os produtos no cesto simultaneamente.
* Pressione `[0]`: Esvazia completamente o cesto.
* Pressione `[Q]`: Encerra o emulador.

Observe no Dashboard o gráfico de latência traçado em tempo real bem abaixo da linha vermelha do deadline ($D = 3000\text{ ms}$), e o som de confirmação sendo emitido.

#### Opção B: Executar com o ESP32-CAM Físico
Siga as instruções da seção seguinte para compilar e gravar a placa.

---

##  8. Configuração do Firmware ESP32-CAM

Para utilizar a placa microcontrolada acoplada ao carrinho físico:

1. Abra o arquivo `firmware_esp32_cam/carrinho_esp32_cam/carrinho_esp32_cam.ino` na **Arduino IDE**.
2. Defina os parâmetros da sua rede local nas linhas 28-34:
   ```cpp
   // Preencha com os dados do seu roteador Wi-Fi:
   const char* WIFI_SSID     = "SUA_REDE_WIFI";
   const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";

   // Endereço IP do computador onde o server.py está rodando:
   const char* WS_SERVER_HOST = "192.168.1.100"; // Obtenha via `hostname -I` no terminal
   const int   WS_SERVER_PORT = 8765;
   const char* WS_SERVER_PATH = "/ws/camera";
   ```
3. Na Arduino IDE, configure os parâmetros em **Ferramentas**:
   * **Placa:** `AI Thinker ESP32-CAM`
   * **PSRAM:** `Enabled` (indispensável para os buffers de imagem)
   * **CPU Frequency:** `240MHz (WiFi/BT)`
   * **Upload Speed:** `115200` ou `921600`
4. Conecte o pino `GPIO 0` ao `GND` para entrar no modo bootloader, faça o upload e, ao finalizar, remova a ponte e pressione o botão **RST**.

---

##  9. Bateria de Testes e Validação Automatizada

O projeto conta com uma suíte de testes automatizados para comprovar a conformidade funcional e temporal:

### 1. Teste de Histerese Temporal e Fluxo do Cesto
Valida os estados transitórios, a janela anti-ruído na entrada, a imunidade contra oclusões momentâneas da mão do consumidor e o estorno automático na saída:
```bash
python3 test_add_remove_flow.py
```
*Resultado esperado:* Todos os 9 passos aprovados com 100% de sucesso.

### 2. Benchmark de Desempenho STR (Latência, Jitter e WCET)
Com o `server.py` em execução, execute em outro terminal:
```bash
python3 benchmark_str.py
```
O benchmark transmite uma rajada de 100 quadros pela esteira WebSocket e gera a análise estatística de pior caso (WCET) contra o deadline de 3000 ms.

### 3. Teste de Integração Ponta a Ponta
Simula a comunicação completa entre Câmera, Servidor e Dashboard Web:
```bash
python3 test_system.py
```

---

##  10. Resultados Experimentais de Desempenho STR

Os ensaios empíricos de tempo real foram coletados por instrumentação monotônica de nanossegundos (`telemetry_str.py` / `benchmark_str.py`):

| Métrica de Desempenho | Valor Medido | Especificação de Projeto | Status de Conformidade |
| :--- | :---: | :---: | :---: |
| **Latência Média ($L_{\text{média}}$)** | **1,74 ms** | $< 100{,}0\text{ ms}$ | ✅ Excelente |
| **Pior Caso de Execução (WCET)** | **4,01 ms** | $\le 3000{,}0\text{ ms}$ | ✅ Aprovado com folga |
| **Jitter Médio ($J_{\text{médio}}$)** | **0,15 ms** | $< 15{,}0\text{ ms}$ | ✅ Altamente Determinístico |
| **Desvio Padrão do Jitter** | **0,22 ms** | $< 5{,}0\text{ ms}$ | ✅ Estabilidade Estrita |
| **Folga Temporal (Slack Time)** | **2995,99 ms** | $> 2500{,}0\text{ ms}$ | ✅ Margem $> 99{,}8\%$ |
| **Taxa de Violações de Deadline** | **0,00% (0 / 500)** | $0{,}00\%$ | ✅ Zero Violações |

Os resultados comprovam que a arquitetura do **SmartCart STR** atende com rigor às exigências de sistemas em tempo real para automação ciberfísica de varejo.

---

>  
> *Relatório e projeto submetidos para avaliação na disciplina PET2245 pelo Prof. Dr. Petrucio Ricardo Tavares de Medeiros.*
