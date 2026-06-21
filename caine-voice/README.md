# 🤡 Caine Voice — make the iPad talk in Caine's voice

This turns the adventure lines into **spoken audio in Caine's voice**, which the **Caine Console** (the iPad app) plays one step at a time while you press NEXT and play Bubble.

It's deeply personalised: Caine **names each child**, gives each one a **character intro** at the reveal, names a **different kid to carry each Gloink**, and cheers **"Happy birthday, Nora!"** at the end.

**Languages:** general lines and lines to **Nora & Leo** are **English then French** (with a short pause between). Lines to the other kids (Hugo, Chloé, Sasha, Nina, Max) are **French only**. The console handles the English→pause→French playback.

**Several models, so you can pick the best.** The script generates the audio with up to three top voice-cloning models, into separate folders, and the console has a **VOICE switcher** at the top so you can A/B them and play whichever sounds most like Caine:

> **Final verdict (after ear-checking):** the shortlist is **OmniVoice** (the one used, native
> French + fast), **IndexTTS-2**, and **F5-TTS**. Chatterbox, XTTS, Qwen3-TTS and CosyVoice 2
> cloned Caine subpar and are hidden in the Studio; OpenAudio and Higgs are experimental. The
> table below is the fuller exploration log.

| Model | Why | Notes |
|---|---|---|
| **Chatterbox Multilingual** (Resemble AI) | SOTA open multilingual clone, MIT, **exaggeration** dial | EN + FR, runs, but the clone sounded subpar by ear, so it's **not in the final shortlist** (hidden in the Studio). |
| **Qwen3-TTS** (Alibaba, Apache-2.0) | Faithful **3-second voice clone**, EN + FR. | Auto-built env, ~1.7B. Clones from the **short** `caine_ref_f5.wav` (it's designed for ~3s refs — a long clip hurt fidelity). Clone path is timbre-only (no style instruction). |
| **XTTS v2** (Coqui) | Robust multilingual clone | EN + FR. Auto-built env. |
| **F5-TTS** | Very natural English | Auto-builds a **short (~4–11s) matched reference** so it doesn't garble (see below). French rough. Auto-built env. |
| **OmniVoice** (k2-fsa, Apache-2.0) | Multilingual clone with **native French** (600+ langs), light & fast | EN + FR. ~2.45 GB, ~6–8 GB GPU (CPU slow). Clean `pip` env. **Best French candidate.** ⚠️ wired, verify by ear. |
| **CosyVoice 2** (FunAudioLLM, Apache-2.0) | Clone **+ natural-language style** (`instruct2`) | EN + FR (current cards add French). ~4 GB GPU. ⚠️ **Windows:** needs the `pynini` workaround (below). Wired, verify by ear. |
| **OpenAudio / Fish-Speech S1-mini** | Inline `(emotion)` tags, 13 langs incl. French | EN + FR. **~4 GB VRAM** (CPU possible), 3-stage CLI. CC-BY-NC-SA (personal use OK). Switched off the 24 GB S2. ⚠️ wired, verify by ear. |
| **IndexTTS-2** (bilibili licence) | Emotion + duration control | **English/Chinese only — French left blank.** ~8–12 GB GPU. Installs via `uv` officially (we try `pip -e`). ⚠️ wired, verify by ear. |
| **Higgs Audio v2** (Boson AI, Apache-2.0 code) | Best open **emotional expressiveness** | English-focused (French best-effort). **Heavy: ~24 GB GPU, CUDA-only, ~14 GB weights.** ⚠️ wired, verify on a big GPU. |

Each ticked model runs in its **own auto-built environment**, so they never clash. If a model fails on a clip, that clip is **left blank** (shown as MISSING in the Studio) — it is **never** quietly filled in with another model's audio, so every A/B comparison is honest.

### Audio descriptions (holistic, LLM-style direction)
Every line carries a short **emotion cue** (e.g. the spooky Manor line is tagged "mysterious, hushed"; a win is "excited, celebratory"), plus a global **Voice description** (the Studio text box, default: "a booming, theatrical circus ringmaster…"). Models that understand it — **Qwen3-TTS** (as a style instruction) and **OpenAudio** (as inline `[tags]`) — use it to *act* the line; Chatterbox/XTTS/F5 ignore it and just read the text. Edit the global description in the Studio, or `--voice-desc="..."` on the CLI.

### The extra models are now wired — but verify them by ear (and most want a GPU)
All four below are integrated (generator + auto-built env + Studio column). They were wired from
each project's **current, verified API** (2026), but — like F5/Qwen3 were at first — they have **not
yet been ear-checked**, and most need a GPU this machine doesn't have. Recommended order to try
(lightest + French first): **OmniVoice → OpenAudio S1-mini → CosyVoice2 → IndexTTS-2 → Higgs**.

- **OmniVoice** (Apache-2.0) — 600+ languages incl. **native French**, ~40× real-time, ~2.45 GB. The
  best French candidate; language is taken from the text (no language flag). `pip install omnivoice`.
- **OpenAudio / Fish-Speech S1-mini** (CC-BY-NC-SA) — **switched here from the 24 GB S2**: ~4 GB VRAM
  (CPU possible), French, inline `(emotion)` tags. Same 3-stage CLI, small open weights (~1 GB).
- **CosyVoice 2** (Apache-2.0) — clone **+ natural-language style** in one call (`instruct2`); current
  cards now include **French**. ~4 GB GPU. ⚠️ Windows `pynini` install snag — see below.
- **IndexTTS-2** (bilibili licence, non-commercial OK) — emotion + duration control, but **English/
  Chinese only**, so its **French clips are left blank** (never faked). ~8–12 GB GPU.
- **Higgs Audio v2** (Apache-2.0 code) — top emotional expressiveness, but **English-focused** and
  **heavy (~24 GB GPU, CUDA-only)** — realistically a big-GPU / cloud job, not this laptop.

#### ⚠️ Windows note for CosyVoice (`pynini`)
CosyVoice's requirements pull `pynini`/`WeTextProcessing`, which have **no Windows wheels** and fail to
`pip`-build. If CosyVoice's auto-build fails, install pynini from conda-forge first, in its env:
`conda install -c conda-forge pynini==2.1.5`, then re-run. (The generator also retries with text
normalisation disabled, so short English/French lines often work even without pynini.) WSL2 or the
`sdbds/CosyVoice-for-windows` fork are smoother fallbacks. IndexTTS-2 officially installs via `uv`
(`uv sync`); we try `pip install -e .` automatically, but if it fails, `uv sync` in its `.venv_indextts2/index-tts` is the fix.

---

## 🎪 One app for the whole party — the Party Server
Double-click **`Start Caine Party.bat`** (in the project root) on the party laptop and **leave it
running**. It starts one local server (opens **http://localhost:8765**) that hosts **three modes** —
no loose HTML files to juggle:

- **`/guide`** — 🎤 **Bubble's Party Guide** (your tablet): run-of-day, the **Caine Soundboard** (tap EN/FR
  to make Caine speak through the tablet), and an **Adventure Remote** that drives Nora's console.
- **`/console`** — 🎪 **Caine's Console** (Nora's iPad): the step-by-step adventure, in OmniVoice.
- **`/studio`** — 🎛 the Voice Studio (below).

