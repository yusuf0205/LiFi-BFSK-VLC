// tx_esp32.ino - Li-Fi BFSK transmitter (Arduino-ESP32 core 3.x)
//
// Reads text from Serial, frames it (preamble 0xAA x4, sync, length, payload,
// CRC-16-CCITT, optional Hamming(7,4)) and sends it as BFSK on an LED:
//   bit 0 -> f0 square tone, bit 1 -> f1 square tone, 50 % duty.
// LED_PIN drives the gate of a logic-level N-MOSFET (low side) that switches
// the LED string; see README for the driver circuit.
//
// Two modulator back-ends (switch at runtime with "!mode dds" / "!mode ledc"):
//   MODE_DDS  (default) continuous-phase FSK: a hardware timer ISR runs a
//             32-bit phase accumulator at TICK_HZ and writes its MSB to the
//             pin. Tone changes happen without phase jumps and the bit clock
//             is a second accumulator, so any f0/f1/bit-rate combination works.
//   MODE_LEDC uses the LEDC PWM peripheral as the tone generator
//             (ledcChangeFrequency at every bit boundary, paced by esp_timer).
//             The new frequency takes effect at the next PWM period, so the
//             switch is close to phase continuous but jitters a little.
//
// Serial commands (115200 baud, newline terminated):
//   any text line          -> sent as one or more frames (<=255 bytes each)
//   !hex <hexbytes>        -> send a binary frame (used by tools/ for files)
//   !f0 <Hz> / !f1 <Hz>    -> set tone frequencies
//   !rate <bps>            -> set bit rate
//   !mode dds|ledc         -> choose modulator
//   !fec on|off            -> Hamming(7,4) coding of LEN/PAYLOAD/CRC
//   !idle mark|off|on      -> what the LED does between frames
//   !bert <n> [gap_ms]     -> send n PRBS9 test frames for BER measurement
//   !info                  -> print settings
#include <Arduino.h>
#include "esp_timer.h"
#include "hal/gpio_ll.h"
#include "soc/gpio_struct.h"
#include "lifi_proto.h"

// ------------------------------------------------------------ configuration
#define LED_PIN 25               // -> 100 R -> MOSFET gate (10k gate pull-down)
#define STATUS_LED_PIN 2         // on-board LED: on while a frame is being sent
#define DEFAULT_F0 10000UL       // Hz, bit 0
#define DEFAULT_F1 15000UL       // Hz, bit 1
#define DEFAULT_RATE 1000UL      // bit/s
#define TICK_HZ 160000UL         // DDS update rate (80 MHz / 500); >= 8 x f1 recommended
#define TIMER_COUNTER_HZ 8000000UL
#define LEDC_RES_BITS 8          // 8 bit -> duty 128 = 50 %
#define IDLE_GAP_BITS 16         // idle bits sent before each frame
#define SERIAL_BAUD 115200

enum { MODE_DDS = 0, MODE_LEDC = 1 };
enum { IDLE_MARK = 0, IDLE_OFF = 1, IDLE_ON = 2 };

static uint32_t g_f0 = DEFAULT_F0, g_f1 = DEFAULT_F1, g_rate = DEFAULT_RATE;
static uint8_t g_mode = MODE_DDS, g_fec = 0;
static volatile uint8_t g_idle = IDLE_MARK;
static uint32_t g_frames_sent = 0;

// ------------------------------------------------------------ bit FIFO (loop -> ISR)
#define BITQ_SIZE 8192           // bits, power of two
static uint8_t s_bitq[BITQ_SIZE / 8];
static volatile uint32_t s_q_head = 0, s_q_tail = 0;  // head written by loop, tail by ISR

static inline uint32_t bitq_count() { return s_q_head - s_q_tail; }

static bool bitq_push(uint8_t bit) {
  if (bitq_count() >= BITQ_SIZE) return false;
  uint32_t i = s_q_head & (BITQ_SIZE - 1);
  if (bit) s_bitq[i >> 3] |= (uint8_t)(1u << (i & 7));
  else s_bitq[i >> 3] &= (uint8_t)~(1u << (i & 7));
  __sync_synchronize();
  s_q_head = s_q_head + 1;
  return true;
}

// ------------------------------------------------------------ DDS modulator (timer ISR)
static hw_timer_t *s_timer = nullptr;
static volatile uint32_t s_acc = 0, s_inc = 0, s_inc0 = 0, s_inc1 = 0;
static volatile uint32_t s_bit_acc = 0, s_bit_inc = 0;
static volatile uint8_t s_dds_silent = 0, s_dds_silent_level = 0;
static volatile uint8_t s_busy = 0;

