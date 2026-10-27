# Guia de Configuração e Gravação: ESP32-CAM (AI-Thinker)
> **SmartCart STR - Carrinho de Supermercado Inteligente em Tempo Real**  
> Disciplina: PET2245 - Sistemas em Tempo Real  
> Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros  
> Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva  

Este documento descreve os passos para compilar e carregar o firmware de monitoramento contínuo do carrinho inteligente no nó embarcado **ESP32-CAM**.

---

## 1. Requisitos de Hardware
- Módulo **ESP32-CAM AI-Thinker** (com sensor OV2640).
- Módulo Conversor USB-Serial FTDI (3.3V/5V) ou placa adaptadora ESP32-CAM MB.
- Fonte de alimentação estável de 5V (corrente recomendada: 1A a 2A para estabilidade de Wi-Fi e RF).
- Jumpers fêmea-fêmea.
- *(Opcional)* Buzzer piezoelétrico de 5V/3.3V no **GPIO 13**.
- *(Opcional)* Push-button táctil conectado entre o **GPIO 12** e o **GND** (para alternar fisicamente entre Modo Adicionar e Modo Retirar).

---

## 2. Diagrama de Ligação para Gravação (Modo Flash)

| Pino do FTDI (USB-Serial) | Pino do ESP32-CAM |
| :--- | :--- |
| **VCC (5V recomendado)** | **5V** (ou **3V3** se o FTDI tiver saída 3.3V potente) |
| **GND** | **GND** |
| **TX** | **U0R (GPIO 3)** |
| **RX** | **U0T (GPIO 1)** |
| — | **GPIO 0 conectado ao GND** *(Apenas durante o upload!)* |

> [!IMPORTANT]
> 1. O jumper entre **GPIO 0** e **GND** coloca o ESP32 em modo de gravação (Bootloader).
> 2. Pressione o botão **RESET** do ESP32 antes de clicar em Upload na Arduino IDE.
> 3. Após o término do upload, **remova o jumper entre GPIO 0 e GND** e pressione **RESET** novamente para iniciar a execução normal.

---

## 3. Configurações na Arduino IDE

1. **URL de Placas Adicionais (Arquivo > Preferências):**
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. **Placa Selecionada (Ferramentas > Placa > ESP32 Arduino):** `AI Thinker ESP32-CAM`
3. **Parâmetros da Placa em Ferramentas:**
   - **PSRAM:** `Enabled` (ou Ativado) — *Essencial para alocação dos buffers DMA da câmera*
   - **CPU Frequency:** `240MHz (WiFi/BT)`
   - **Flash Frequency:** `80MHz`
   - **Flash Mode:** `QIO`
   - **Partition Scheme:** `Huge APP (3MB No OTA/1MB SPIFFS)`
   - **Core Debug Level:** `None` (ou `Info` para depuração)
   - **Upload Speed:** `115200` ou `921600`
4. **Bibliotecas Necessárias (Gerenciador de Bibliotecas):**
   - `WebSockets` por *Markus Sattler* (versão >= 2.3.6)

---

## 4. Ajustes no Arquivo `carrinho_esp32_cam.ino`

Abra o arquivo e altere as credenciais Wi-Fi e o endereço IP do seu computador na rede local:
```cpp
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";
const char* WS_SERVER_HOST = "192.168.1.100"; // IP da máquina executando server.py (verifique via `hostname -I` no Linux)
const int   WS_SERVER_PORT = 8765;
```

> [!TIP]
> Para descobrir o endereço IP do seu computador no Linux execute no terminal:
> ```bash
> hostname -I | awk '{print $1}'
> ```

---

## 5. Melhorias e Proteções Implementadas no Firmware

* **Proteção contra Brownout:** Desativa o detector de subtensão no boot (`RTC_CNTL_BROWN_OUT_REG`) para evitar loops infinitos de reinicialização quando alimentado via USB/FTDI.
* **Reset de Hardware do Sensor OV2640:** Pulso no pino PWDN (GPIO 32) antes de inicializar para garantir que o sensor saia de estados travados após reset.
* **Fallback Automático de Clock (XCLK):** Tenta operar em $20\text{ MHz}$, e se houver ruído no barramento I2C/SCCB, faz fallback automático para $10\text{ MHz}$ ou $16\text{ MHz}$.
* **Streaming de Baixa Latência:** Configurado com `CAMERA_GRAB_LATEST` e resolução QVGA ($320 \times 240$), prevenindo bufferbloat e mantendo o fluxo sincronizado com o pipeline YOLO ($T = 50\text{ ms}$, 20 FPS).
* **LED Onboard Seguro (GPIO 33):** Sinalização de boot e status utilizando o LED vermelho SMD de baixo consumo, reservando o Flash de alta potência (GPIO 4) para evitar quedas abruptas de corrente.
* **Auto-Reconexão Wi-Fi e WebSocket:** Se o sinal Wi-Fi oscilar, a borda restabelece a conexão sem necessidade de reinicializar a placa.
* **Protocolo WebSocket Compatibilizado:** Eliminação do subprotocolo mandatório incompatível, garantindo handshake direto e estável com o `server.py`.

---

## 6. Diagnóstico e Verificação no Monitor Serial

Abra o Monitor Serial na Arduino IDE a **115200 baud**. A saída esperada deve ser:

```text
========================================================
   INICIALIZANDO ESP32-CAM - SMARTCART STR
========================================================
[CAMERA] PSRAM detectada! Alocando buffers duplos na PSRAM.
[CAMERA] Sensor OV2640 inicializado e calibrado com sucesso!
[WIFI] Conectando a MinhaRede.....
[WIFI] CONECTADO COM SUCESSO!
[WIFI] Endereco IP do ESP32-CAM: 192.168.1.50
[WS] Configurando conexao para ws://192.168.1.100:8765/ws/camera
[WS] CONECTADO ao Servidor STR em 192.168.1.100:8765/ws/camera
```

Se o sensor não for detectado na primeira tentativa, o firmware agora repete a inicialização a cada 2 segundos exibindo o código de erro para facilitar a checagem do cabo flat do sensor OV2640.