**On the iPad & tablet** (same WiFi), open the address the window prints, e.g. `http://party-laptop.local:8765/`
then tap a mode. The server binds to the LAN, so **allow it through the Windows firewall** when asked.
The single source of truth is `make_caine_voice.py` (roster, lines, host phrases, steps) — exposed at
`/api/game`, and every voice you hear is what the engine generated, so the screens stay consistent.

### Remote-control the adventure (don't touch her iPad)
Both screens share one step (`/api/adv`). On **Bubble's Guide → 🎪 The Adventure**, the **Adventure Remote**
(◀ Back · ↻ Replay · Next ▶ · tap a step to jump) advances **Nora's iPad** over the network — and her
console's own NEXT/BACK stay in sync too. Either device can drive; the audio plays on her iPad.

## The Voice Studio (tune & regenerate) — at `/studio`
In the Studio you can:
- **pick a model** (only the three judged best by ear are shown — see verdicts below; OmniVoice is selected by default),
- **tune per-model, per-language knobs** with sliders — e.g. OmniVoice's *Guidance* and *Diffusion steps*
  separately for English and French. Tweaks **save automatically** to `knobs.json` and are remembered next
  time; **↺ Revert to defaults** clears them.
- **⚡ Test phrase** or **▶ Full run**, watching the live log,
- **browse every clip** across models: **▶** plays it in the browser, and **🎲** *re-rolls a single clip*
  (generation is a bit random — re-rolling a weird French take often fixes it).

