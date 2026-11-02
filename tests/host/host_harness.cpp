// host_harness.cpp - runs the firmware's own lifi_proto.h / lifi_demod.h on a PC.
//
//   host_harness txbits <hexpayload|-> <fec 0|1>     print the on-air bit string
//   host_harness demod <file.f32> <fs> <rb> <f0> <f1> demodulate float32 samples
//
// Build: c++ -O2 -std=c++11 -I../../common host_harness.cpp -o host_harness
// (the pytest suite builds it automatically with g++/clang++ or `python -m ziglang c++`).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lifi_proto.h"
#include "lifi_demod.h"

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

int main(int argc, char **argv) {
  if (argc >= 4 && !strcmp(argv[1], "txbits")) {
    static uint8_t buf[256];
    size_t n = 0;
    const char *h = argv[2];
    if (strcmp(h, "-") != 0)
      for (size_t i = 0; h[i] && h[i + 1] && n < 255; i += 2) buf[n++] = (uint8_t)(hexval(h[i]) * 16 + hexval(h[i + 1]));
    lifi_txf_t f;
    lifi_txf_begin(&f, buf, (uint8_t)n, (uint8_t)atoi(argv[3]));
    int b;
    while ((b = lifi_txf_next(&f)) >= 0) putchar('0' + b);
    putchar('\n');
    return 0;
  }
  if (argc >= 7 && !strcmp(argv[1], "demod")) {
    FILE *fp = fopen(argv[2], "rb");
    if (!fp) { perror("open"); return 1; }
    static lifi_demod_t d;
    lifi_demod_init(&d, (float)atof(argv[3]), (float)atof(argv[4]), (float)atof(argv[5]), (float)atof(argv[6]));
    float buf[4096];
    size_t got;
    unsigned long t = 0;
    while ((got = fread(buf, sizeof(float), 4096, fp)) > 0) {
      for (size_t i = 0; i < got; i++, t++) {
        if (lifi_demod_push(&d, buf[i]) == 2) {
          lifi_frame_t *fr = &d.frame;
          printf("#FRAME,%d,%d,%d,%.2f,%.2f,%.4f,%u,%u,%u,%lu,", fr->ok, fr->fec, fr->len, d.frame_rssi_db,
                 d.frame_snr_db, d.frame_quality, fr->corrected, d.frame_phase, d.phase_moves, t + 1);
          for (int k = 0; k < fr->len; k++) printf("%02x", fr->payload[k]);
          printf("\n");
        }
      }
    }
    fclose(fp);
    printf("#END,%lu,%lu,%lu,%lu\n", t, (unsigned long)d.syncs, (unsigned long)d.frames, (unsigned long)d.crc_fail);
    return 0;
  }
  fprintf(stderr, "usage: see header\n");
  return 2;
}
