// lifi_proto.h - Li-Fi BFSK link: framing, CRC-16-CCITT, Hamming(7,4), PRBS.
//
// Canonical copy lives in common/. Each Arduino sketch folder carries an
// identical copy (Arduino cannot include files outside the sketch folder).
// Run tools/sync_common.py after editing; tests check the copies match.
//
// Frame on air (bits MSB-first):
//
//   | 0xAA x4 (preamble) | SYNC (16b) | LEN (8b) | PAYLOAD (LEN bytes) | CRC16 (16b, MSB first) |
//
//   SYNC = 0x2DD4 -> body sent as plain bytes (8 bits each)
//   SYNC = 0xD263 -> body (LEN, PAYLOAD, CRC) sent Hamming(7,4) coded:
//                    every byte = high nibble codeword (7b) + low nibble codeword (7b)
//   CRC  = CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection, no xorout)
//          computed over LEN + PAYLOAD. check("123456789") = 0x29B1
//
// Header-only, plain C/C++ (no Arduino dependencies) so the exact same code
// builds on ESP32, AVR and on a PC for the host-side tests.
#ifndef LIFI_PROTO_H
#define LIFI_PROTO_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define LIFI_PREAMBLE_BYTE 0xAAu
#define LIFI_PREAMBLE_LEN 4u
#define LIFI_SYNC_PLAIN 0x2DD4u
#define LIFI_SYNC_FEC 0xD263u
#ifndef LIFI_MAX_PAYLOAD
#define LIFI_MAX_PAYLOAD 255u
#endif
#ifndef LIFI_SYNC_MAX_ERRS
#define LIFI_SYNC_MAX_ERRS 0u      // bit errors tolerated in the 16-bit sync word
#endif
#ifndef LIFI_PRE_MAX_ERRS
#define LIFI_PRE_MAX_ERRS 1u       // bit errors tolerated in the last preamble byte
#endif

// Bit-error-rate test (BERT) frames: payload = MARKER, SEQ, 32 bytes PRBS9
#define LIFI_BERT_MARKER 0xB5u
#define LIFI_BERT_PRBS_BYTES 32u
#define LIFI_BERT_LEN (2u + LIFI_BERT_PRBS_BYTES)

// ---------------------------------------------------------------- CRC
static inline uint16_t lifi_crc16_update(uint16_t crc, uint8_t b) {
  crc ^= (uint16_t)b << 8;
  for (uint8_t i = 0; i < 8; i++)
    crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
  return crc;
}

static inline uint16_t lifi_crc16(const uint8_t *d, size_t n) {
  uint16_t c = 0xFFFFu;
  for (size_t i = 0; i < n; i++) c = lifi_crc16_update(c, d[i]);
  return c;
}

static inline uint8_t lifi_popcount16(uint16_t v) {
  uint8_t c = 0;
  while (v) { v &= (uint16_t)(v - 1); c++; }
  return c;
}

// ---------------------------------------------------------------- Hamming(7,4)
// Codeword bit order (transmitted MSB first, bit6 first): p1 p2 d1 p3 d2 d3 d4
static inline uint8_t lifi_ham74_encode(uint8_t nib) {
  uint8_t d1 = (nib >> 3) & 1, d2 = (nib >> 2) & 1, d3 = (nib >> 1) & 1, d4 = nib & 1;
  uint8_t p1 = d1 ^ d2 ^ d4, p2 = d1 ^ d3 ^ d4, p3 = d2 ^ d3 ^ d4;
  return (uint8_t)((p1 << 6) | (p2 << 5) | (d1 << 4) | (p3 << 3) | (d2 << 2) | (d3 << 1) | d4);
}

// Returns the 4-bit data nibble; *fixed is set to 1 if a bit was corrected.
static inline uint8_t lifi_ham74_decode(uint8_t cw, uint8_t *fixed) {
  uint8_t c[8];
  for (uint8_t i = 1; i <= 7; i++) c[i] = (cw >> (7 - i)) & 1;  // c[1]=bit6 ... c[7]=bit0
  uint8_t s = (uint8_t)((c[1] ^ c[3] ^ c[5] ^ c[7]) | ((c[2] ^ c[3] ^ c[6] ^ c[7]) << 1) |
                        ((c[4] ^ c[5] ^ c[6] ^ c[7]) << 2));
  if (fixed) *fixed = s ? 1 : 0;
  if (s) c[s] ^= 1;
  return (uint8_t)((c[3] << 3) | (c[5] << 2) | (c[6] << 1) | c[7]);
}