### Which models are worth using (verdict by ear, on an RTX 4070 8 GB)
- **OmniVoice — BEST.** Native French, ~2 s to generate a 10 s line. The recommended voice.
- **F5-TTS / IndexTTS-2 — next best.** F5 is EN+FR; **IndexTTS-2 is English-only** (its French clips stay blank).
- **chatterbox / xtts / qwen3 / cosyvoice — subpar by ear**, hidden in the Studio (still runnable from the CLI).
- **openaudio / higgs — don't work on this machine** (OpenAudio's `dual_ar` checkpoint won't load with the
  current fish-speech+transformers; Higgs needs ~24 GB VRAM). Wired and ready for a bigger GPU.

### Improving French (and re-rolling clips)
French is **cross-lingual** — it clones Caine's *English* voice into French, which occasionally destabilises
(a high-pitched "aigu" patch that then recovers). Two fixes, both in the Studio:
1. **Re-roll** the weird clips with **🎲** (often enough on its own).
2. Nudge **OmniVoice → Guidance (French)** up (default 3.0; try 3.5–4.0 for steadier, or down if it sounds harsh)
   and/or **Diffusion steps (French)** up. Then regenerate. The single best fix would be a **French reference
   clip** of Caine (from the show's French dub) as `caine_ref_fr.wav` — then French clones from a French voice.

Everything below is the same thing from the command line (`--only=<clip>` regenerates a single clip).

---

## Easiest way: one script does everything ⭐

1. Put a clean Caine clip named **`caine_ref.wav`** in this `caine-voice` folder (8–20s, English, no music).
   - (Only if you want to try F5 too: also add **`caine_ref.txt`** = the exact words spoken in that clip.)
2. Open a terminal in this folder and run:

   ```
   python make_caine_voice.py
   ```

It auto-installs each model, generates **every line in the right language(s) with the kids' names baked in**, and writes the audio into **`../caine-console/audio/<model>/`**. Open the console, use the VOICE buttons to pick the one you like, and you're done.

- **Just one model:** `python make_caine_voice.py --model chatterbox` (or `xtts`, `f5`).
- **Re-running is safe & resumable:** by default it **skips files that already exist** (isolated tracks and audio clips), so it only fills in what's missing — nothing is overwritten.
- **To refresh everything** (e.g. after swapping in a new `caine_ref.wav` or changing `EXAGGERATION`): add **`--force`**. That re-cleans the clip AND regenerates all the audio. Without `--force`, a new clip won't take effect because the old files are still there.
- **Heads-up:** different models want different PyTorch versions, so installing all three in one environment can clash. The cleanest is **one model per fresh environment / Colab runtime** — run `--model chatterbox`, then `--model xtts`, etc. The script already skips any model that won't install and tells you.

### Both attendance scenarios are already baked in
Audio is generated for **every** guest, including **Nina** and **Max**. Whether they get named on the day is just a **toggle in the console**, not a re-run:

- Open `caine-console/index.html` in a text editor, find the `ROSTER` near the top, and set `present:true`/`present:false` for each child. The reveal will name only the present kids. (Nina and Max default to `false`; flip them to `true` if they come.)

### No Python / no GPU?
Use the **Colab notebook** (`Caine_Voice_Colab.ipynb`) — same idea in your browser, free GPU. It generates the Chatterbox voice into `audio/chatterbox/`.

---

## Step 1 — Get a Caine reference clip (`caine_ref.wav`)

The models need one short, **clean** sample of the target voice — just Caine talking, ideally **no background music or sound effects**, about **8–20 seconds**.

Options:
- **Record your own** big, theatrical ringmaster voice — 100% yours, works great.
- **Capture a short clip** of Caine from the show for your own personal use (a moment where he talks over a quiet background). Save it as `.wav`.
- Mono, clear, his normal speaking range (not screaming), trim out music/silence.

### Cleaning music out of the clip — this is AUTOMATIC
Music or sound effects in the reference clip make the clone warbly, so **every normal run cleans the clip first** (with Demucs) before generating — you don't have to ask for it. It writes the cleaned files and an `audit.html` page right at the start.

If you'd rather clean **and stop** (to listen/check before the long generation), run:

```
python make_caine_voice.py --isolate
```

Either way you get files you can check, **and an `audit.html` page** to hear them: just **double-click `audit.html`** to open it in your browser and play each one. (To skip cleaning entirely on a clean clip, add `--no-isolate` or `--raw`.)

### Already cleaned the voice yourself? (e.g. lalal.ai)
If you've isolated the voice with another tool and have a clean, voice-only clip, just name it **`caine_ref_clean.mp3`** (or `.wav`) and drop it in this folder. When it's present, the script **converts it to WAV if needed, uses it directly, and skips Demucs entirely** — no `--no-isolate` flag needed. (For French, use `caine_ref_fr_clean.mp3/.wav`.) It takes priority over `caine_ref.wav`, and you can hear it in `audit.html`.
- **`caine_ref_vocals.wav`** — voice only (this is what gets used for cloning).
- **`caine_ref_music.wav`** — the music that was removed (so you can confirm it pulled the right thing out).

Play both in `audit.html`. The vocals file should be clean Caine speech; the music file should be just the backing. If the vocals still have music bleeding in, try a longer or cleaner source clip and run `--isolate` again, then refresh `audit.html`. Once you're happy, just run `python make_caine_voice.py` — it automatically uses `caine_ref_vocals.wav` from then on. (Clip already clean? Skip this, or force the original with `--raw`.)

## 🇫🇷 The French accent — how to fix it
Cloning Caine's **English** voice into French will always carry some English accent — that's how cross-language cloning works, not a bug. Two things help a lot:

1. **Give a French reference clip.** Drop a clip of Caine speaking French — e.g. from the show's **French dub** — into this folder as **`caine_ref_fr.wav`**. The script will then clone the **French** lines from the *French* Caine (natural French) and the English lines from your English clip. Run `--isolate` to clean it too (it handles both clips and adds them to `audit.html`).
2. **Lower the drama.** `EXAGGERATION` at the top of the script is now **0.5** (down from 0.7). Lower it toward `0.4` for an even cleaner, calmer read; raise toward `0.6` for more ham. Re-run with `--force`.

Also: **try all three models** and use the console's VOICE switcher — XTTS and Chatterbox handle French differently, and one may sound noticeably better to you on your clip. If none is great in French and you have no French clip, the cleanest option is to let Caine speak the French lines with a light accent (kids won't mind) or translate them yourself live as Bubble.

