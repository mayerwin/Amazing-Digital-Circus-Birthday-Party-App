# Agent.md — Nora's Digital Circus party project

> **How to use:** open THIS folder (`Amazing-Digital-Circus-Birthday-Party-App/`) in Claude Code and say
> **"proceed"**. This is the full context + task list. The current open task is finishing the
> open-source voice models in `caine-voice/` (Section 6). Work locally — you CAN install packages,
> download weights, run models, and **listen** to the output. The previous (cloud) assistant could
> NOT run anything (no GPU, couldn't download torch), so the models in Section 3 are wired blind and
> need real verification by ear.

---

## 1. The project (most of it is DONE — context only)
A parent is hosting their child **Nora's 7th birthday party** (a weekend afternoon) with an
*Amazing Digital Circus* theme. Deliverables already built and finished — **do not edit unless asked**:
- **`Nora-Circus-Party-Guide.html`** — the phone run-of-day + adventure script + bilingual host lines.
- **`Circus-Print-Pack.html`** — printable badges, station signs, exit-door card, cue cards.
- **`caine-console/`** — the iPad app that narrates the 45-min adventure in Caine's voice, step by step
  (you press NEXT, playing "Bubble"). Plays `caine-console/audio/<model>/<clip>.wav` (English then French).
- **`venue/`** — (optional) your own photos + floor plan of the party space, to help plan the
  physical adventure. Empty by default; gitignored so your private photos never get committed.

**The only active work** is the voice cloning in **`caine-voice/`** (below).

## 2. The voice pipeline (`caine-voice/`)
Clones **Caine** (a booming circus ringmaster) to speak every adventure line, personalised with the
kids' names, in EN + FR. Key files:
- **`caine-voice/make_caine_voice.py`** — the engine: the lines, per-model generators, isolated-venv
  builder, Demucs isolation, Whisper transcription, CLI parsing. Generates into
  `caine-console/audio/<model>/<clip>.wav`.
- **`caine-voice/caine_studio_web.py`** — the **Party Server**: one app, three modes (`/guide`,
  `/console`, `/studio`) + the Talk-to-Caine pipeline + Sonos. Launched by **`Start Caine Party.bat`**
  in the project root. The Voice Studio (`/studio`) reads the `MODELS` dict; per-model knobs + Play.
- **`caine-voice/caine_ref_clean.wav`** — the reference voice to clone (already music-free). French
  clip optional (`caine_ref_fr_clean.*`). **French is OPTIONAL** — OmniVoice produces native French straight from the text.
- **`caine-voice/caine_ref.txt`** — transcript (auto-made by Whisper; needed by F5/Qwen3/OpenAudio).
- **`caine-voice/logs/`** — every run logged here. **Read these to debug.**

## 3. Current model state (in `make_caine_voice.py` -> `MODELS`)
| key | status | notes |
|---|---|---|
| `chatterbox` | ✅ WORKS | baseline, EN+FR. Sliders: exaggeration(0.8)/temperature(0.7). Clone fidelity was subpar by ear, so it's hidden in the Studio (the party used OmniVoice). |
| `xtts` | ⚠️ fragile | auto-pins `transformers<5` + `torch<2.9`. Verify it runs. |
| `f5` | ✅ WORKS | EN+FR. Auto-builds a SHORT matched reference (`caine_ref_f5.wav`+`.txt`, ≤~11s) so it no longer garbles — F5 clips refs >12s but keeps the full transcript, which wrecks its duration estimate. English-focused; FR carries an accent. |
| `qwen3` | ✅ runs on GPU (verify timbre by ear) | Qwen3-TTS-1.7B-Base clone (Apache-2.0). DOES clone from the sample; encodes ref ONCE (`create_voice_clone_prompt`) + `non_streaming_mode=True`. **LIKELY FIDELITY FIX: now clones from the SHORT 4s `caine_ref_f5.wav` via `clone_ref()`, not the full 46s clip** — Qwen3 is "a 3-second clone", so 46s was probably why it sounded weak. No `instruct`/style on the clone path (only on custom/design voices, which don't clone), so "Voice Design then Clone" isn't one call. |
| `openaudio` | ⚠️ EXPERIMENTAL | Fish-Speech S2 (~24GB GPU, 3-stage). Probably switch to MIT S1-mini for normal hardware. |

Each non-chatterbox model runs in its **own auto-built venv** (`caine-voice/.venv_<key>/`) via
`ensure_venv()` + `run_one_model()`, which re-invokes the script inside that venv (`CAINE_IN_VENV=1`).

## 4. Contract for adding/maintaining a model
Generator: `def gen_X(clips, outdir, force):` — `clips` is `(base, lang, text)` tuples. Write
`os.path.join(outdir, base+".wav")` (skip if exists & not `force`). Rules you MUST keep:
1. **Reference**: use `REFS[lang]` (path); transcript `open(REF_TXT).read()`; `lang` is `"en"`/`"fr"`.
2. **No fake fallback**: on failure, leave the clip **blank** + print `FAILED (left blank)`. NEVER copy
   another model's audio into this folder — it would silently corrupt the A/B comparison. (User was emphatic.)
3. **Descriptions**: `clip_desc(base)` = per-line emotion; `VOICE_DESC` = global character;
   `styled(base)` combines them. Use for instruct/description-aware models; clone-only models ignore them.
4. **Register**: add to `MODELS`; if it needs deps, add to `ISOLATED_ENVS` (`pip` + `check_code`, a python
   one-liner that must import cleanly — used to detect/repair a broken env). Repo-based models use the
   `repo`/`weights` pattern (see `openaudio` + `ensure_repo()`).
5. **Transcript-needing models**: add the key to the auto-`transcribe()` list in `run_one_model()`.
6. The Studio auto-detects new `MODELS` keys (checkbox + column) — no GUI edits needed.

## 5. How to test (every model — do it and LISTEN)
```
cd caine-voice
py make_caine_voice.py --model=qwen3 --test --force      # just the 2-clip welcome phrase
# listen: ../caine-console/audio/qwen3/test_en.wav  and  test_fr.wav
# or Studio: "Start Caine Party.bat" -> /studio -> tick the model -> "Test phrase" -> per-model Play
```
Always read `caine-voice/logs/` for the real error. Compare against `chatterbox/test_en.wav`.

---

## 6. TASKS (do in order; verify each by listening)

### T1 — Verify & improve **Qwen3** (highest priority; user's main complaint)
- STATUS (2026-06-18): introspected the REAL `qwen-tts` API in `.venv_qwen3`. Methods are
  `generate_voice_clone / create_voice_clone_prompt / generate_custom_voice / generate_voice_design /
  get_supported_speakers / get_supported_languages`. **Confirmed the clone uses the sample.** Applied:
  build the clone prompt ONCE (`create_voice_clone_prompt`) + reuse via `voice_clone_prompt=`, and
  `non_streaming_mode=True`, with a safe fallback to the per-clip `ref_audio`/`ref_text` call.
- **No clone+style call exists.** `instruct=` is only on `generate_custom_voice`/`generate_voice_design`
  (built-in/designed voice, NOT a clone of Caine). So "Voice Design then Clone" is not one call here.
  If wanted, it'd be two stages (design a styled voice, then clone toward Caine) — needs ear A/B; skipped
  for now to avoid breaking the working clone. `--voice-desc` stays plumbed but unused by the clone path.
- Still TODO **by ear** (CPU here is slow; GPU strongly preferred): judge fidelity; if weak try a SHORTER
  reference clip (like F5's `caine_ref_f5.wav`), `dtype=torch.bfloat16` (GPU), or **0.6B-Base**.
- Docs: https://github.com/QwenLM/Qwen3-TTS

> **T2–T6 STATUS (2026-06-18): RAN ON GPU (RTX 4070 Laptop, 8GB). 6 of 9 WORK** producing non-garbled
> audio: **chatterbox, f5, qwen3, omnivoice (FR, ~2s/sentence — the standout), indextts2 (EN only),
> cosyvoice (EN+FR)**. OmniVoice is the recommended new voice (fast + native French).
> Last 2 — ALL infra blockers cleared (gating via HF_TOKEN in SECRETS.env, disk via D:, GPU, env builds,
> downloads), now stuck on UPSTREAM library incompatibilities (not worth chasing — French is already
> covered 4× over):
>   • **openaudio** (s1-mini): weights download fine, encode stage works, but text2semantic's tokenizer
>     loads as None — checkpoint is custom `model_type='dual_ar'` which the current fish-speech+transformers
>     can't load. Would need pinning fish-speech to an s1-mini-matched commit. (Patched a separate
>     `content_sequence.visualize` None-crash; the real blocker is the tokenizer/dual_ar arch.)
>   • **higgs**: install fixed (requirements+editable, transformers 4.46.3), reaches model load, fails
>     `Padding_idx must be within num_embeddings` (transformers-version/config mismatch) — never even OOMs.
> Each model has its OWN venv (no shared torch) under `D:\AI\cache\audio\venvs\` — e.g. cosyvoice pins
> torch 2.3.1+cu121 without touching the others' 2.8.0+cu128.
> **Infra added this session:** CUDA torch auto-installed from the cu128 wheel index when a GPU is
> present (`cuda_index()`, auto-upgrades CPU-only envs; override `CAINE_TORCH_CUDA`). All clone models
> use the SHORT matched reference (`caine_ref_f5.wav`, via `clone_ref()`). Big caches relocated off
> your synced project folder to `D:\AI\cache\audio` (venvs/huggingface/pip) via `CACHE_ROOT`/`HF_HOME`. `ensure_repo()`
> generalised: repo_dir / recursive / install=editable|requirements / requirements_skip / pip_no_isolation
> / weights={id:subdir} / weights_sentinel. setuptools pinned <81 (81 removed pkg_resources).

### T2 — **IndexTTS-2** (`indextts2`) ✅ wired — emotion control (ENGLISH/Chinese; **NO French**)
- Verified: `from indextts.infer_v2 import IndexTTS2; tts=IndexTTS2(cfg_path="checkpoints/config.yaml",
  model_dir="checkpoints", use_fp16=..., use_cuda_kernel=False); tts.infer(spk_audio_prompt=REF, text,
  output_path, use_emo_text=True, emo_text=clip_desc(base), emo_alpha=0.6)`. **Audio-only — no ref_text.**
- French is NOT an output language → **French clips left blank** (gen_indextts2 skips non-`en`). ~8-12GB GPU.
- Install: git repo; official is `uv sync`, we try `pip install -e .` (may need manual `uv sync`). Licence: bilibili (non-commercial OK).

### T3 — **Higgs Audio v2** (`higgs`) ✅ wired — expressive, but HEAVY (English; ~24GB GPU, CUDA-only)
- Verified: `from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine` + `data_types`
  (`ChatMLSample, Message, AudioContent`). Clone = ChatML: system scene (`<|scene_desc_start|>..`) +
  user=ref_text + assistant=`AudioContent(raw_audio=<b64>, audio_url="placeholder")` + user=new text;
  then `engine.generate(ChatMLSample(messages), max_new_tokens=1024, temperature=0.3, ...)`. **Needs ref_text.**
- Weights `bosonai/higgs-audio-v2-generation-3B-base` + `bosonai/higgs-audio-v2-tokenizer` auto-download (~14GB).
  French not official (best-effort). Realistically a big-GPU/cloud job, not this laptop.

### T4 — **OmniVoice** (`omnivoice`) ✅ wired — 600+ langs incl **native French**, light/fast ⭐ best FR
- Verified: `pip install omnivoice`; `from omnivoice import OmniVoice; m=OmniVoice.from_pretrained(
  "k2-fsa/OmniVoice", device_map=..., dtype=..., load_asr=False); audio=m.generate(text, ref_audio=REF,
  ref_text=optional); sf.write(out, audio[0], 24000)`. **NO language arg** — French comes from French text.
  ~2.45GB weights, ~6-8GB GPU (CPU slow). Apache-2.0. No k2/icefall pain. Clean pip env.

### T5 — **CosyVoice 2** (`cosyvoice`) ✅ wired — clone **+ style** (`instruct2`); **French IS supported now**
- Correction to old note: current CosyVoice2/3 cards list **9 langs incl. French** → we generate EN+FR.
- Verified: `sys.path.insert(0,"<repo>/third_party/Matcha-TTS")` FIRST; `from cosyvoice.cli.cosyvoice import
  CosyVoice2; cosy=CosyVoice2("pretrained_models/CosyVoice2-0.5B", load_jit=False, load_trt=False, fp16=...)`.
  **`prompt_wav` must be a PATH now (not a tensor).** clone+style: `inference_instruct2(text,
  styled(base)+"<|endofprompt|>", REFS[lang], stream=False)` → yields dicts with `['tts_speech']`;
  `torchaudio.save(out, chunk['tts_speech'], cosy.sample_rate)`. ⚠️ Windows pynini/WeTextProcessing snag
  (conda-forge pynini==2.1.5, or our `text_frontend=False` retry). Apache-2.0.

### T6 — **OpenAudio** ✅ switched **S2 → S1-mini** (the right call for no-24GB-GPU hardware)
- Now uses `fishaudio/openaudio-s1-mini` (~0.5B, **~4GB VRAM, CPU possible**, French, CC-BY-NC-SA) via the
  SAME 3-stage CLI. Fixed a real bug: stage-2 `text2semantic` was **missing `--checkpoint-path`** (added,
  pointing at the s1-mini dir). Emotion tags are parenthesised `(excited)` (was `[..]`). S2/s2-pro stays
  the 24GB research-licence option if a big GPU appears. **Still experimental — verify the decode output
  filename (`fake.wav`) against the cloned repo's version.**

---

## 7. Guardrails
- **Free / open-weight models only.** Note licences (Fish S2 is research-only; prefer MIT/Apache).
- **Never** silently substitute one model's audio for another's.
- Everything stays **driven from the Studio** (auto-venv; no manual setup for the user).
- Big downloads are fine. GPU strongly preferred (CPU may be too slow to be usable).
- After a model works: update `caine-voice/README.md` model table + "Other models" section, and listen
  to a full `--test` before claiming success.
- The party's voice is **OmniVoice** (shortlist by ear: OmniVoice, IndexTTS-2, F5-TTS). Chatterbox / XTTS / Qwen3 / CosyVoice cloned Caine subpar and are hidden in the Studio. **Don't break OmniVoice.**

## 8. The lines (already built — context)
`build_clips()` ≈ 47 clips: narration `s01..s14`, per-kid reveals (`s03_<name>_<lang>`), named Gloink
carriers (`s05_carry` …). Roster: Nora=Pomni, Leo=Jax, Hugo=Kinger, Chloé=Ragatha, Theo=Gangle,
(Nina=Zooble, Max=Gummigoo if they come). `test_en/test_fr` = "Welcome to the Amazing Digital Circus!"
for quick checks.

---
*Tip: Claude Code auto-loads `CLAUDE.md`/`AGENTS.md`. If you want this picked up automatically every
session, copy it: `copy Agent.md AGENTS.md`.*
