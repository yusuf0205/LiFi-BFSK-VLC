// lifi_demod.h - streaming BFSK demodulator for the Li-Fi link.
//
//   samples -> 2x DC/flicker removal (cascaded mean trackers)
//           -> LIFI_PHASES parallel Goertzel pairs (f0, f1), one per bit-timing
//              phase, each integrating one bit window (fractional samples/bit OK)
//           -> hard decision bit = P1 > P0, margin = (P1-P0)/(P1+P0)
//           -> hunt: every phase looks for [0xAA][SYNC]; when one matches, the
//              phase with the best average margin over the preamble is locked
//              (bit timing recovered from the 1010... preamble)
//           -> tracking: after every bit the lock may move one phase towards a
//              neighbour with a clearly better slow-average margin (handles
//              clock offset between TX and RX crystals)
//           -> deframer (LEN, payload, CRC, optional Hamming(7,4))
//
// Header-only, float math only (ESP32 has a single-precision FPU). The
// identical algorithm is ported to Python in sim/lifi_ref.py and the two are
// cross-checked by tests/host + sim/tests.
#ifndef LIFI_DEMOD_H
#define LIFI_DEMOD_H

#include <math.h>
#include "lifi_proto.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#ifndef LIFI_PHASES
#define LIFI_PHASES 8
#endif
#ifndef LIFI_TRACK_HYST
#define LIFI_TRACK_HYST 0.10f   // neighbour must beat current phase by 10 % (+0.01)
#endif
#ifndef LIFI_AVG_K
#define LIFI_AVG_K 0.125f       // fast |margin| average (about 8 bits): picks the phase at sync
#endif
#ifndef LIFI_TRACK_K
#define LIFI_TRACK_K 0.03125f   // slow |margin| average (about 32 bits): drives tracking
#endif

typedef struct {
  float q0a, q0b, q1a, q1b;  // Goertzel states for f0 and f1
  uint16_t n;                // samples so far in this window
  uint16_t win;              // length of this window
  float frac;                // fractional sample accumulator
  float avg_q;               // fast smoothed |margin| (acquisition)
  float avg_t;               // slow smoothed |margin| (tracking)
  uint32_t sr;               // hunt shift register for this phase
  uint8_t primed;            // first (partial) window is discarded
} lifi_phase_t;

typedef struct {
  // configuration
  float fs, rb, f0, f1, spb;
  float w0, w1, c0, c1;
  float hp_alpha;
  // state
  float m1, m2;
  lifi_phase_t ph[LIFI_PHASES];
  int8_t lock;
  uint8_t skip_next;
  lifi_deframer_t df;
  lifi_frame_t frame;
  // running per-frame statistics
  double acc_pmax, acc_pmin, acc_mag, acc_q;
  uint16_t nsym;
  // results of the last completed frame (valid after push returns 2)
  float frame_rssi_db;   // 20log10(mean tone amplitude) in input units (ADC counts)
  float frame_snr_db;    // 10log10(sum P_winner / sum P_loser): tone contrast
  float frame_quality;   // mean |margin| 0..1
  uint8_t frame_phase;
  uint8_t phase_moves;
  // last decision (any phase) for an idle RSSI meter
  float last_amp0, last_amp1;
  // counters
  uint32_t syncs, frames, crc_fail;
} lifi_demod_t;

static inline void lifi_demod_init(lifi_demod_t *d, float fs, float rb, float f0, float f1) {
  memset(d, 0, sizeof(*d));
  d->fs = fs; d->rb = rb; d->f0 = f0; d->f1 = f1;
  d->spb = fs / rb;
  d->w0 = 2.0f * (float)M_PI * f0 / fs;
  d->w1 = 2.0f * (float)M_PI * f1 / fs;
  d->c0 = 2.0f * cosf(d->w0);
  d->c1 = 2.0f * cosf(d->w1);
  // DC tracker corner ~ fs*alpha/(2 pi): 1/16 at 40 kSps -> ~400 Hz per stage
  d->hp_alpha = 1.0f / 16.0f;
  d->lock = -1;
  for (int p = 0; p < LIFI_PHASES; p++) {
    float x = (float)p * d->spb / (float)LIFI_PHASES + d->spb;
    d->ph[p].win = (uint16_t)x;
    d->ph[p].frac = x - (float)d->ph[p].win;
  }
  lifi_df_init(&d->df, &d->frame);
}

static inline void lifi_demod_unlock(lifi_demod_t *d) {
  d->lock = -1;
  d->skip_next = 0;
  for (int p = 0; p < LIFI_PHASES; p++) d->ph[p].sr = 0;
  lifi_df_reset(&d->df);
}

// Goertzel power of a finished window: |X|^2 = q1^2 + q2^2 - c q1 q2
static inline float lifi_gpow(float a, float b, float c) {
  float p = a * a + b * b - c * a * b;
  return p > 0.0f ? p : 0.0f;
}