// ---------------------------------------------------------------- PRBS9 (x^9 + x^5 + 1)
static inline void lifi_prbs9_fill(uint8_t *out, size_t n, uint16_t seed) {
  uint16_t s = seed ? (seed & 0x1FFu) : 0x1FFu;
  for (size_t i = 0; i < n; i++) {
    uint8_t b = 0;
    for (uint8_t k = 0; k < 8; k++) {
      uint8_t nb = (uint8_t)(((s >> 8) ^ (s >> 4)) & 1u);
      s = (uint16_t)(((s << 1) | nb) & 0x1FFu);
      b = (uint8_t)((b << 1) | nb);
    }
    out[i] = b;
  }
}

// ---------------------------------------------------------------- TX: streaming bit framer
// Produces one bit at a time so even an AVR never needs a whole bit buffer.
typedef struct {
  const uint8_t *payload;
  uint8_t len;
  uint8_t fec;
  uint16_t crc;
  uint16_t byte_idx;  // index into the virtual byte stream
  uint8_t bit_idx;    // bit inside the current (possibly coded) byte
  uint8_t cur_nbits;  // 8 (plain) or 14 (Hamming)
  uint16_t cur_word;  // current symbol word, MSB first
  uint8_t done;
} lifi_txf_t;

// Virtual byte stream: [pre x4][sync hi][sync lo][len][payload...][crc hi][crc lo]
static inline uint16_t lifi_txf_total_bytes(const lifi_txf_t *f) {
  return (uint16_t)(LIFI_PREAMBLE_LEN + 2u + 1u + f->len + 2u);
}

static inline void lifi_txf_load(lifi_txf_t *f) {
  uint16_t i = f->byte_idx;
  uint8_t b;
  uint8_t coded = 0;
  uint16_t sync = f->fec ? LIFI_SYNC_FEC : LIFI_SYNC_PLAIN;
  if (i < LIFI_PREAMBLE_LEN) b = LIFI_PREAMBLE_BYTE;
  else if (i == LIFI_PREAMBLE_LEN) b = (uint8_t)(sync >> 8);
  else if (i == LIFI_PREAMBLE_LEN + 1u) b = (uint8_t)(sync & 0xFF);
  else {
    uint16_t j = (uint16_t)(i - LIFI_PREAMBLE_LEN - 2u);  // 0 = LEN
    coded = f->fec;
    if (j == 0) b = f->len;
    else if (j <= f->len) b = f->payload[j - 1];
    else if (j == (uint16_t)(f->len + 1u)) b = (uint8_t)(f->crc >> 8);
    else b = (uint8_t)(f->crc & 0xFF);
  }
  if (coded) {
    f->cur_word = (uint16_t)(((uint16_t)lifi_ham74_encode(b >> 4) << 7) | lifi_ham74_encode(b & 0x0F));
    f->cur_nbits = 14;
  } else {
    f->cur_word = b;
    f->cur_nbits = 8;
  }
  f->bit_idx = 0;
}

static inline void lifi_txf_begin(lifi_txf_t *f, const uint8_t *payload, uint8_t len, uint8_t fec) {
  f->payload = payload;
  f->len = len;
  f->fec = fec ? 1 : 0;
  uint16_t c = lifi_crc16_update(0xFFFFu, len);
  for (uint16_t i = 0; i < len; i++) c = lifi_crc16_update(c, payload[i]);
  f->crc = c;
  f->byte_idx = 0;
  f->done = 0;
  lifi_txf_load(f);
}

// Next bit (0/1) or -1 when the frame is finished.
static inline int lifi_txf_next(lifi_txf_t *f) {
  if (f->done) return -1;
  int bit = (f->cur_word >> (f->cur_nbits - 1u - f->bit_idx)) & 1;
  if (++f->bit_idx >= f->cur_nbits) {
    if (++f->byte_idx >= lifi_txf_total_bytes(f)) f->done = 1;
    else lifi_txf_load(f);
  }
  return bit;
}

static inline uint16_t lifi_frame_bits(uint8_t len, uint8_t fec) {
  return (uint16_t)((LIFI_PREAMBLE_LEN + 2u) * 8u + (uint16_t)(len + 3u) * (fec ? 14u : 8u));
}

// ---------------------------------------------------------------- RX: streaming deframer
typedef enum { LIFI_DF_HUNT = 0, LIFI_DF_BODY = 1 } lifi_df_state_t;

typedef struct {
  uint8_t ok;          // CRC matched
  uint8_t fec;         // frame used Hamming(7,4)
  uint8_t len;
  uint16_t crc_rx, crc_calc;
  uint16_t corrected;  // Hamming corrections applied
  uint8_t payload[LIFI_MAX_PAYLOAD];
} lifi_frame_t;

typedef struct {
  uint32_t sr;          // last 32 received bits (hunt)
  uint8_t state;
  uint8_t fec;
  uint16_t word;        // bits of the current (coded) byte
  uint8_t nbits;
  uint16_t body_idx;    // 0 = LEN, then payload, then 2 CRC bytes
  uint16_t crc;
  uint16_t crc_rx;
  uint16_t corrected;
  uint8_t len;
  lifi_frame_t *out;
} lifi_deframer_t;

