#!/usr/bin/env python3
# =============================================================================
#  Warm OmniVoice TTS worker for "Talk to Caine".
#  Loads OmniVoice ONCE (the slow part), then answers requests on stdin and
#  writes results on stdout — so each spoken reply is ~2s instead of a 3-min
#  model reload. Runs inside .venv_omnivoice; spawned + kept warm by the Party
#  Server. Protocol: one JSON object per line.
#     in : {"text": "...", "lang": "en|fr", "out": "C:/path/reply.wav"}
#     out: {"ok": true, "out": "..."}   or   {"ok": false, "error": "..."}
#  First line emitted is {"ready": true} (or {"ready": false, "error": ...}).
# =============================================================================
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The parent talks to us over a strict JSON-per-line protocol on STDOUT. Library chatter
# (torch/transformers progress bars, CUDA warnings, the engine's "building short reference…"
# prints) would corrupt that stream, so we point Python's stdout at STDERR (which the parent
# discards) and emit the protocol JSON only via the SAVED real stdout handle.
_PROTO = sys.stdout
sys.stdout = sys.stderr

def emit(obj):
    _PROTO.write(json.dumps(obj) + "\n"); _PROTO.flush()

try:
    import torch, soundfile as sf
    import make_caine_voice as cv
    from omnivoice import OmniVoice
    from omnivoice.models.omnivoice import OmniVoiceGenerationConfig
    dev   = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=dev, dtype=dtype, load_asr=False)
    REF_AUDIO, REF_TEXT = cv.clone_ref("en")
    REF_TEXT = REF_TEXT or None
    # Push-to-talk's OWN settings (cv.talk_knob, fewer steps = faster). ONE config for EN+FR: OmniVoice
    # infers the language from the text, and French renders BETTER with the EN config (lower guidance)
    # than a separate higher-guidance "FR" one — so we never pass a French-specific tag.
    _gc = OmniVoiceGenerationConfig(num_step=cv.talk_knob("steps", "en"), guidance_scale=cv.talk_knob("guidance", "en"))
    GC = {"en": _gc, "fr": _gc}
    emit({"ready": True, "device": dev})
except Exception as e:
    emit({"ready": False, "error": str(e)[:300]})
    sys.exit(1)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req  = json.loads(line)
        text = (req.get("text") or "").strip()
        lang = req.get("lang", "en")
        out  = req["out"]
        if not text:
            emit({"ok": False, "error": "empty text"}); continue
        audio = model.generate(text=text, ref_audio=REF_AUDIO, ref_text=REF_TEXT,
                               generation_config=GC.get(lang, GC["en"]))
        wav = audio[0] if isinstance(audio, (list, tuple)) else audio
        if hasattr(wav, "detach"):
            wav = wav.detach().cpu().numpy()
        sf.write(out, wav, 24000)
        emit({"ok": True, "out": out})
    except Exception as e:
        emit({"ok": False, "error": str(e)[:300]})
