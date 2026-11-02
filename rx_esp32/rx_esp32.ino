// rx_esp32.ino - Li-Fi BFSK receiver (Arduino-ESP32 core 3.x)
//
// Photodiode front-end (TIA + AC/HPF + gain, biased at mid-supply) -> ADC1.
// The ADC runs in continuous (DMA) mode at FS_HZ through the ESP-IDF
// adc_continuous driver; every sample goes through lifi_demod.h:
//   DC/flicker removal (cascaded mean trackers) -> 8 timing phases x Goertzel
//   (f0, f1) per bit window -> preamble/sync timing lock -> tracking ->
//   LEN/payload/CRC (+ Hamming(7,4) if the TX used it).
//
// Output (921600 baud):
//   RX ok "text"                                  human readable
//   #FRAME,ok,fec,len,rssi_db,snr_db,quality,corrected,phase,moves,hex
//   #BERT,frames,bits,errors,ber,lost
//   #STAT,ms,fs_meas,syncs,frames,crc_fail,bert_frames,bert_bits,bert_errs,ber,idle_rssi_db
// rssi_db  = 20log10(mean amplitude of the winning tone, ADC counts)
// snr_db   = winning vs losing tone energy over the frame (tone contrast)
// quality  = mean |P1-P0|/(P1+P0), 0..1
//
// Commands: "!reset" clears statistics, "!info" prints settings.
#include <Arduino.h>
#include "esp_timer.h"
#include "esp_adc/adc_continuous.h"

#define LIFI_PHASES 8
#include "lifi_proto.h"
#include "lifi_demod.h"

// ------------------------------------------------------------ configuration
#define ADC_GPIO 34              // ADC1 pin (ESP32: GPIO32..39). ADC2 cannot be used with Wi-Fi.
#define FS_HZ 48000UL            // sample rate request (48k: tone harmonics never alias onto f0/f1); measured at boot
#define F0_HZ 10000.0f
#define F1_HZ 15000.0f
#define RATE_BPS 1000.0f
#define AUTO_CAL_FS 1            // 1: measure real ADC rate for 1 s and use it in the demod
#define STAT_PERIOD_MS 2000
#define SERIAL_BAUD 921600
#define READ_BYTES 1024          // DMA frame read size

#if CONFIG_IDF_TARGET_ESP32 || CONFIG_IDF_TARGET_ESP32S2
#define LIFI_ADC_FORMAT ADC_DIGI_OUTPUT_FORMAT_TYPE1
#define ADC_SAMPLE_CH(p) ((p)->type1.channel)
#define ADC_SAMPLE_VAL(p) ((p)->type1.data)
#else
#define LIFI_ADC_FORMAT ADC_DIGI_OUTPUT_FORMAT_TYPE2
#define ADC_SAMPLE_CH(p) ((p)->type2.channel)
#define ADC_SAMPLE_VAL(p) ((p)->type2.data)
#endif

typedef void (*sample_fn_t)(float);  // must precede Arduino's generated prototypes
static adc_continuous_handle_t s_adc = nullptr;
static adc_channel_t s_chan;
static lifi_demod_t s_dm;
static uint8_t s_buf[READ_BYTES];
static float s_fs = FS_HZ;

// BER statistics
static uint32_t s_bert_frames = 0, s_bert_bits = 0, s_bert_errs = 0, s_bert_lost = 0;
static int s_bert_last_seq = -1;
static uint32_t s_samples = 0, s_last_stat = 0, s_samples_at_stat = 0;

static bool adc_begin() {
  adc_unit_t unit;
  if (adc_continuous_io_to_channel(ADC_GPIO, &unit, &s_chan) != ESP_OK || unit != ADC_UNIT_1) {
    Serial.println("#ERR ADC_GPIO is not an ADC1 pin");
    return false;
  }
  adc_continuous_handle_cfg_t hc = {};
  hc.max_store_buf_size = 16384;
  hc.conv_frame_size = READ_BYTES;
  if (adc_continuous_new_handle(&hc, &s_adc) != ESP_OK) return false;

  static adc_digi_pattern_config_t pat = {};
  pat.atten = ADC_ATTEN_DB_12;           // ~0..3.1 V input range
  pat.channel = (uint8_t)s_chan;
  pat.unit = ADC_UNIT_1;
  pat.bit_width = SOC_ADC_DIGI_MAX_BITWIDTH;

  adc_continuous_config_t cfg = {};
  cfg.pattern_num = 1;
  cfg.adc_pattern = &pat;
  cfg.sample_freq_hz = FS_HZ;
  cfg.conv_mode = ADC_CONV_SINGLE_UNIT_1;
  cfg.format = LIFI_ADC_FORMAT;
  if (adc_continuous_config(s_adc, &cfg) != ESP_OK) return false;
  return adc_continuous_start(s_adc) == ESP_OK;
}

// Reads one DMA chunk; calls fn(sample) for every valid sample. Returns count.
static uint32_t adc_pump(sample_fn_t fn) {
  uint32_t got = 0;
  esp_err_t r = adc_continuous_read(s_adc, s_buf, READ_BYTES, &got, 100);
  if (r != ESP_OK) return 0;
  uint32_t n = 0;
  for (uint32_t i = 0; i + SOC_ADC_DIGI_RESULT_BYTES <= got; i += SOC_ADC_DIGI_RESULT_BYTES) {
    adc_digi_output_data_t *p = (adc_digi_output_data_t *)&s_buf[i];
    if (ADC_SAMPLE_CH(p) != (uint32_t)s_chan) continue;
    fn((float)ADC_SAMPLE_VAL(p));
    n++;
  }
  return n;
}