static void ARDUINO_ISR_ATTR onDdsTick() {
  uint32_t a = s_acc + s_inc;
  s_acc = a;
  if (s_dds_silent) gpio_ll_set_level(&GPIO, LED_PIN, s_dds_silent_level);
  else gpio_ll_set_level(&GPIO, LED_PIN, a >> 31);
  uint32_t b = s_bit_acc + s_bit_inc;
  if (b < s_bit_acc) {  // bit clock wrapped: start next bit (phase is kept)
    if (s_q_head != s_q_tail) {
      uint32_t i = s_q_tail & (BITQ_SIZE - 1);
      uint8_t bit = (s_bitq[i >> 3] >> (i & 7)) & 1;
      s_q_tail = s_q_tail + 1;
      s_inc = bit ? s_inc1 : s_inc0;
      s_dds_silent = 0;
      s_busy = 1;
    } else {
      s_busy = 0;
      if (g_idle == IDLE_MARK) { s_inc = s_inc1; s_dds_silent = 0; }
      else { s_dds_silent = 1; s_dds_silent_level = (g_idle == IDLE_ON); }
    }
  }
  s_bit_acc = b;
}

static float s_tick_actual = TICK_HZ;

static void dds_set_freqs() {
  // phase increment = f / tick * 2^32
  s_inc0 = (uint32_t)((double)g_f0 / s_tick_actual * 4294967296.0);
  s_inc1 = (uint32_t)((double)g_f1 / s_tick_actual * 4294967296.0);
  s_bit_inc = (uint32_t)((double)g_rate / s_tick_actual * 4294967296.0);
}

static void dds_start() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  uint32_t alarm = (TIMER_COUNTER_HZ + TICK_HZ / 2) / TICK_HZ;
  s_tick_actual = (float)TIMER_COUNTER_HZ / (float)alarm;
  dds_set_freqs();
  s_inc = s_inc1;
  s_timer = timerBegin(TIMER_COUNTER_HZ);
  if (!s_timer) { Serial.println("#ERR timerBegin failed"); return; }
  timerAttachInterrupt(s_timer, &onDdsTick);
  timerAlarm(s_timer, alarm, true, 0);
}

static void dds_stop() {
  if (s_timer) { timerEnd(s_timer); s_timer = nullptr; }
  digitalWrite(LED_PIN, LOW);
}

// ------------------------------------------------------------ LEDC modulator (blocking)
static void ledc_idle() {
  if (g_idle == IDLE_MARK) { ledcChangeFrequency(LED_PIN, g_f1, LEDC_RES_BITS); ledcWrite(LED_PIN, 1u << (LEDC_RES_BITS - 1)); }
  else ledcWrite(LED_PIN, g_idle == IDLE_ON ? (1u << LEDC_RES_BITS) - 1 : 0);
}

static void ledc_start() {
  ledcAttach(LED_PIN, g_f1, LEDC_RES_BITS);
  ledc_idle();
}

static void ledc_stop() { ledcDetach(LED_PIN); }

static void ledc_send_bits(lifi_txf_t *f) {
  const uint32_t half = 1u << (LEDC_RES_BITS - 1);
  const double tb = 1e6 / (double)g_rate;  // microseconds per bit
  int last = -1;
  int64_t t0 = esp_timer_get_time();
  ledcWrite(LED_PIN, half);
  uint32_t k = 0;
  for (uint32_t i = 0; i < IDLE_GAP_BITS; i++) {  // leading idle (mark) bits
    ledcChangeFrequency(LED_PIN, g_f1, LEDC_RES_BITS);
    last = 1;
    while (esp_timer_get_time() - t0 < (int64_t)(tb * (++k))) { }
  }
  int b;
  while ((b = lifi_txf_next(f)) >= 0) {
    if (b != last) { ledcChangeFrequency(LED_PIN, b ? g_f1 : g_f0, LEDC_RES_BITS); last = b; }
    while (esp_timer_get_time() - t0 < (int64_t)(tb * (++k))) { }
  }
  ledc_idle();
}

// ------------------------------------------------------------ frame sending
static void send_frame(const uint8_t *p, uint8_t len) {
  lifi_txf_t f;
  lifi_txf_begin(&f, p, len, g_fec);
  digitalWrite(STATUS_LED_PIN, HIGH);
  if (g_mode == MODE_LEDC) {
    ledc_send_bits(&f);
  } else {
    for (uint32_t i = 0; i < IDLE_GAP_BITS; i++) { while (!bitq_push(1)) delay(1); }
    int b;
    while ((b = lifi_txf_next(&f)) >= 0) { while (!bitq_push((uint8_t)b)) delay(1); }
    while (bitq_count() > 0 || s_busy) delay(1);  // wait until on air
  }
  digitalWrite(STATUS_LED_PIN, LOW);
  g_frames_sent++;
}

