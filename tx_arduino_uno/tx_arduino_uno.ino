// tx_arduino_uno.ino - Li-Fi BFSK transmitter for an Arduino Uno (ATmega328P, 16 MHz)
//
// Alternative to tx_esp32. Two tone generators (compile-time USE_TONE):
//   USE_TONE 0 (default): Timer1 in CTC mode toggles OC1A (pin 9) in hardware.
//       The compare ISR counts elapsed timer ticks and changes OCR1A only at a
//       tone edge, so frequency switches are phase continuous and the long-run
//       bit rate is exact (16 MHz / rate ticks per bit).
//   USE_TONE 1: Arduino tone() (Timer2) restarted at every bit, paced with
//       micros(). Simple but the phase restarts at each bit.
//
// Two line codings (runtime "!uart on|off"):
//   packet (default) : same frame as the ESP32 link (0xAA x4, sync, len, payload, CRC16, opt. Hamming)
//   uart             : plain 8N1 async bytes (start 0, 8 data LSB first, stop 1),
//                      idle = mark. Feed XR2211 DATA OUT straight into a UART RX.
//
// Pin 9 -> 100 R -> logic-level N-MOSFET gate (10k pull-down), LED string on the drain.
// Commands (115200 baud): text line = send, !fec on|off, !uart on|off, !bert <n>, !info
#include <Arduino.h>
#include "lifi_proto.h"

#define USE_TONE 0
#define LED_PIN 9            // OC1A (must be 9 for the Timer1 generator)
#define F0_HZ 10000UL        // space / bit 0  (XR2211 example values in README)
#define F1_HZ 15000UL        // mark  / bit 1
#define RATE_BPS 1000UL
#define IDLE_GAP_BITS 16

static uint8_t g_fec = 0, g_uart = 0;

#if !USE_TONE
// ------------------------------------------------------------ bit FIFO (loop -> ISR)
#define BITQ_SIZE 512                       // bits, power of two (64 bytes of RAM)
static uint8_t s_bitq[BITQ_SIZE / 8];
static volatile uint16_t s_head = 0, s_tail = 0;

static uint16_t bitq_count() {
  uint16_t h, t;
  noInterrupts(); h = s_head; t = s_tail; interrupts();
  return (uint16_t)(h - t);
}

static void bitq_push_blocking(uint8_t bit) {
  while (bitq_count() >= BITQ_SIZE) { }
  uint16_t i = s_head & (BITQ_SIZE - 1);
  if (bit) s_bitq[i >> 3] |= (uint8_t)(1 << (i & 7));
  else s_bitq[i >> 3] &= (uint8_t)~(1 << (i & 7));
  noInterrupts(); s_head++; interrupts();
}

// returns 0/1, or 1 (mark) when the queue is empty
static inline uint8_t bitq_pop_isr(uint8_t *was_empty) {
  if (s_head == s_tail) { *was_empty = 1; return 1; }
  uint16_t i = s_tail & (BITQ_SIZE - 1);
  s_tail++;
  *was_empty = 0;
  return (s_bitq[i >> 3] >> (i & 7)) & 1;
}

#endif

static volatile uint8_t s_busy = 0;

#if !USE_TONE
// ------------------------------------------------------------ Timer1 CPFSK
static const uint16_t HALF0 = (uint16_t)((F_CPU + F0_HZ) / (2UL * F0_HZ));  // ticks per half period
static const uint16_t HALF1 = (uint16_t)((F_CPU + F1_HZ) / (2UL * F1_HZ));
static const uint32_t BIT_TICKS = F_CPU / RATE_BPS;
static volatile uint32_t s_elapsed = 0;
static volatile uint16_t s_half = HALF1;

ISR(TIMER1_COMPA_vect) {
  // OC1A has just toggled in hardware; decide the length of the next half period.
  s_elapsed += s_half;
  if (s_elapsed >= BIT_TICKS) {
    s_elapsed -= BIT_TICKS;
    uint8_t empty;
    uint8_t b = bitq_pop_isr(&empty);
    s_busy = !empty;
    s_half = b ? HALF1 : HALF0;
    OCR1A = s_half - 1;
  }
}