> Note: Caine is a character from *The Amazing Digital Circus* (© Glitch Productions). Cloning a voice here is for **personal, non-commercial** use — a private birthday party. Don't redistribute the audio or use it commercially.

---

## Step 2 — Where the audio ends up

After running, you'll have folders like:

```
caine-console/audio/
  chatterbox/  s01_en.wav  s01_fr.wav  s02_en.wav … s03_alyssa_en.wav  s03_noe_fr.wav  s05_carry_fr.wav …
  xtts/        (same filenames)
  f5/          (same filenames, if you ran F5)
```

Open `caine-console/index.html` on the iPad (see `caine-console/README.txt`). The **VOICE** buttons at the top switch between `chatterbox` / `xtts` / `f5`; a greyed-out button means that model's audio isn't there. If a clip is missing, the console just shows the words so you (Bubble) can read them — nothing breaks.

---

## Voice quality knobs (Chatterbox only)
Two sliders at the top of the Studio control the Chatterbox voice (XTTS/F5 ignore them):

- **Exaggeration** (default **0.80**) — emotion/intensity. 0.5 = normal, 0.8 = very dramatic (great for a ringmaster). Higher is more theatrical but can drift from the exact timbre.
- **Temperature** (default **0.70**) — randomness. **Lower = more faithful/steady** to the reference voice (try 0.5–0.7 for the most accurate clone); higher = more varied/expressive.

From the command line these are `--exaggeration=0.80 --temperature=0.70` (and `--cfg=` to force the guidance weight). Re-run with `--force` to re-generate with new settings.

**What makes the clone most faithful, in order of impact:** (1) a clean, ~10–20s reference clip — you've got that with the lalal clip; (2) **lower temperature** (0.5–0.7); (3) moderate **exaggeration** — very high values trade faithfulness for drama; (4) `cfg` around 0.3–0.5 for steady pacing (for French from an English clip it's auto-set to 0 to avoid an English accent).

## 🎮 GPU / CUDA (automatic)
Plain `pip install torch` gives a **CPU-only** build on Windows, so the models would crawl even with
an NVIDIA card. The script now detects your GPU (`nvidia-smi`) and installs the **CUDA** PyTorch wheel
(`cu128`) into each model's environment — and **auto-upgrades** any env that was built CPU-only. No
action needed. Overrides via env var: `CAINE_TORCH_CUDA=cu126` (older driver) or `CAINE_TORCH_CUDA=cpu`
(force CPU). On an 8 GB card, chatterbox/qwen3/f5/xtts/OmniVoice/CosyVoice/OpenAudio-S1-mini fit;
IndexTTS-2 is tight (fp16) and **Higgs (~24 GB) will not fit 8 GB** (it OOMs → those clips stay blank).
*(Chatterbox runs in the main Python, not a per-model env; it stays on whatever torch that has — upgrade
the system torch if you want it on the GPU too.)*

