// rx_arduino_uno_xr2211.ino - Li-Fi receiver for an Arduino Uno behind an XR2211 FSK demodulator
//
// Photodiode -> TIA -> AC coupling -> XR2211 (PLL FSK demod, f0/f1 tuned as in
// README) -> DATA OUT (open collector, 5k1 pull-up to 5 V) -> Uno pin D2.
// The XR2211 does the tone detection in analog; the Uno only decodes the
// digital data line.
//
// RX_MODE_PACKET (default): Timer2 samples D2 at 8 x bit rate. A DPLL keeps a
//   0..7 bit-phase counter: while hunting it is re-aligned on every edge (the
//   0xAA preamble gives an edge every bit; an edge in the second half of a
//   bit first completes that bit), once a sync word is found it is nudged by
//   one step per edge. Bit = majority of samples 3,4,5. The bit
//   stream goes through the same deframer as the ESP32 (sync, len, CRC16,
//   Hamming). Data polarity is detected automatically from the sync word.
//   The identical algorithm is in sim/lifi_ref.py (DigitalLineDecoder) and tested.
// RX_MODE_UART: TX in "!uart on" mode sends plain 8N1 bytes; read them with
//   SoftwareSerial on D8 (wire DATA OUT to D8 as well) and print them.
//
// Output (115200): RX ok "text" / #FRAME,ok,fec,len,corrected,hex / #BERT,frames,bits,errors,ber
#include <Arduino.h>
#define LIFI_MAX_PAYLOAD 255
#include "lifi_proto.h"

#define RX_MODE_PACKET 0
#define RX_MODE_UART 1
#define RX_MODE RX_MODE_PACKET

#define DATA_PIN 2            // PD2
#define RATE_BPS 1000UL
#define OS 8                  // oversampling

#if RX_MODE == RX_MODE_UART
#include <SoftwareSerial.h>
SoftwareSerial lifiSerial(8, 255);  // RX on D8, no TX pin
void setup() {
  Serial.begin(115200);
  lifiSerial.begin(RATE_BPS);
  Serial.println(F("#READY rx_arduino_uno_xr2211 (UART mode)"));
}
void loop() {
  while (lifiSerial.available()) Serial.write((char)lifiSerial.read());
}
#else

// ------------------------------------------------------------ bit FIFO (ISR -> loop)
#define BITQ_SIZE 256
static volatile uint8_t s_bitq[BITQ_SIZE / 8];
static volatile uint8_t s_head = 0, s_tail = 0;
static volatile uint8_t s_overflow = 0;

// DPLL state (ISR only)
static volatile uint8_t s_hunting = 1;   // set/cleared by loop()
static int8_t s_c = 0;
static uint8_t s_prev = 1, s_votes = 0;

static inline void put_bit_isr(uint8_t bit) {
  if ((uint8_t)(s_head - s_tail) < BITQ_SIZE - 1) {
    uint8_t i = s_head;  // BITQ_SIZE == 256 -> natural wrap
    if (bit) s_bitq[i >> 3] |= (uint8_t)(1 << (i & 7));
    else s_bitq[i >> 3] &= (uint8_t)~(1 << (i & 7));
    s_head++;
  } else {
    s_overflow = 1;
  }
}

ISR(TIMER2_COMPA_vect) {
  uint8_t s = (PIND >> DATA_PIN) & 1;
  if (s != s_prev) {
    if (s_hunting) {
      // hard re-align; an edge in the 2nd half of the bit ends the current bit
      if (s_c >= OS / 2) put_bit_isr(s_votes >= 2);
      s_votes = 0;
      s_c = 0;
    } else if (s_c != 0) {
      s_c += (s_c < OS / 2) ? -1 : 1;  // edge late: slow down / early: speed up
    }
    s_prev = s;
  }
  if (s_c >= OS / 2 - 1 && s_c <= OS / 2 + 1) s_votes += s;
  if (++s_c >= OS) {
    s_c -= OS;
    put_bit_isr(s_votes >= 2);
    s_votes = 0;
  }
}

