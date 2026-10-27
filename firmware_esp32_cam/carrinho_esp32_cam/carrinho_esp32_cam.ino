/*
 * ==============================================================================
 * SISTEMAS EM TEMPO REAL (STR) - SMARTCART STR
 * Firmware de Borda para ESP32-CAM (Câmera Acoplada ao Cesto do Carrinho)
 * Disciplina: PET2245 - Sistemas em Tempo Real
 * Docente: Prof. Dr. Petrucio Ricardo Tavares de Medeiros
 * Autores: Nattan Ferreira Lopes e Anderson Esmael Da Silva
 * ==============================================================================
 * Arquitetura de Inicialização Limpa e Drenagem Contínua:
 * 1. Wi-Fi e WebSocket conectam primeiro com o sensor inativo (zero FB-OVF).
 * 2. Câmera configurada com buffers em PSRAM (CAMERA_FB_IN_PSRAM) imediatamente antes do loop.
 * 3. O loop() drena os quadros continuamente em tempo real sem bloqueios nem delays.
 * 4. Feedback sonoro duplo:
 *    - PRODUTO_REGISTRADO: 1 BEEP (Item inserido no cesto)
 *    - PRODUTO_REMOVIDO:   2 BEEPS (Item retirado do cesto)
 * ==============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebSocketsClient.h> // WebSockets by Markus Sattler
#include "soc/soc.h"          // Registradores internos
#include "soc/rtc_cntl_reg.h" // Desativação do detector de brownout

// ==============================================================================
// CONFIGURAÇÕES DE REDE E SERVIDOR STR
// ==============================================================================
// Preencha com as credenciais da rede Wi-Fi local:
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";

// Endereço IP e porta do computador host executando o server.py:
const char* WS_SERVER_HOST = "192.168.1.100"; // Substitua pelo IP local do servidor
const int   WS_SERVER_PORT = 8765;
const char* WS_SERVER_PATH = "/ws/camera";

// ==============================================================================
// MAPEAMENTO DE PINOS DO ESP32-CAM (MODELO AI-THINKER)
// ==============================================================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// Periféricos de Feedback
#define FLASH_LED_PIN      4   // Flash LED integrado (GPIO 4)
#define ONBOARD_LED_PIN   33   // LED SMD vermelho integrado (GPIO 33, ativo em LOW)
#define BUZZER_PIN        13   // Buzzer sonoro piezoelétrico (GPIO 13)

// ==============================================================================
// VARIÁVEIS DE CONTROLE DE TEMPO REAL (STR)
// ==============================================================================
WebSocketsClient webSocket;
bool wsConnected = false;

// Período nominal de transmissão: 50 ms (20 FPS)
const unsigned long PERIODO_FRAME_MS = 50;
unsigned long ultimoFrameEnvioMs = 0;
uint32_t sequenciaFrame = 0;

// ==============================================================================
// FUNÇÕES DE FEEDBACK SONORO E VISUAL (BEEPS)
// ==============================================================================
void tocarFeedbackAdicao() {
  // 1 Beep: Confirmação de item adicionado ao cesto
  digitalWrite(ONBOARD_LED_PIN, LOW); // Liga LED
  digitalWrite(BUZZER_PIN, HIGH);
  delay(65);
  digitalWrite(ONBOARD_LED_PIN, HIGH); // Desliga LED
  digitalWrite(BUZZER_PIN, LOW);
}

void tocarFeedbackRemocao() {
  // 2 Beeps: Confirmação de item retirado do cesto
  for (int i = 0; i < 2; i++) {
    digitalWrite(ONBOARD_LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, HIGH);
    delay(45);
    digitalWrite(ONBOARD_LED_PIN, HIGH);
    digitalWrite(BUZZER_PIN, LOW);
    delay(45);
  }
}

// ==============================================================================
// GERENCIADOR DE EVENTOS WEBSOCKET
// ==============================================================================
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("[WS] Desconectado do Servidor STR!");
      wsConnected = false;
      break;

    case WStype_CONNECTED:
      Serial.printf("[WS] CONECTADO ao Servidor STR em %s:%d%s\n", WS_SERVER_HOST, WS_SERVER_PORT, WS_SERVER_PATH);
      wsConnected = true;
      webSocket.sendTXT("{\"tipo\":\"DISPOSITIVO_BORDA\",\"id\":\"ESP32-CESTO-01\"}");
      tocarFeedbackAdicao();
      break;

    case WStype_TEXT:
      Serial.printf("[WS] Evento STR Recebido: %s\n", payload);
      if (strstr((char*)payload, "PRODUTO_REGISTRADO") != NULL || strstr((char*)payload, "REGISTRADO") != NULL) {
        Serial.println("[CESTO] >>> 🔔 ITEM INSERIDO NO CESTO!");
        tocarFeedbackAdicao();
      } else if (strstr((char*)payload, "PRODUTO_REMOVIDO") != NULL || strstr((char*)payload, "REMOVIDO") != NULL) {
        Serial.println("[CESTO] <<< 🔔🔔 ITEM RETIRADO DO CESTO!");
        tocarFeedbackRemocao();
      }
      break;

    case WStype_BIN:
      break;

    default:
      break;
  }
}

// ==============================================================================
// INICIALIZAÇÃO DA CÂMERA OV2640 (BUFFERS EM PSRAM)
// ==============================================================================
bool iniciarCamera() {
  // Limpeza prévia segura de interrupções
  esp_camera_deinit();
  gpio_uninstall_isr_service();
  delay(30);

  // Reset físico no sensor via pino PWDN
  if (PWDN_GPIO_NUM != -1) {
    pinMode(PWDN_GPIO_NUM, OUTPUT);
    digitalWrite(PWDN_GPIO_NUM, HIGH);
    delay(20);
    digitalWrite(PWDN_GPIO_NUM, LOW);
    delay(20);
  }

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  config.xclk_freq_hz = 10000000;       // 10 MHz: Clock estável de captura
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size   = FRAMESIZE_QVGA; // 320x240 nativo para inferência YOLO
  config.grab_mode    = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    Serial.println("[CAMERA] Alocando 2 buffers diretamente na PSRAM (CAMERA_FB_IN_PSRAM)...");
    config.fb_count     = 2;
    config.jpeg_quality = 12;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("[CAMERA] Alocando 1 buffer na DRAM (CAMERA_FB_IN_DRAM)...");
    config.fb_count     = 1;
    config.jpeg_quality = 20;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  Serial.println("[CAMERA] Inicializando sensor OV2640...");
  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("[CAMERA] Falha a 10MHz (0x%x). Tentando a 8MHz...\n", err);
    esp_camera_deinit();
    gpio_uninstall_isr_service();
    delay(50);
    config.xclk_freq_hz = 8000000;
    err = esp_camera_init(&config);
  }

  if (err != ESP_OK) {
    Serial.printf("[CAMERA] Erro fatal na inicializacao: 0x%x\n", err);
    esp_camera_deinit();
    gpio_uninstall_isr_service();
    return false;
  }

  sensor_t * s = esp_camera_sensor_get();
  if (s != NULL) {
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    s->set_saturation(s, 0);
  }

  Serial.println("[CAMERA] Sensor OV2640 calibrado para visao do cesto!");
  return true;
}

// ==============================================================================
// SETUP PRINCIPAL
// ==============================================================================
void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Desativa detector de brownout

  Serial.begin(115200);
  delay(150);

  pinMode(FLASH_LED_PIN, OUTPUT);
  pinMode(ONBOARD_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(FLASH_LED_PIN, LOW);
  digitalWrite(ONBOARD_LED_PIN, HIGH); // HIGH = Desligado
  digitalWrite(BUZZER_PIN, LOW);

  Serial.println("\n========================================================");
  Serial.println("   INICIALIZANDO ESP32-CAM - SMARTCART STR");
  Serial.println("   Monitoramento Automático de Cesto em Tempo Real");
  Serial.println("========================================================");

  if (psramFound()) {
    Serial.printf("[SISTEMA] PSRAM Detectada: %d KB Livres\n", ESP.getFreePsram() / 1024);
  } else {
    Serial.println("[SISTEMA] AVISO: PSRAM nao encontrada.");
  }

  // PASSO 1: CONECTA AO WI-FI PRIMEIRO
  // (Sensor inativo: DMA livre e zero FB-OVF)
  Serial.printf("[WIFI] Conectando a rede \"%s\"", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  WiFi.setSleep(false); // Streaming contínuo sem sleep
  Serial.printf("\n[WIFI] CONECTADO COM SUCESSO! IP: %s (Sinal: %d dBm)\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());

  // PASSO 2: CONFIGURA WEBSOCKET
  Serial.printf("[WS] Conectando ao backend STR em ws://%s:%d%s\n", WS_SERVER_HOST, WS_SERVER_PORT, WS_SERVER_PATH);
  webSocket.begin(WS_SERVER_HOST, WS_SERVER_PORT, WS_SERVER_PATH, "arduino");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(1500);

  // PASSO 3: INICIALIZA CÂMERA IMEDIATAMENTE ANTES DO LOOP
  while (!iniciarCamera()) {
    Serial.println("[CAMERA] Tentando reconectar ao sensor em 2s...");
    delay(2000);
  }

  Serial.println("[SISTEMA] Setup finalizado! Iniciando streaming em tempo real do cesto...");
}

// ==============================================================================
// LOOP PRINCIPAL DE TEMPO REAL (STR)
// ==============================================================================
void loop() {
  // 1. Processa a pilha de rede WebSocket
  webSocket.loop();

  // 2. CAPTURA E DRENAGEM CONTÍNUA DE QUADROS (SEM DELAY, SEM FB-OVF)
  camera_fb_t * fb = esp_camera_fb_get();
  if (fb) {
    unsigned long agoraMs = millis();

    // 3. Transmissão a 20 FPS (T = 50ms)
    if (wsConnected && (WiFi.status() == WL_CONNECTED) && (agoraMs - ultimoFrameEnvioMs >= PERIODO_FRAME_MS)) {
      ultimoFrameEnvioMs = agoraMs;
      bool enviado = webSocket.sendBIN(fb->buf, fb->len);
      if (enviado) {
        sequenciaFrame++;
      }
    }

    // 4. Liberação imediata do buffer
    esp_camera_fb_return(fb);
  }

  yield();
}
