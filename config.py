"""Clack configuration: every tunable in one place.

All modules import their settings from here (golden rule: config over hardcoding).
Values that other code and tests assert on (for example ``WINDOW_SAMPLES`` and
``SPEC_FRAMES``) are real module attributes, not comments, so they can be checked.

See CLACK_BUILD_PLAN.md section 8 for the canonical specification of these values.
"""

SEED = 42

# Audio
SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = "float32"
INPUT_DEVICE = "HyperX SoloCast"   # pinned at the venue by NAME (index-independent; sounddevice resolves it). None = system default.

# Keystroke window
WINDOW_MS = 200
PRE_ONSET_MS = 40
WINDOW_SAMPLES = int(SAMPLE_RATE * WINDOW_MS / 1000)   # 8820, defined (not a comment): test_config asserts it
ONSET_SEARCH_MS = 100          # training: search this far each side of a key event for the real acoustic onset

# Log-Mel spectrogram
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 64
FMIN = 0
FMAX = 22050
SPEC_FRAMES = WINDOW_SAMPLES // HOP_LENGTH + 1          # T, the fixed time dimension; test_config asserts it

# Onset detection (attack path)
ONSET_HP_CUTOFF_HZ = 1500
ONSET_FRAME_MS = 5
ONSET_K = 3.0                  # default; ambient calibration overrides this at attack startup
ONSET_MIN_GAP_MS = 60          # transient debounce: one physical press-onset yields one onset
ONSET_REFRACTORY_MS = 180      # keystroke refractory (attack path): collapse the press+release click pair of one keystroke into one onset. Below DEMO_MIN_GAP_MS so distinct keystrokes at the MVP cadence are kept.
CLEAN_ISOLATION_MS = 200       # training data quality: a keystroke whose nearest neighbor press-onset is closer than this has an overlapping window (the previous key's release or the next key's press bleeds in) and is flagged as contaminated for optional cleaning.
AMBIENT_CALIB_S = 2            # quiet room calibration at attack start to set the onset threshold dynamically

# Modes
ATTACK_DISABLES_KEYLOGGER = True   # in attack mode the pynput listener is never instantiated (provable mic-only)

# Key set (classes)
KEY_SET = list("abcdefghijklmnopqrstuvwxyz0123456789") + ["space"]

# Model
EMBED_DIM = 128
DROPOUT = 0.3

# Training
BATCH_SIZE = 64
EPOCHS = 60
LR = 1e-3
WEIGHT_DECAY = 1e-4
EARLY_STOP_PATIENCE = 8
SPLIT_BY_SESSION = True         # validate on a SEPARATE recording session, never a random split of one session

# Augmentation (train only)
AUG_NOISE_STD = 0.005
AUG_TIME_SHIFT_MS = 10
AUG_PITCH_SEMITONES = 1.0
SPECAUG_TIME_MASK = 6
SPECAUG_FREQ_MASK = 8

# Trainer (collection): two independent quotas for two separate sessions
TRAIN_SAMPLES_PER_KEY = 40      # Session A (training): collect until every key hits this
EVAL_SAMPLES_PER_KEY = 10       # Session B (held-out eval): a SEPARATE recording, ideally a different typist
TRAINER_PACED_GAP_MS = 550      # paced isolation for collection; the demo cadence is different (see MVP cadence)
TRAINER_MIN_TYPISTS = 2         # collect from 2-3 people so the model is not tuned to one pair of hands
DEMO_MIN_GAP_MS = 250           # MVP threat model: the guaranteed demo promises typing at >= this gap (~3-4 keys/sec)

# Correction
NGRAM_ORDER = 5
BEAM_WIDTH = 8
USE_LLM_CORRECTION = False
LLM_MODEL = None

# Defense
MASKER_BAND_HZ = (1000, 10000)   # default band; D2 tunes this to the measured keyboard
MASKER_LEVEL = 0.3               # default; D2 sweeps to find the minimum effective level
MASKER_LEVEL_STEPS = [0.1, 0.2, 0.3, 0.5]   # D2 sweep: pick the lowest that hits the target
MASKER_TARGET_RECOVERY = 0.20    # D2: lowest masking level that pushes recovery below this
MASKER_TRIGGERED = False         # Standard Shield = continuous while armed (guaranteed demo path). Triggered "Smart Shield" is a stretch, off by default (a triggered masker can fire after the identifying transient already reached the mic)
EXPOSURE_GRADE_BANDS = {"A": 0.15, "B": 0.25, "C": 0.40, "D": 0.60}  # Clack heuristic grade by recovery R; above D = F. A project heuristic, not an industry standard
FLEET_REPORTS_DIR = "data/reports"  # D3: each endpoint SAVES an audit report here; the dashboard reads saved reports (no live heartbeat infrastructure)

# Evaluation (see BUILD_EVAL.md)
EVAL_TOPK = [1, 3, 5]            # top-k recall levels to report

# Paths
DATA_DIR = "data"
RECORDINGS_DIR = "data/recordings"
DATASETS_DIR = "data/datasets"
MODELS_DIR = "data/models"
CORPUS_DIR = "data/corpus"
REPORTS_DIR = "data/reports"
