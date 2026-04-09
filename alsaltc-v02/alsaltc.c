/*
 * alsaltc - ALSA capture -> libltc decoder -> prints HH:MM:SS:FF (one per frame)
 *          + optional dropout detection (prints "NO_LTC" on stdout)
 *
 * Build:
 *   gcc -O2 -Wall -Wall alsaltc.c -o alsaltc $(pkg-config --cflags --libs ltc) -lasound -lm -lpthread
 *
 * Example:
 *   ./alsaltc -d hw:2,0 -r 48000 -c 1 -f 25 --channel 0 --dropout-ms 800 --format S32_LE
 */

#include <alsa/asoundlib.h>
#include <ltc.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t g_stop = 0;

static void on_sigint(int sig) {
    (void)sig;
    g_stop = 1;
}

static double now_mono_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static void usage(const char* prog) {
    fprintf(stderr,
        "Usage: %s [-d device] [-r rate] [-c channels] [-f fps] [--channel N] [--dropout-ms MS] [--format FMT]\n"
        "\n"
        "  -d device         ALSA capture device (default: hw:0,0)\n"
        "  -r rate           Sample rate (default: 48000)\n"
        "  -c channels       Capture channels requested from ALSA (default: 1)\n"
        "  -f fps            Expected FPS for apv calc (default: 25)\n"
        "  --channel N       Which channel to decode (0=left,1=right). Default: 0\n"
        "  --dropout-ms MS   If >0: emit 'NO_LTC' when no LTC frame received for MS milliseconds.\n"
        "                    Default: 0 (disabled)\n"
        "  --format FMT      Sample format (S16_LE or S32_LE). Default: S16_LE\n"
        "\n"
        "Examples:\n"
        "  %s -d hw:2,0 -r 48000 -c 1 -f 25 --channel 0 --dropout-ms 800 --format S32_LE\n"
        "  %s -d hw:2,0 -r 48000 -c 2 -f 25 --channel 1 --dropout-ms 500 --format S32_LE\n",
        prog, prog, prog);
}

/* Create or recreate decoder. queue_size>1 improves robustness. */
static LTCDecoder* make_decoder(unsigned int rate_set, double fps) {
    int apv = (int)((double)rate_set / fps + 0.5);
    if (apv <= 0) apv = (int)(rate_set / 25);

    /* queue size: 32 is still tiny but avoids corner cases with size=1 */
    LTCDecoder* dec = ltc_decoder_create(apv, 32);
    return dec;
}

/* Hard reset: drop decoder state and recreate. */
static void reset_decoder(LTCDecoder** dec, unsigned int rate_set, double fps,
                          int* last_h, int* last_m, int* last_s, int* last_f,
                          double* last_frame_s, bool* dropout_emitted,
                          double* start_s) {
    if (*dec) {
        ltc_decoder_free(*dec);
        *dec = NULL;
    }
    *dec = make_decoder(rate_set, fps);

    /* Force next valid frame to print immediately */
    *last_h = *last_m = *last_s = *last_f = -1;

    /* Dropout tracking reset */
    *last_frame_s = 0.0;
    *dropout_emitted = false;

    /* New reference for "no frames seen yet" */
    *start_s = now_mono_s();
}

