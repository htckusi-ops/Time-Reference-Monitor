APP_TITLE = "Time Reference Monitor – Studio Bundeshaus"
APP_SUBTITLE = "PTP / NTP / optional LTC · Monitoring only"
FOOTER_TEXT = "Monitoring only – no time discipline is applied. • Programmed by markus.gerber@srgssr.ch"

# bounded in-memory event list (UI/API)
EVENTS_MAXLEN = 500

# how many events shown in UI table
EVENTS_UI_MAX = 60

# rolling counters windows default (seconds)
DEFAULT_GM_WINDOW_S = 48 * 3600
DEFAULT_ERROR_WINDOW_S = 3600

# DB defaults
DEFAULT_DB_PATH = "ptp_monitor.sqlite"
DEFAULT_DB_MAX_EVENTS = 5000
DB_TRIM_EVERY_N_INSERTS = 50

# UI defaults
DEFAULT_UI_REFRESH_MS = 20
DEFAULT_UI_API_POLL_MS = 250
DEFAULT_STALE_THRESHOLD_MS = 2000

# NTP & LTC snapshot refresh
DEFAULT_NTP_REFRESH_S = 0.25
DEFAULT_LTC_REFRESH_S = 0.25

# pmc timeout
PMC_TIMEOUT_S = 1.5

LTC_ALSA_DEVICE = "ltc_left_mono"
LTC_LEVEL_CHANNELS = 2
# Spectrum (on-demand) – uses RAM tmp dir to avoid SD writes
SPECTRUM_TMP_DIR = "/dev/shm"
SPECTRUM_DEFAULT_DEVICE = "ltc_left_mono"
SPECTRUM_SAMPLE_RATE = 48000
SPECTRUM_CHANNELS = 1
SPECTRUM_FORMAT = "S32_LE"
SPECTRUM_MAX_DURATION_S = 60
SPECTRUM_ALLOWED_DURATIONS_S = [5, 10, 20, 30, 60]
CLOCK_FONTS = [
    {"id": "seg7", "label": "Segment7 Standard", "family": "Segment7Standard", "file": "Segment7Standard.otf"},
    {"id": "mono", "label": "Mono (Fallback)", "family": None, "file": None},
]
CLOCK_DEFAULT_FONT_ID = "seg7"