// Internal: a phase finished its bit window. Returns 0/1/2 like lifi_demod_push.
static inline uint8_t lifi_demod_emit(lifi_demod_t *d, int p) {
  lifi_phase_t *ph = &d->ph[p];
  float P0 = lifi_gpow(ph->q0a, ph->q0b, d->c0);
  float P1 = lifi_gpow(ph->q1a, ph->q1b, d->c1);
  float n = (float)ph->win;
  ph->q0a = ph->q0b = ph->q1a = ph->q1b = 0.0f;
  ph->n = 0;
  float x = d->spb + ph->frac;
  ph->win = (uint16_t)x;
  ph->frac = x - (float)ph->win;
  if (!ph->primed) { ph->primed = 1; return 0; }

  float m = (P1 - P0) / (P1 + P0 + 1e-20f);
  uint8_t bit = m > 0.0f;
  float q = fabsf(m);
  ph->avg_q += (q - ph->avg_q) * LIFI_AVG_K;
  ph->avg_t += (q - ph->avg_t) * LIFI_TRACK_K;
  float a0 = 2.0f * sqrtf(P0) / n, a1 = 2.0f * sqrtf(P1) / n;  // tone amplitude
  d->last_amp0 = a0; d->last_amp1 = a1;

  if (d->lock < 0) {
    ph->sr = (ph->sr << 1) | bit;
    uint8_t mt = lifi_sync_match(ph->sr);
    if (mt) {
      // Bit timing: lock the phase with the best |margin| over the preamble.
      // A phase up to half a bit later than p has not yet produced the last
      // sync bit, so its next window is skipped.
      int best = p;
      for (int k = 0; k < LIFI_PHASES; k++)
        if (d->ph[k].avg_q > d->ph[best].avg_q) best = k;
      int off = (best - p + LIFI_PHASES) % LIFI_PHASES;
      d->lock = (int8_t)best;
      d->skip_next = (uint8_t)(off >= 1 && off <= LIFI_PHASES / 2);
      lifi_df_start_body(&d->df, (uint8_t)(mt == 2));
      d->acc_pmax = d->acc_pmin = d->acc_mag = d->acc_q = 0.0;
      d->nsym = 0;
      d->phase_moves = 0;
      d->syncs++;
      return 1;
    }
    return 0;
  }
  if (p != d->lock) return 0;
  if (d->skip_next) { d->skip_next = 0; return 0; }

  d->acc_pmax += bit ? P1 : P0;
  d->acc_pmin += bit ? P0 : P1;
  d->acc_mag += bit ? a1 : a0;
  d->acc_q += q;
  d->nsym++;

  uint8_t r = lifi_df_push(&d->df, bit);
  if (r == 2) {
    float ns = d->nsym ? (float)d->nsym : 1.0f;
    float mag = (float)(d->acc_mag / ns);
    d->frame_rssi_db = 20.0f * log10f(mag + 1e-9f);
    d->frame_snr_db = 10.0f * log10f((float)((d->acc_pmax + 1e-20) / (d->acc_pmin + 1e-20)));
    d->frame_quality = (float)(d->acc_q / ns);
    d->frame_phase = (uint8_t)d->lock;
    d->frames++;
    if (!d->frame.ok) d->crc_fail++;
    lifi_demod_unlock(d);
    return 2;
  }

  // timing tracking: move at most one phase per bit
  int pm = (p + LIFI_PHASES - 1) % LIFI_PHASES;
  int pp = (p + 1) % LIFI_PHASES;
  float cur = ph->avg_t * (1.0f + LIFI_TRACK_HYST) + 0.01f;
  float qm = d->ph[pm].avg_t, qp = d->ph[pp].avg_t;
  if (qp > cur && qp >= qm) {
    d->lock = (int8_t)pp;   // later phase: its next window still covers this bit
    d->skip_next = 1;
    d->phase_moves++;
  } else if (qm > cur) {
    d->lock = (int8_t)pm;   // earlier phase: its next window is the next bit
    d->phase_moves++;
  }
  return 0;
}

// Push one ADC sample. Returns 0 nothing, 1 sync found, 2 frame complete
// (d->frame holds it; d->frame.ok says whether the CRC matched).
static inline uint8_t lifi_demod_push(lifi_demod_t *d, float x) {
  d->m1 += d->hp_alpha * (x - d->m1);
  float y1 = x - d->m1;
  d->m2 += d->hp_alpha * (y1 - d->m2);
  float y = y1 - d->m2;
  uint8_t ret = 0;
  for (int p = 0; p < LIFI_PHASES; p++) {
    lifi_phase_t *ph = &d->ph[p];
    float s0 = y + d->c0 * ph->q0a - ph->q0b;
    ph->q0b = ph->q0a; ph->q0a = s0;
    float s1 = y + d->c1 * ph->q1a - ph->q1b;
    ph->q1b = ph->q1a; ph->q1a = s1;
    if (++ph->n >= ph->win) {
      uint8_t r = lifi_demod_emit(d, p);
      if (r > ret) ret = r;
    }
  }
  return ret;
}

#endif  // LIFI_DEMOD_H