int main(int argc, char** argv) {
    const char* device = "hw:0,0";
    unsigned rate = 48000;
    unsigned channels = 1;
    double fps = 25.0;
    int decode_channel = 0;      // 0=left, 1=right
    int dropout_ms = 0;          // 0 disables dropout output
    snd_pcm_format_t format = SND_PCM_FORMAT_S16_LE;  // Default format
    const char* format_str = "S16_LE";  // Default string

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-d") && i + 1 < argc) {
            device = argv[++i];
        } else if (!strcmp(argv[i], "-r") && i + 1 < argc) {
            rate = (unsigned)atoi(argv[++i]);
        } else if (!strcmp(argv[i], "-c") && i + 1 < argc) {
            channels = (unsigned)atoi(argv[++i]);
        } else if (!strcmp(argv[i], "-f") && i + 1 < argc) {
            fps = atof(argv[++i]);
        } else if (!strcmp(argv[i], "--channel") && i + 1 < argc) {
            decode_channel = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--dropout-ms") && i + 1 < argc) {
            dropout_ms = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--format") && i + 1 < argc) {
            format_str = argv[++i];
            if (!strcmp(format_str, "S16_LE")) {
                format = SND_PCM_FORMAT_S16_LE;
            } else if (!strcmp(format_str, "S32_LE")) {
                format = SND_PCM_FORMAT_S32_LE;
            } else {
                fprintf(stderr, "Invalid format: %s (use S16_LE or S32_LE)\n", format_str);
                return 2;
            }
        } else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
            usage(argv[0]);
            return 0;
        } else {
            fprintf(stderr, "Unknown arg: %s\n", argv[i]);
            usage(argv[0]);
            return 2;
        }
    }

    if (channels < 1 || channels > 2) {
        fprintf(stderr, "Unsupported channels=%u (use 1 or 2)\n", channels);
        return 2;
    }
    if (decode_channel < 0 || decode_channel > 1) {
        fprintf(stderr, "Invalid --channel %d (use 0 or 1)\n", decode_channel);
        return 2;
    }

    signal(SIGINT, on_sigint);
    signal(SIGTERM, on_sigint);

    snd_pcm_t* pcm;
    int err = snd_pcm_open(&pcm, device, SND_PCM_STREAM_CAPTURE, 0);
    if (err < 0) {
        fprintf(stderr, "ALSA open(%s) failed: %s\n", device, snd_strerror(err));
        return 1;
    }

    snd_pcm_hw_params_t* hw_params;
    snd_pcm_hw_params_alloca(&hw_params);
    err = snd_pcm_hw_params_any(pcm, hw_params);
    if (err < 0) {
        fprintf(stderr, "snd_pcm_hw_params_any: %s\n", snd_strerror(err));
        snd_pcm_close(pcm);
        return 1;
    }

    err = snd_pcm_hw_params_set_access(pcm, hw_params, SND_PCM_ACCESS_RW_INTERLEAVED);
    if (err < 0) {
        fprintf(stderr, "set_access: %s\n", snd_strerror(err));
        snd_pcm_close(pcm);
        return 1;
    }

    err = snd_pcm_hw_params_set_format(pcm, hw_params, format);
    if (err < 0) {
        fprintf(stderr, "ALSA set format %s: %s\n", format_str, snd_strerror(err));
        snd_pcm_close(pcm);
        return 1;
    }

    err = snd_pcm_hw_params_set_rate_near(pcm, hw_params, &rate, 0);
    if (err < 0) {
        fprintf(stderr, "set_rate: %s\n", snd_strerror(err));
        snd_pcm_close(pcm);
        return 1;
    }

    unsigned ch_set = channels;
    err = snd_pcm_hw_params_set_channels(pcm, hw_params, ch_set);
    if (err < 0) {
        fprintf(stderr, "ALSA set channels %u: %s\n", ch_set, snd_strerror(err));
        snd_pcm_close(pcm);
        return 1;
    }

    err = snd_pcm_hw_params(pcm, hw_params);
    if (err < 0) {
        fprintf(stderr, "snd_pcm_hw_params: %s\n", snd_strerror(err));
        snd_pcm_close(pcm);
        return 1;
    }

    snd_pcm_uframes_t frames = 128;  // Small buffer for low latency
    err = snd_pcm_set_params(pcm, format, SND_PCM_ACCESS_RW_INTERLEAVED, ch_set, rate, 1, 500000);
    if (err < 0) {
        fprintf(stderr, "snd_pcm_set_params: %s\n", snd_strerror(err));
        snd_pcm_close(pcm);
        return 1;
    }

    snd_pcm_prepare(pcm);

    size_t sample_bytes = (format == SND_PCM_FORMAT_S16_LE) ? 2 : 4;
    size_t frame_bytes = sample_bytes * ch_set;
    size_t buf_size = frames * frame_bytes;

    void* interleaved = malloc(buf_size);
    if (!interleaved) {
        fprintf(stderr, "OOM\n");
        snd_pcm_close(pcm);
        return 5;
    }

    ltcsnd_sample_t* mono = (ltcsnd_sample_t*)calloc(frames, sizeof(ltcsnd_sample_t));
    if (!mono) {
        fprintf(stderr, "OOM\n");
        free(interleaved);
        snd_pcm_close(pcm);
        return 5;
    }

    LTCDecoder* dec = NULL;
    int last_h = -1, last_m = -1, last_s = -1, last_f = -1;
    double last_frame_s = 0.0;
    bool dropout_emitted = false;
    double start_s = now_mono_s();

    reset_decoder(&dec, rate, fps, &last_h, &last_m, &last_s, &last_f, &last_frame_s, &dropout_emitted, &start_s);

    uint64_t sample_pos = 0;

    while (!g_stop) {
        snd_pcm_sframes_t got = snd_pcm_readi(pcm, interleaved, frames);

        if (got == -EPIPE) {
            snd_pcm_prepare(pcm);
            reset_decoder(&dec, rate, fps, &last_h, &last_m, &last_s, &last_f, &last_frame_s, &dropout_emitted, &start_s);
            continue;
        } else if (got < 0) {
            fprintf(stderr, "ALSA read error: %s\n", snd_strerror((int)got));
            snd_pcm_prepare(pcm);
            usleep(20000);
            reset_decoder(&dec, rate, fps, &last_h, &last_m, &last_s, &last_f, &last_frame_s, &dropout_emitted, &start_s);
            continue;
        } else if (got == 0) {
            usleep(10000);
            continue;
        }

        // Extract selected channel to mono buffer and scale to ltcsnd_sample_t (0-255)
        const int ch_idx = (ch_set == 1) ? 0 : decode_channel;
        for (snd_pcm_sframes_t i = 0; i < got; i++) {
            if (format == SND_PCM_FORMAT_S16_LE) {
                int16_t *samples = (int16_t*)interleaved;
                int16_t v = samples[i * ch_set + ch_idx];
                mono[i] = (ltcsnd_sample_t)(((v + 32768) >> 8) & 0xFF);  // Scale S16 to 8-bit unsigned
            } else {  // S32_LE
                int32_t *samples = (int32_t*)interleaved;
                int32_t v = samples[i * ch_set + ch_idx];
                mono[i] = (ltcsnd_sample_t)(((v + 2147483648LL) >> 24) & 0xFF);  // Scale S32 to 8-bit unsigned
            }
        }

        ltc_decoder_write(dec, mono, (size_t)got, (ltc_off_t)sample_pos);
        sample_pos += (uint64_t)got;

        LTCFrameExt frame;

        while (ltc_decoder_read(dec, &frame)) {
            SMPTETimecode tc;
            ltc_frame_to_time(&tc, &frame.ltc, LTC_USE_DATE);

            int hh = tc.hours;
            int mm = tc.mins;
            int ss = tc.secs;
            int ff = tc.frame;

            if (hh != last_h || mm != last_m || ss != last_s || ff != last_f) {
                /* Decode date + timezone from user bits (SMPTE 309M via libltc).
                 * LTC_USE_DATE populates tc.years/months/days and tc.timezone[6]
                 * (e.g. "+0000" or "-0530"). */
                int year_2d = (int)tc.years;
                int month   = (int)tc.months;
                int day     = (int)tc.days;
                int year    = (year_2d < 70) ? 2000 + year_2d : 1900 + year_2d;
                bool has_date = (month >= 1 && month <= 12 && day >= 1 && day <= 31);
                bool has_tz   = has_date &&
                                (tc.timezone[0] == '+' || tc.timezone[0] == '-');

                if (has_date && has_tz) {
                    /* ltcdump -F compatible: "YYYY-MM-DD ±HHMM HH:MM:SS:FF" */
                    printf("%04d-%02d-%02d %.5s %02d:%02d:%02d:%02d\n",
                           year, month, day, tc.timezone, hh, mm, ss, ff);
                } else if (has_date) {
                    printf("%02d:%02d:%02d:%02d %04d-%02d-%02d\n",
                           hh, mm, ss, ff, year, month, day);
                } else {
                    printf("%02d:%02d:%02d:%02d\n", hh, mm, ss, ff);
                }
                fflush(stdout);

                last_h = hh; last_m = mm; last_s = ss; last_f = ff;
                last_frame_s = now_mono_s();
                dropout_emitted = false;
            }
        }

        if (dropout_ms > 0) {
            double now_s = now_mono_s();

            if (last_frame_s <= 0.0) {
                if (!dropout_emitted && (now_s - start_s) * 1000.0 >= (double)dropout_ms) {
                    printf("NO_LTC\n");
                    fflush(stdout);
                    dropout_emitted = true;

                    reset_decoder(&dec, rate, fps, &last_h, &last_m, &last_s, &last_f, &last_frame_s, &dropout_emitted, &start_s);
                }
            } else {
                if (!dropout_emitted && (now_s - last_frame_s) * 1000.0 >= (double)dropout_ms) {
                    printf("NO_LTC\n");
                    fflush(stdout);
                    dropout_emitted = true;

                    reset_decoder(&dec, rate, fps, &last_h, &last_m, &last_s, &last_f, &last_frame_s, &dropout_emitted, &start_s);
                }
            }
        }
    }

    free(mono);
    free(interleaved);
    if (dec) ltc_decoder_free(dec);
    snd_pcm_close(pcm);
    return 0;
}