static void print_frame() {
  lifi_frame_t *fr = &s_dm.frame;
  bool printable = true;
  for (int i = 0; i < fr->len; i++)
    if ((fr->payload[i] < 0x20 || fr->payload[i] > 0x7E) && fr->payload[i] != '\t') printable = false;

  bool bert = fr->len == LIFI_BERT_LEN && lifi_popcount16((uint16_t)(fr->payload[0] ^ LIFI_BERT_MARKER)) <= 2;
  if (bert) {
    uint16_t e = lifi_bert_errors(fr->payload);
    s_bert_frames++;
    s_bert_bits += LIFI_BERT_PRBS_BYTES * 8;
    s_bert_errs += e;
    int seq = fr->payload[1];
    if (s_bert_last_seq >= 0 && fr->ok) {
      int gap = (seq - s_bert_last_seq - 1) & 0xFF;
      if (gap < 128) s_bert_lost += gap;
    }
    if (fr->ok) s_bert_last_seq = seq;
  }

  Serial.printf("#FRAME,%d,%d,%d,%.1f,%.1f,%.3f,%u,%u,%u,", fr->ok, fr->fec, fr->len, s_dm.frame_rssi_db,
                s_dm.frame_snr_db, s_dm.frame_quality, fr->corrected, s_dm.frame_phase, s_dm.phase_moves);
  for (int i = 0; i < fr->len; i++) Serial.printf("%02x", fr->payload[i]);
  Serial.println();
  if (bert) {
    Serial.printf("#BERT,%lu,%lu,%lu,%.3e,%lu\n", (unsigned long)s_bert_frames, (unsigned long)s_bert_bits,
                  (unsigned long)s_bert_errs, s_bert_bits ? (double)s_bert_errs / s_bert_bits : 0.0,
                  (unsigned long)s_bert_lost);
  } else if (printable) {
    Serial.printf("RX %s \"%.*s\"\n", fr->ok ? "ok" : "CRC-FAIL", fr->len, (const char *)fr->payload);
  } else {
    Serial.printf("RX %s <%u bytes binary>\n", fr->ok ? "ok" : "CRC-FAIL", fr->len);
  }
}

static void reset_stats() {
  s_bert_frames = s_bert_bits = s_bert_errs = s_bert_lost = 0;
  s_bert_last_seq = -1;
  s_dm.syncs = s_dm.frames = s_dm.crc_fail = 0;
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(300);
  Serial.println("#READY rx_esp32 Li-Fi BFSK");
  if (!adc_begin()) {
    Serial.println("#ERR ADC continuous init failed");
    while (true) delay(1000);
  }
#if AUTO_CAL_FS
  // Measure the real sample rate (the ESP32 ADC DMA clock is not exact).
  uint32_t n = 0;
  int64_t t0 = esp_timer_get_time();
  while (esp_timer_get_time() - t0 < 1000000) n += adc_pump([](float) {});
  s_fs = (float)n * 1e6f / (float)(esp_timer_get_time() - t0);
#endif
  lifi_demod_init(&s_dm, s_fs, RATE_BPS, F0_HZ, F1_HZ);
  Serial.printf("#INFO,fs_req=%lu,fs_used=%.1f,f0=%.0f,f1=%.0f,rate=%.0f,spb=%.2f,gpio=%d\n", (unsigned long)FS_HZ, s_fs,
                F0_HZ, F1_HZ, RATE_BPS, s_dm.spb, ADC_GPIO);
  s_last_stat = millis();
}

void loop() {
  s_samples += adc_pump([](float x) {
    if (lifi_demod_push(&s_dm, x) == 2) print_frame();
  });

  uint32_t now = millis();
  if (now - s_last_stat >= STAT_PERIOD_MS) {
    float fs_meas = (float)(s_samples - s_samples_at_stat) * 1000.0f / (float)(now - s_last_stat);
    float amp = s_dm.last_amp0 > s_dm.last_amp1 ? s_dm.last_amp0 : s_dm.last_amp1;
    Serial.printf("#STAT,%lu,%.0f,%lu,%lu,%lu,%lu,%lu,%lu,%.3e,%.1f\n", (unsigned long)now, fs_meas,
                  (unsigned long)s_dm.syncs, (unsigned long)s_dm.frames, (unsigned long)s_dm.crc_fail,
                  (unsigned long)s_bert_frames, (unsigned long)s_bert_bits, (unsigned long)s_bert_errs,
                  s_bert_bits ? (double)s_bert_errs / s_bert_bits : 0.0, 20.0f * log10f(amp + 1e-9f));
    s_last_stat = now;
    s_samples_at_stat = s_samples;
  }

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "!reset") { reset_stats(); Serial.println("#OK reset"); }
    else if (cmd == "!info") Serial.printf("#INFO,fs_used=%.1f,f0=%.0f,f1=%.0f,rate=%.0f\n", s_fs, F0_HZ, F1_HZ, RATE_BPS);
  }
}