static void send_buffer(const uint8_t *p, size_t n) {
  while (n > 0) {
    uint8_t chunk = (uint8_t)(n > LIFI_MAX_PAYLOAD ? LIFI_MAX_PAYLOAD : n);
    send_frame(p, chunk);
    p += chunk;
    n -= chunk;
  }
}

static void set_mode(uint8_t m) {
  if (m == g_mode) return;
  if (g_mode == MODE_DDS) dds_stop(); else ledc_stop();
  g_mode = m;
  if (g_mode == MODE_DDS) dds_start(); else ledc_start();
}

static void print_info() {
  Serial.printf("#INFO,f0=%lu,f1=%lu,rate=%lu,mode=%s,fec=%u,idle=%u,tick=%.1f,frames=%lu\n",
                (unsigned long)g_f0, (unsigned long)g_f1, (unsigned long)g_rate,
                g_mode == MODE_DDS ? "dds" : "ledc", g_fec, g_idle, s_tick_actual, (unsigned long)g_frames_sent);
  if (g_mode == MODE_DDS && g_f1 * 4 > s_tick_actual) Serial.println("#WARN f1 > TICK_HZ/4: square wave will jitter badly");
}

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  c |= 0x20;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

static void handle_command(char *line) {
  char *cmd = strtok(line, " ");
  char *arg = strtok(nullptr, " ");
  char *arg2 = strtok(nullptr, " ");
  if (!cmd) return;
  if (!strcmp(cmd, "!f0") && arg) { g_f0 = strtoul(arg, nullptr, 10); dds_set_freqs(); }
  else if (!strcmp(cmd, "!f1") && arg) { g_f1 = strtoul(arg, nullptr, 10); dds_set_freqs(); }
  else if (!strcmp(cmd, "!rate") && arg) { g_rate = strtoul(arg, nullptr, 10); dds_set_freqs(); }
  else if (!strcmp(cmd, "!mode") && arg) set_mode(!strcmp(arg, "ledc") ? MODE_LEDC : MODE_DDS);
  else if (!strcmp(cmd, "!fec") && arg) g_fec = !strcmp(arg, "on");
  else if (!strcmp(cmd, "!idle") && arg) {
    g_idle = !strcmp(arg, "off") ? IDLE_OFF : (!strcmp(arg, "on") ? IDLE_ON : IDLE_MARK);
    if (g_mode == MODE_LEDC) ledc_idle();
  } else if (!strcmp(cmd, "!bert")) {
    uint32_t n = arg ? strtoul(arg, nullptr, 10) : 100;
    uint32_t gap = arg2 ? strtoul(arg2, nullptr, 10) : 20;
    uint8_t p[LIFI_BERT_LEN];
    for (uint32_t i = 0; i < n; i++) {
      lifi_bert_build(p, (uint8_t)i);
      send_frame(p, LIFI_BERT_LEN);
      delay(gap);
      if (Serial.available() && Serial.peek() == '!') break;  // allow abort
    }
    Serial.printf("#BERTTX,%lu\n", (unsigned long)n);
  } else if (!strcmp(cmd, "!hex") && arg) {
    static uint8_t buf[LIFI_MAX_PAYLOAD];
    size_t n = 0;
    for (size_t i = 0; arg[i] && arg[i + 1] && n < sizeof(buf); i += 2) {
      int h = hexval(arg[i]), l = hexval(arg[i + 1]);
      if (h < 0 || l < 0) break;
      buf[n++] = (uint8_t)(h * 16 + l);
    }
    send_frame(buf, (uint8_t)n);
    Serial.printf("#SENT,%u\n", (unsigned)n);
    return;
  }
  print_info();
}

// ------------------------------------------------------------ Arduino entry points
static char s_line[600];
static size_t s_len = 0;

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);
  dds_start();
  delay(200);
  Serial.println("#READY tx_esp32 Li-Fi BFSK");
  print_info();
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n' || s_len >= sizeof(s_line) - 1) {
      s_line[s_len] = 0;
      if (s_len > 0) {
        if (s_line[0] == '!') handle_command(s_line);
        else {
          send_buffer((const uint8_t *)s_line, s_len);
          Serial.printf("#SENT,%u\n", (unsigned)s_len);
        }
      }
      s_len = 0;
      if (c != '\n') s_line[s_len++] = c;
    } else {
      s_line[s_len++] = c;
    }
  }
}