static void gen_begin() {
  pinMode(LED_PIN, OUTPUT);
  noInterrupts();
  TCCR1A = _BV(COM1A0);              // toggle OC1A on compare match
  TCCR1B = _BV(WGM12) | _BV(CS10);   // CTC (TOP = OCR1A), prescaler 1
  OCR1A = HALF1 - 1;
  TCNT1 = 0;
  TIMSK1 = _BV(OCIE1A);
  interrupts();
}
#else
// ------------------------------------------------------------ tone() generator
static void gen_begin() { pinMode(LED_PIN, OUTPUT); tone(LED_PIN, F1_HZ); }
#endif

static void put_bit(uint8_t b) {
#if USE_TONE
  static uint32_t t_next = 0;
  if ((int32_t)(micros() - t_next) > 100000L) t_next = micros();  // resync after idle
  tone(LED_PIN, b ? F1_HZ : F0_HZ);
  t_next += 1000000UL / RATE_BPS;
  while ((int32_t)(micros() - t_next) < 0) { }
#else
  bitq_push_blocking(b);
#endif
}

static void wait_done() {
#if !USE_TONE
  while (bitq_count() > 0 || s_busy) { }
#else
  tone(LED_PIN, F1_HZ);  // idle = mark
#endif
}

static void send_uart_bytes(const uint8_t *p, uint8_t n) {
  for (uint8_t i = 0; i < 4; i++) put_bit(1);
  for (uint8_t i = 0; i < n; i++) {
    put_bit(0);                                   // start
    for (uint8_t k = 0; k < 8; k++) put_bit((p[i] >> k) & 1);  // LSB first
    put_bit(1);                                   // stop
  }
  wait_done();
}

static void send_frame(const uint8_t *p, uint8_t n) {
  if (g_uart) { send_uart_bytes(p, n); return; }
  lifi_txf_t f;
  lifi_txf_begin(&f, p, n, g_fec);
  for (uint8_t i = 0; i < IDLE_GAP_BITS; i++) put_bit(1);
  int b;
  while ((b = lifi_txf_next(&f)) >= 0) put_bit((uint8_t)b);
  wait_done();
}

static char s_line[130];
static uint8_t s_len = 0;

static void info() {
  Serial.print(F("#INFO,f0=")); Serial.print(F0_HZ);
  Serial.print(F(",f1=")); Serial.print(F1_HZ);
  Serial.print(F(",rate=")); Serial.print(RATE_BPS);
  Serial.print(F(",fec=")); Serial.print(g_fec);
  Serial.print(F(",uart=")); Serial.print(g_uart);
  Serial.print(F(",gen=")); Serial.println(USE_TONE ? F("tone") : F("timer1"));
}

void setup() {
  Serial.begin(115200);
  gen_begin();
  Serial.println(F("#READY tx_arduino_uno Li-Fi BFSK"));
  info();
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c != '\n' && s_len < sizeof(s_line) - 1) { s_line[s_len++] = c; continue; }
    s_line[s_len] = 0;
    if (s_len == 0) continue;
    if (!strncmp(s_line, "!fec ", 5)) g_fec = !strcmp(s_line + 5, "on");
    else if (!strncmp(s_line, "!uart ", 6)) g_uart = !strcmp(s_line + 6, "on");
    else if (!strncmp(s_line, "!bert", 5)) {
      int n = atoi(s_line + 5);
      if (n <= 0) n = 100;
      uint8_t p[LIFI_BERT_LEN];
      for (int i = 0; i < n; i++) { lifi_bert_build(p, (uint8_t)i); send_frame(p, LIFI_BERT_LEN); delay(20); }
    } else if (s_line[0] != '!') {
      send_frame((const uint8_t *)s_line, s_len);
      Serial.print(F("#SENT,")); Serial.println(s_len);
    }
    if (s_line[0] == '!') info();
    s_len = 0;
    if (c != '\n') s_line[s_len++] = c;
  }
}