## 💾 Where the big files live (D:\AI\cache\audio)
The model environments and downloaded weights are **multi-GB each** (a CUDA PyTorch alone is ~3.5 GB),
so they do **not** live in this project folder (which may be inside a cloud-synced folder). They go on a roomy drive:
- **`D:\AI\cache\audio\venvs\`** — one auto-built Python environment per model (`.venv_f5`, `.venv_qwen3`, …)
- **`D:\AI\cache\audio\huggingface\`** — downloaded model weights (`HF_HOME`)
- **`D:\AI\cache\audio\pip\`** — cached pip wheels (so the 3.5 GB torch downloads once, not per model)

This is automatic: the script uses `D:\AI\cache\audio` when a `D:\AI` folder exists. Override the location
with the **`CAINE_CACHE_ROOT`** env var (it's also set as a persistent user variable, alongside `HF_HOME`
and `PIP_CACHE_DIR`). Everything here is **rebuildable** — delete a `.venv_*` folder to force a clean
re-install, or the whole `D:\AI\cache\audio` to reclaim space (models simply re-download next run).

## A short reference clip is best (all clone models)
Most voice cloners (F5, Qwen3 "a 3-second clone", OmniVoice, OpenAudio, CosyVoice, IndexTTS-2) clone
**better from a short 3–10s sample** — several explicitly warn that a >20s reference *degrades* quality.
So they all reuse the short, transcript-matched `caine_ref_f5.wav` / `.txt` (see below) instead of the
full ~46s clip. This is automatic; it's also the most likely reason Qwen3 sounded weak before.

## Auto-transcribe for F5 (Whisper)
F5 needs a transcript of your clip. The Studio's **📝 Transcribe (F5)** button (or `python make_caine_voice.py --transcribe`) runs a **fast Whisper** (`faster-whisper`, CPU-friendly, no torch) to auto-write `caine_ref.txt`. It also happens automatically the first time you generate F5. Check/edit `caine_ref.txt` afterwards if Whisper misheard a word.

### Why F5 needs a *short* reference (the "garbled voice" fix)
F5 guesses how long each generated line should be from the **ratio of reference-audio length to reference-text length**, and it silently **clips any reference longer than ~12s**. So if you hand it a 46s clip but the full 46s transcript, it thinks Caine speaks ~4× faster than he does and **crams every line into a fraction of a second** — fast, garbled noise. To avoid this, F5 generation first builds **`caine_ref_f5.wav`** (the first few whole sentences of your clip, ≤~11s) together with **`caine_ref_f5.txt`** (the transcript of *exactly* that snippet), and clones from those. This is automatic; delete the two files (or run with `--force`) to rebuild them after swapping your reference clip.

## Troubleshooting
- **XTTS / F5 environments are now automatic.** Chatterbox and XTTS need different `transformers` versions, so they can't share one Python environment. You don't have to manage this: when you generate **xtts** (or **f5**) from the Studio, the script **auto-builds a dedicated environment under the hood** (`.venv_xtts` / `.venv_f5`, one-time, a few minutes the first time) and runs the model there. Just tick the model in the Studio and click **⚡ Test phrase** — the result appears in the comparison columns when it finishes.
- **F5 sounds fast / garbled / robotic** → F5 was given a reference clip longer than ~12s with a full transcript. Fixed automatically now: F5 builds a short matched `caine_ref_f5.wav` + `caine_ref_f5.txt` and clones from those (see *"Why F5 needs a short reference"* above). If you swapped your reference clip, delete those two files or re-run with `--force` to rebuild them. (F5's French is weak — mainly useful for English.)
- **A model won't install** → run it alone in a fresh environment: `python make_caine_voice.py --model xtts`. Or use Colab (fresh runtime per model).
- **French has an English twang** → that's the English reference clip showing through; it usually suits Caine. For cleaner French, use a French reference clip (Chatterbox uses cfg=0 for French to minimise this).
- **Audio won't play on the iPad** → tap **▶ Play Caine** once (Safari needs one tap before auto-play); after that each step auto-plays.