static inline void lifi_df_reset(lifi_deframer_t *d) {
  d->sr = 0;
  d->state = LIFI_DF_HUNT;
  d->nbits = 0;
  d->word = 0;
}

static inline void lifi_df_init(lifi_deframer_t *d, lifi_frame_t *out) {
  d->out = out;
  lifi_df_reset(d);
}

// Hunt helper: does a 32-bit history end with [preamble byte][sync]? Returns
// 1 = plain, 2 = FEC, 0 = no.
static inline uint8_t lifi_sync_match(uint32_t sr) {
  uint16_t s = (uint16_t)(sr & 0xFFFFu);
  uint8_t pre = (uint8_t)((sr >> 16) & 0xFFu);
  if (lifi_popcount16((uint16_t)(pre ^ LIFI_PREAMBLE_BYTE)) > LIFI_PRE_MAX_ERRS) return 0;
  if (lifi_popcount16((uint16_t)(s ^ LIFI_SYNC_PLAIN)) <= LIFI_SYNC_MAX_ERRS) return 1;
  if (lifi_popcount16((uint16_t)(s ^ LIFI_SYNC_FEC)) <= LIFI_SYNC_MAX_ERRS) return 2;
  return 0;
}

// Start receiving a body right after a sync match (used by the multi-phase demod).
static inline void lifi_df_start_body(lifi_deframer_t *d, uint8_t fec) {
  d->state = LIFI_DF_BODY;
  d->fec = fec;
  d->nbits = 0;
  d->word = 0;
  d->body_idx = 0;
  d->crc = 0xFFFFu;
  d->corrected = 0;
  d->len = 0;
}

// Feed one bit. Returns 1 when a sync was just found, 2 when a frame is
// complete (check d->out->ok), 0 otherwise.
static inline uint8_t lifi_df_push(lifi_deframer_t *d, uint8_t bit) {
  if (d->state == LIFI_DF_HUNT) {
    d->sr = (d->sr << 1) | (bit & 1u);
    uint8_t m = lifi_sync_match(d->sr);
    if (m) {
      lifi_df_start_body(d, (uint8_t)(m == 2));
      return 1;
    }
    return 0;
  }
  d->word = (uint16_t)((d->word << 1) | (bit & 1u));
  d->nbits++;
  uint8_t need = d->fec ? 14 : 8;
  if (d->nbits < need) return 0;
  uint8_t b;
  if (d->fec) {
    uint8_t f1 = 0, f2 = 0;
    uint8_t hi = lifi_ham74_decode((uint8_t)((d->word >> 7) & 0x7F), &f1);
    uint8_t lo = lifi_ham74_decode((uint8_t)(d->word & 0x7F), &f2);
    d->corrected = (uint16_t)(d->corrected + f1 + f2);
    b = (uint8_t)((hi << 4) | lo);
  } else {
    b = (uint8_t)d->word;
  }
  d->word = 0;
  d->nbits = 0;
  uint16_t j = d->body_idx++;
  if (j == 0) {
    d->len = b;
    d->crc = lifi_crc16_update(d->crc, b);
#if LIFI_MAX_PAYLOAD < 255
    if (b > LIFI_MAX_PAYLOAD) { lifi_df_reset(d); return 0; }
#endif
    return 0;
  }
  if (j <= d->len) {
    d->out->payload[j - 1] = b;
    d->crc = lifi_crc16_update(d->crc, b);
    return 0;
  }
  if (j == (uint16_t)(d->len + 1u)) { d->crc_rx = (uint16_t)b << 8; return 0; }
  d->crc_rx |= b;
  lifi_frame_t *o = d->out;
  o->len = d->len;
  o->fec = d->fec;
  o->crc_rx = d->crc_rx;
  o->crc_calc = d->crc;
  o->ok = (uint8_t)(d->crc_rx == d->crc);
  o->corrected = d->corrected;
  lifi_df_reset(d);
  return 2;
}

// BERT helpers: build a test payload, and count bit errors of a received one.
static inline void lifi_bert_build(uint8_t *p, uint8_t seq) {
  p[0] = LIFI_BERT_MARKER;
  p[1] = seq;
  lifi_prbs9_fill(p + 2, LIFI_BERT_PRBS_BYTES, 0x1FF);
}

static inline uint16_t lifi_bert_errors(const uint8_t *p) {
  uint8_t ref[LIFI_BERT_PRBS_BYTES];
  lifi_prbs9_fill(ref, LIFI_BERT_PRBS_BYTES, 0x1FF);
  uint16_t e = 0;
  for (uint8_t i = 0; i < LIFI_BERT_PRBS_BYTES; i++) e = (uint16_t)(e + lifi_popcount16((uint16_t)(p[2 + i] ^ ref[i])));
  return e;
}

#endif  // LIFI_PROTO_H