static void timer2_begin(uint32_t rate_hz) {
  // pick the smallest prescaler that fits OCR2A in 8 bits
  static const uint16_t pres[] = {1, 8, 32, 64, 128, 256, 1024};
  uint8_t cs = 1;
  uint32_t ocr = 0;
  for (uint8_t i = 0; i < 7; i++) {
    ocr = F_CPU / ((uint32_t)pres[i] * rate_hz);
    if (ocr >= 1 && ocr <= 256) { cs = i + 1; break; }
  }
  noInterrupts();
  TCCR2A = _BV(WGM21);   // CTC
  TCCR2B = cs;           // CS22:0 = 1..7 matches the table order above
  OCR2A = (uint8_t)(ocr - 1);
  TCNT2 = 0;
  TIMSK2 = _BV(OCIE2A);
  interrupts();
}

static lifi_frame_t s_frame;
static lifi_deframer_t s_df;
static uint32_t s_sr = 0;
static uint8_t s_invert = 0;
static uint32_t s_bert_frames = 0, s_bert_bits = 0, s_bert_errs = 0;

static void print_frame() {
  Serial.print(F("#FRAME,")); Serial.print(s_frame.ok);
  Serial.print(','); Serial.print(s_frame.fec);
  Serial.print(','); Serial.print(s_frame.len);
  Serial.print(','); Serial.print(s_frame.corrected);
  Serial.print(',');
  for (uint8_t i = 0; i < s_frame.len; i++) {
    if (s_frame.payload[i] < 16) Serial.print('0');
    Serial.print(s_frame.payload[i], HEX);
  }
  Serial.println();
  if (s_frame.len == LIFI_BERT_LEN && lifi_popcount16((uint16_t)(s_frame.payload[0] ^ LIFI_BERT_MARKER)) <= 2) {
    s_bert_frames++;
    s_bert_bits += LIFI_BERT_PRBS_BYTES * 8;
    s_bert_errs += lifi_bert_errors(s_frame.payload);
    Serial.print(F("#BERT,")); Serial.print(s_bert_frames);
    Serial.print(','); Serial.print(s_bert_bits);
    Serial.print(','); Serial.print(s_bert_errs);
    Serial.print(','); Serial.println((double)s_bert_errs / (double)s_bert_bits, 6);
    return;
  }
  Serial.print(s_frame.ok ? F("RX ok \"") : F("RX CRC-FAIL \""));
  Serial.write(s_frame.payload, s_frame.len);
  Serial.println('"');
}

void setup() {
  Serial.begin(115200);
  pinMode(DATA_PIN, INPUT_PULLUP);
  lifi_df_init(&s_df, &s_frame);
  timer2_begin(RATE_BPS * OS);
  Serial.println(F("#READY rx_arduino_uno_xr2211 (packet mode)"));
}

void loop() {
  while (s_tail != s_head) {
    uint8_t i = s_tail;
    uint8_t bit = (s_bitq[i >> 3] >> (i & 7)) & 1;
    s_tail++;
    if (s_df.state == LIFI_DF_HUNT) {
      // hunt for the sync word in both polarities (XR2211 output polarity depends on wiring)
      s_sr = (s_sr << 1) | bit;
      uint8_t m = lifi_sync_match(s_sr), inv = 0;
      if (!m) { m = lifi_sync_match(~s_sr); inv = 1; }
      if (m) {
        s_invert = inv;
        lifi_df_start_body(&s_df, m == 2);
        s_hunting = 0;
      }
      continue;
    }
    if (lifi_df_push(&s_df, bit ^ s_invert) == 2) {
      s_hunting = 1;
      s_sr = 0;
      print_frame();
    }
  }
  if (s_overflow) { s_overflow = 0; Serial.println(F("#WARN bit fifo overflow")); }
}
#endif
