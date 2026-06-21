#!/usr/bin/env python3
# =============================================================================
#  make_caine_voice.py  —  ONE script, MANY models, EN + FR.
#
#  Generates every Caine line for Nora's party in Caine's voice, personalised
#  with the kids' names, using SEVERAL top voice-cloning models so you can pick
#  the one that sounds best. Audio goes to ../caine-console/audio/<model>/ and
#  the console has a model switcher to A/B them.
#
#  ABOUT THE FRENCH ACCENT
#  Cloning an ENGLISH voice (Caine's) into French always carries some English
#  accent — that's a limit of cross-language cloning, not a bug. Best fixes:
#    1) Give a FRENCH reference clip too:  caine_ref_fr.wav  (e.g. a clip of
#       Caine from the show's FRENCH DUB). Then French lines clone from the
#       French Caine = natural French, while English lines use caine_ref.wav.
#    2) Lower EXAGGERATION (below) — cleaner, less artefacty.
#    3) Compare models with the console's VOICE switcher and keep the best.
#
#  MODELS (best-effort; any that fail to install are skipped):
#    chatterbox : Chatterbox Multilingual (Resemble AI) — SOTA, MIT, EN+FR,
#                 emotion "exaggeration" control.
#    xtts       : XTTS v2 (Coqui) — robust multilingual clone, EN+FR.
#    f5         : F5-TTS — very natural English. Needs caine_ref.txt (transcript).
#
#  HOW TO USE
#    1. Put a Caine clip here:  caine_ref.wav  (~8-20s English).
#       Optional but recommended for clean French:  caine_ref_fr.wav (French dub).
#       For F5 also add caine_ref.txt = the words spoken in caine_ref.wav.
#       ALREADY cleaned the voice yourself (e.g. lalal.ai)?  Name it
#       caine_ref_clean.mp3 (or .wav). If present it's converted to wav and used
#       directly, and Demucs isolation is BYPASSED. (French: caine_ref_fr_clean.*)
#    2. Generate:
#         python make_caine_voice.py                  (all models)
#         python make_caine_voice.py --model chatterbox
#         python make_caine_voice.py --models chatterbox,xtts
#       Add --force to overwrite.  Add --raw to skip isolation/use the raw clip.
#
#  QUICK TEST: generate ONLY a short welcome phrase (test_en.wav / test_fr.wav) to
#  check a clip / model / accent fast:
#         python make_caine_voice.py --test --model chatterbox
#
#  ISOLATION IS AUTOMATIC: every normal run first cleans the reference voice with
#  Demucs (writing caine_ref_vocals.wav, caine_ref_music.wav, and audit.html), then
#  generates from the clean voice. So the isolated tracks always appear right at the
#  start. To isolate ONLY and stop (to audit before the long generation), run:
#         python make_caine_voice.py --isolate
#  then open audit.html in a browser. (Use --no-isolate to skip cleaning entirely.)
#
#  Personal, non-commercial use (a private birthday party). Use reference clips
#  you sourced yourself and keep the generated audio private.
# =============================================================================

import os, sys, subprocess, csv, unicodedata, glob, shutil, tempfile, time

# ----------------------------------------------------------------------------
# CAST.  'bilingual': True -> English + French.  False -> French only.
# ----------------------------------------------------------------------------
ROSTER = [
    {"name": "Nora", "character": "Pomni",    "bilingual": True,  "star": True},
    {"name": "Leo",  "character": "Jax",      "bilingual": True},
    {"name": "Hugo",    "character": "Kinger",   "bilingual": False},
    {"name": "Chloé",    "character": "Ragatha",  "bilingual": False},
    {"name": "Sasha",   "character": "Zooble",   "bilingual": False},  # new player (took Nina's Zooble role)
    {"name": "Nina",   "character": "Gangle",   "bilingual": False},  # optional (90% absent) — Gangle is free now
    {"name": "Max",   "character": "Gummigoo", "bilingual": False},  # optional (90% absent) — Nina's sister
]

CHAR_INTRO = {
    "Pomni":    {"en": "the brave new jester who leads the way",
                 "fr": "le nouveau clown courageux qui ouvre la voie"},
    "Jax":      {"en": "the cheeky purple trickster",
                 "fr": "le petit malin violet, le farceur"},
    "Kinger":   {"en": "the wise, wonderfully wobbly chess king",
                 "fr": "le roi des échecs, sage et tout tremblant"},
    "Ragatha":  {"en": "the kindest ragdoll in the whole circus",
                 "fr": "la poupée de chiffon la plus gentille du cirque"},
    "Gangle":   {"en": "the gentle one with the happy little mask",
                 "fr": "la plus douce, avec son joli petit masque"},
    "Zooble":   {"en": "the coolest mix-and-match adventurer",
                 "fr": "l'aventurier le plus cool, fait de mille morceaux"},
    "Gummigoo": {"en": "the brave cowboy of the Candy Canyon",
                 "fr": "le courageux cowboy du Canyon de Bonbons"},
}

CARRIERS = {
 "s05": {"bilingual": False,  # Chloé
   "en": "And the keeper of the RED Gloink is… CHLOÉ! When you find it, players, give it straight to Chloé — she will keep it safe!",
   "fr": "Et la gardienne du Gloink ROUGE, c'est… CHLOÉ ! Quand vous le trouvez, les joueurs, donnez-le vite à Chloé — elle le gardera bien !"},
 "s07": {"bilingual": False,  # Hugo
   "en": "The keeper of the YELLOW Gloink is… HUGO! Find it and hand it to Hugo to carry, players!",
   "fr": "Le gardien du Gloink JAUNE, c'est… HUGO ! Trouvez-le et donnez-le à Hugo, c'est lui qui le porte, les joueurs !"},
 "s09": {"bilingual": True,   # Leo
   "en": "The keeper of the PURPLE Gloink is… LEO! Solve the riddle, find the Gloink, and give it to Leo — guard it well!",
   "fr": "Le gardien du Gloink VIOLET, c'est… LEO ! Résolvez l'énigme, trouvez le Gloink, et donnez-le à Leo — protégez-le bien !"},
 "s11": {"bilingual": True,   # Nora
   "en": "And the keeper of the very last one, the BLUE Gloink, is our birthday hero… NORA! Find it and give it to Nora to carry to the Exit Door!",
   "fr": "Et le gardien du tout dernier, le Gloink BLEU, c'est notre héroïne du jour… NORA ! Trouvez-le et donnez-le à Nora, c'est elle qui le porte jusqu'à la Porte de Sortie !"},
}

# ---- Chatterbox voice knobs (these only affect the 'chatterbox' model) ----
EXAGGERATION = 0.80   # emotion/intensity. 0.5 normal .. 0.8 very dramatic (Caine!).
TEMPERATURE  = 0.70   # randomness. LOWER (0.5-0.7) = more faithful/steady to the reference voice.
CFG_OVERRIDE = None   # None = auto per-language; or force a number (0.0-0.7). Lower = slower, clearer.
CFG_EN       = 0.35   # default guidance for English lines
# (XTTS / F5 ignore all of the above.)

# ============================================================================
#  PER-MODEL, PER-LANGUAGE KNOBS  (the Studio exposes these as sliders)
#  Each knob has a per-language default (keys of "default" = the languages it applies to).
#  Tweaks are saved to knobs.json next to this script and read back by knob(); the Studio's
#  "Revert to defaults" just deletes those overrides. Cross-lingual French (cloning an English
#  voice into French) is the wobbly case, so French defaults are tuned a bit stronger.
# ============================================================================
KNOBS = {
    "omnivoice": {
        "_label": "OmniVoice — BEST (native French, ~2s/line)",
        "guidance": {"label": "Guidance (faithfulness / steadiness)", "min": 1.0, "max": 5.0, "step": 0.1,
                     "default": {"en": 2.0, "fr": 3.0}},
        "steps":    {"label": "Diffusion steps (quality, slower)",   "min": 8,   "max": 80,  "int": True,
                     "default": {"en": 32, "fr": 48}},
    },
    "f5": {
        "_label": "F5-TTS — next best",
        "nfe":   {"label": "Steps / NFE (quality)",  "min": 8,   "max": 64,  "int": True, "default": {"en": 32,  "fr": 32}},
        "cfg":   {"label": "Guidance (cfg strength)", "min": 1.0, "max": 4.0, "step": 0.1, "default": {"en": 2.0, "fr": 2.0}},
        "speed": {"label": "Speed",                   "min": 0.5, "max": 1.5, "step": 0.05,"default": {"en": 1.0, "fr": 1.0}},
    },
    "indextts2": {
        "_label": "IndexTTS-2 — next best (English; French is experimental/accented)",
        "emo_alpha": {"label": "Emotion strength", "min": 0.0, "max": 1.0, "step": 0.05, "default": {"en": 0.6}},
    },
}
# Curated for the party: these three were judged best by ear. The others are hidden in the Studio.
RECOMMENDED_MODELS = ["omnivoice", "f5", "indextts2"]

# ---- Style / audio descriptions (used by description-aware models: qwen3, openaudio;
#      ignored by chatterbox / xtts / f5). VOICE_DESC = the overall character. ----
VOICE_DESC = "a booming, theatrical circus ringmaster: manic, gleeful, larger-than-life, playful"
CLIP_EMOTION = {
    "test": "booming theatrical ringmaster, building excitement",
    "s01":  "booming, theatrical, building anticipation",
    "s02":  "grand and manic, gleeful ringmaster announcement",
    "s03":  "playful, delighted showman",
    "s04":  "energetic, urgent, fun",
    "s05":  "excited and celebratory",
    "s06":  "silly, bossy, fast-paced",
    "s07":  "excited and celebratory",
    "s08":  "mysterious, spooky, hushed",
    "s09":  "excited and proud",
    "s10":  "alarmed but playful, urgent",
    "s11":  "triumphant and excited",
    "s12":  "suspenseful, building tension",
    "s13":  "triumphant, joyful, climactic",
    "s14":  "warm, fond, a grand farewell",
}
def clip_desc(base):
    """Short per-line emotion cue for a clip basename (e.g. 's05_carry_fr' -> 's05')."""
    for key in ["test"] + [f"s{n:02d}" for n in range(1, 15)]:
        if base.startswith(key):
            return CLIP_EMOTION.get(key, "")
    return ""

def slug(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())

def star_name():
    for k in ROSTER:
        if k.get("star"): return k["name"]
    return ROSTER[0]["name"]
STAR = star_name()

# ----------------------------------------------------------------------------
# Lines
# ----------------------------------------------------------------------------
GENERAL = {
 "s01": {"en": f"Headsets on, {STAR} and all you players! No peeking! In three, two, one, you are entering the Amazing Digital Circus!",
         "fr": f"Casques sur les yeux, {STAR} et tous les joueurs ! On ne triche pas ! Trois, deux, un, vous entrez dans le Cirque Numérique Fantastique !"},
 "s02": {"en": "OH-HO-HOOO! New players! I am CAINE, your magnificent ringmaster! Today's adventure is GATHER THE GLOINKS! Find four magic Gloinks, open the Exit Door, and win the greatest treasure of all!",
         "fr": "OH-HO-HOOO ! De nouveaux joueurs ! Je suis CAINE, votre magnifique présentateur ! L'aventure du jour, RASSEMBLEZ LES GLOINKS ! Trouvez quatre Gloinks magiques, ouvrez la Porte de Sortie, et gagnez le plus grand trésor de tous !"},
 "s04": {"en": "Goggles down and held tight, players? Here comes the magic… 3… 2… 1… ZAP! Goggles UP and look — Welcome to the Candy Canyon Kingdom! That sneaky Candy Bandit has scattered his STOLEN candy all over the land, and he's guarding it! Grab every piece and rush it back to your base bucket before time runs out — but BEWARE: if the Bandit tags you, run all the way back to base before you try again! Team up and trick him, players… ready… GO!",
         "fr": "Lunettes sur les yeux, bien accrochés, les joueurs ? Voici la magie… 3… 2… 1… ZAP ! Lunettes en haut, et regardez — Bienvenue au Royaume du Canyon de Bonbons ! Ce sournois Bandit des Bonbons a éparpillé ses bonbons VOLÉS dans tout le pays, et il les garde ! Attrapez chaque bonbon et rapportez-le vite dans le seau de votre base avant la fin du temps — mais ATTENTION : si le Bandit vous touche, retournez jusqu'à la base avant de réessayer ! Faites équipe et rusez, les joueurs… prêts… ALLEZ !"},
 "s05": {"en": "You beat the bandit! Now listen, players — a little RED Gloink is hiding somewhere very close by! He's a shy, giggly fellow, he's not far… look high, look low, and FIND him! Find the RED Gloink and that's your first — one down, three to go!",
         "fr": "Vous avez battu le bandit ! Écoutez, les joueurs — un petit Gloink ROUGE se cache tout près d'ici ! C'est un timide qui rigole, il n'est pas loin… cherchez en haut, cherchez en bas, et TROUVEZ-le ! Trouvez le Gloink ROUGE et ce sera le premier — un de pris, plus que trois !"},
 "s06": {"en": "Goggles down, players? Here comes the magic again… 3… 2… 1… ZAP! Goggles UP and look — Welcome to my Fast Food! The manager wants one perfect burger, bottom bun, patty, cheese, lettuce, tomato, top bun. All hands, build it NOW!",
         "fr": "Lunettes sur les yeux, les joueurs ? Encore de la magie… 3… 2… 1… ZAP ! Lunettes en haut, et regardez — Bienvenue à mon Fast Food ! La gérante veut un burger parfait, pain du bas, steak, fromage, salade, tomate, pain du haut. Tous ensemble, construisez-le MAINTENANT !"},
 "s07": {"en": "A perfect burger! The manager is SO happy! Quick — a YELLOW Gloink is hiding nearby, the cheeky little fellow! Hunt high and low, look behind and under… find him! That makes TWO Gloinks!",
         "fr": "Un burger parfait ! La gérante est trop contente ! Vite — un Gloink JAUNE se cache tout près, le petit coquin ! Cherchez en haut, en bas, derrière, dessous… trouvez-le ! Ça fait DEUX Gloinks !"},
 "s08": {"en": "Goggles down, players? Here comes the magic… 3… 2… 1… ZAP! Goggles UP and look — Welcome to the spooky Mildenhall Manor, ooooh! Somewhere in this dark room I have hidden FIFTEEN glowing stars — find every last one before your ninety seconds run out! Ready? Hunt, hunt, HUNT!",
         "fr": "Lunettes sur les yeux, les joueurs ? Voici la magie… 3… 2… 1… ZAP ! Lunettes en haut, et regardez — Bienvenue au manoir mystérieux de Mildenhall, ouuuh ! Quelque part dans cette pièce sombre, j'ai caché QUINZE étoiles brillantes — trouvez-les toutes avant la fin de vos quatre-vingt-dix secondes ! Prêts ? Cherchez, cherchez, CHERCHEZ !"},
 "s09": {"en": "MAGNIFICENT — you found all fifteen glowing stars! Now, my clever players, here is a riddle to find the hidden PURPLE Gloink. Listen closely… We come as a pair and we cover your toes, we keep them all warm wherever feet go. We sleep folded up somewhere cosy and deep — find where WE live, and the Gloink you will keep! Solve it and search… three Gloinks now, just one more!",
         "fr": "MAGNIFIQUE — vous avez trouvé les quinze étoiles brillantes ! Maintenant, mes petits malins, voici une énigme pour trouver le Gloink VIOLET caché. Écoutez bien… On va par deux pour couvrir tes orteils, et on les tient au chaud, quel beau travail ! On dort bien pliées tout au fond, à l'abri — trouvez où NOUS vivons, et le Gloink est ici ! Résolvez et cherchez… trois Gloinks, plus qu'un seul !"},
 "s10": {"en": "Goggles down — last teleport, players! Here comes the magic… 3… 2… 1… ZAP! Goggles UP and… UH OH — BUBBLE is glitching! Run and dodge his glitchy hands — if Bubble TAGS you, you're abstracted, so FREEZE like a statue until a friend frees you with a high-five! Survive together… GO!",
         "fr": "Lunettes sur les yeux — dernière téléportation, les joueurs ! Voici la magie… 3… 2… 1… ZAP ! Lunettes en haut et… OH NON — BUBBLE bugue ! Courez et esquivez ses mains qui buguent — si Bubble vous TOUCHE, vous êtes abstrait, alors figez-vous comme une statue jusqu'à ce qu'un ami vous libère avec un check ! Survivez ensemble… ALLEZ !"},
 "s11": {"en": "Now, my wonderful HUMANS — the very LAST Gloink, the BLUE one, is hiding nearby! Everybody hunt… find him and we will have ALL FOUR! Then quick, my players, to the Exit Door!",
         "fr": "Maintenant, mes merveilleux HUMAINS — le tout DERNIER Gloink, le BLEU, se cache tout près ! Tout le monde cherche… trouvez-le et nous aurons les QUATRE ! Puis vite, mes joueurs, à la Porte de Sortie !"},
 "s12": {"en": "Goggles down… here comes the magic… 3… 2… 1… ZAP! Goggles UP — there it is, the mighty EXIT DOOR! All four Gloinks are here, but the door needs the secret Gloink CODE. Tap the four colours on my magic terminal… let me see… BLUE… PURPLE… YELLOW… RED… ahh, but in WHICH order?! Hmmm! Only YOU know, my clever players — think hard: in what order did you find your Gloinks? Take all the time you need… no rushing!",
         "fr": "Lunettes sur les yeux… voici la magie… 3… 2… 1… ZAP ! Lunettes en haut — la voilà, la grande PORTE DE SORTIE ! Les quatre Gloinks sont là, mais la porte a besoin du CODE Gloink secret. Tapez les quatre couleurs sur mon terminal magique… voyons voir… BLEU… VIOLET… JAUNE… ROUGE… ahh, mais dans QUEL ordre ?! Hmmm ! Vous seuls le savez, mes petits malins — réfléchissez bien : dans quel ordre avez-vous trouvé vos Gloinks ? Prenez tout le temps qu'il faut… pas de précipitation !"},
 "s13": {"en": "The code is COMPLETE! Push the Exit Door… and it swings WIDE OPEN! You did it, my magnificent heroes — you have ESCAPED the Amazing Digital Circus! And now, for your reward… somewhere very close, I have HIDDEN your treasure — a chest full of goodies! Hunt high, hunt low… find your treasure!",
         "fr": "Le code est COMPLET ! Poussez la Porte de Sortie… et elle s'ouvre EN GRAND ! Vous avez réussi, mes magnifiques héros — vous vous êtes ÉCHAPPÉS du Cirque Numérique Fantastique ! Et maintenant, votre récompense… tout près d'ici, j'ai CACHÉ votre trésor — un coffre plein de surprises ! Cherchez partout… trouvez votre trésor !"},
 "s14": {"en": f"You FOUND it — the treasure is YOURS, a goodie bag for every single hero! MAGNIFICENT! You were the bravest, cleverest players the circus has ever seen. And now… do I smell something DELICIOUS? It is CAKE TIME! Everybody, follow Bubble to the birthday cake — and a great big HAPPY BIRTHDAY, {STAR}!",
         "fr": f"Vous l'avez TROUVÉ — le trésor est à VOUS, un sac de surprises pour chaque héros ! MAGNIFIQUE ! Vous êtes les joueurs les plus courageux et les plus malins que le cirque ait jamais vus. Et maintenant… est-ce que je sens quelque chose de DÉLICIEUX ? C'est l'heure du GÂTEAU ! Tout le monde, suivez Bubble vers le gâteau d'anniversaire — et un grand JOYEUX ANNIVERSAIRE, {STAR} !"},
}

REVEAL_INTRO = {"en": "Now hold still, players, because my circus has turned each of you into a brand-new character!",
                "fr": "Ne bougez plus, les joueurs, car mon cirque a transformé chacun de vous en un nouveau personnage !"}
REVEAL_OUTRO = {"en": "Players, on the count of three, open your eyes and meet yourselves! Three, two, one, EYES OPEN!",
                "fr": "Joueurs, à trois, ouvrez les yeux et découvrez qui vous êtes ! Trois, deux, un, OUVREZ LES YEUX !"}

def kid_intro(kid, lang):
    nm, ch = kid["name"], kid["character"]; desc = CHAR_INTRO[ch][lang]
    return f"{nm}! You are {ch.upper()}, {desc}!" if lang == "en" else f"{nm} ! Tu es {ch.upper()}, {desc} !"

# ----------------------------------------------------------------------------
# HOST phrases — Caine punctuating the WHOLE party (not just the adventure). Bubble
# triggers these from the Party Guide (an EN button + a FR button per phrase). Generated
# as host_<key>_<lang>.wav. cat = soundboard group; label = short button caption.
# ----------------------------------------------------------------------------
HOST = {
 "welcome":  {"cat":"Arrivals","label":"New player!",
   "en":"OH-HO-HOOO! A new player has entered the Amazing Digital Circus! Welcome, welcome, welcome!",
   "fr":"OH-HO-HOOO ! Un nouveau joueur entre dans le Cirque Numérique Fantastique ! Bienvenue, bienvenue, bienvenue !"},
 "gather":   {"cat":"Arrivals","label":"Gather round (Bubble talks)",
   "en":"Players, players! Gather round, gather round! My wonderful helper Bubble has something to say!",
   "fr":"Les joueurs, les joueurs ! Rassemblez-vous, rassemblez-vous ! Mon merveilleux assistant Bubble a quelque chose à dire !"},
 # Caine formally introduces YOU (Bubble) right after the hype — a fake Q&A you pace yourself:
 # play one clip, answer out loud with what you already know, play the next. Establishes Bubble
 # as Caine's trusted helper so the kids treat you well. Suggested answers are in the Party Guide.
 "meet_bubble1":{"cat":"🎤 Meet Bubble","label":"1 · Introduce Bubble + ‘all here?’",
   "en":"And now, my magnificent players — let me introduce my number-one helper in the real world… everybody, say hello to BUBBLE! Bubble, Bubble, come here — let me ask you a few things, right in front of everyone. First: are ALL of my wonderful players here and ready today?",
   "fr":"Et maintenant, mes magnifiques joueurs — laissez-moi vous présenter mon assistant numéro un dans le monde réel… tout le monde, dites bonjour à BUBBLE ! Bubble, Bubble, viens ici — laisse-moi te poser quelques questions, devant tout le monde. D'abord : est-ce que TOUS mes merveilleux joueurs sont là et prêts aujourd'hui ?"},
 "meet_bubble2":{"cat":"🎤 Meet Bubble","label":"2 · ‘How many players?’",
   "en":"WONDERFUL! Hee-hee-hee! Now tell me, Bubble — how MANY brave little players do we have for today's adventure?",
   "fr":"MERVEILLEUX ! Hi-hi-hi ! Maintenant dis-moi, Bubble — COMBIEN de courageux petits joueurs avons-nous pour l'aventure d'aujourd'hui ?"},
 "meet_bubble3":{"cat":"🎤 Meet Bubble","label":"3 · ‘Who is the birthday star?’",
   "en":"What a MAGNIFICENT crowd! And one more thing, my friend — tell me, WHO is our special birthday star today, and how old is she turning?",
   "fr":"Quelle MAGNIFIQUE foule ! Et une dernière chose, mon ami — dis-moi, QUI est notre étoile d'anniversaire aujourd'hui, et quel âge fête-t-elle ?"},
 "meet_bubble4":{"cat":"🎤 Meet Bubble","label":"4 · Treat Bubble well — don't erase him!",
   "en":f"{STAR}! Turning SEVEN! Oh, how MAGNIFICENT — today the whole circus is for YOU! Now listen closely, my players: Bubble here is MY trusted helper in your world. He looks after all the important bits — the logistics, the little jobs, and the clever advice — whenever you need him. So you must treat Bubble VERY well: be kind, listen to him, and whatever you do… do NOT erase him! No abstracting my Bubble — hee-hee-hee — we NEED him! Now go and play, my magnificent players… and get ready, because very soon, we go on a GREAT adventure together!",
   "fr":f"{STAR} ! SEPT ans ! Oh, comme c'est MAGNIFIQUE — aujourd'hui, tout le cirque est pour TOI ! Maintenant écoutez bien, les joueurs : Bubble, ici présent, est mon assistant de confiance dans votre monde. Il s'occupe de tout ce qui est important — la logistique, les petites tâches, et les conseils malins — chaque fois que vous en avez besoin. Alors traitez très bien Bubble : soyez gentils, écoutez-le, et surtout… ne l'effacez PAS ! Pas question d'abstraire mon Bubble — hi-hi-hi — on a besoin de lui ! Maintenant allez jouer, mes magnifiques joueurs… et tenez-vous prêts, car très bientôt, nous partons ensemble pour une GRANDE aventure !"},
 "myshow":   {"cat":"Arrivals","label":"I run the show!",
   "en":f"OH-HO-HOOO! This is {STAR}'s party… and I am the one who is running the show!",
   "fr":f"OH-HO-HOOO ! C'est la fête d'{STAR}… et c'est MOI qui dirige le spectacle !"},
 "lunch":    {"cat":"Food & water","label":"Lunchtime!",
   "en":"ATTENTION, magnificent players! It is FUEL-UP time! To the table — pizza and sushi await! Even a ringmaster must eat!",
   "fr":"ATTENTION, magnifiques joueurs ! C'est l'heure de FAIRE LE PLEIN ! À table — pizzas et sushis vous attendent ! Même un présentateur doit manger !"},
 "eatup":    {"cat":"Food & water","label":"Eat up",
   "en":"Eat up, my players! You will need ALL of your energy for the great adventure to come!",
   "fr":"Mangez bien, mes joueurs ! Vous aurez besoin de TOUTE votre énergie pour la grande aventure à venir !"},
 "water":    {"cat":"Food & water","label":"Drink water",
   "en":"It is a HOT day in my circus! Everybody — drink some water! Glug, glug, glug… aaah, magnificent!",
   "fr":"Quelle chaleur dans mon cirque ! Tout le monde — buvez de l'eau ! Glou, glou, glou… aaah, magnifique !"},
 "calm":     {"cat":"Settle down","label":"Big breath",
   "en":"Easy now, my players! Even a glitch must breathe. A big circus breath… iiiin… and ouuut. Lovely!",
   "fr":"Du calme, mes joueurs ! Même un bug doit respirer. Une grande respiration de cirque… on inspiiire… et on souffle. Magnifique !"},
 "quiet":    {"cat":"Settle down","label":"Shhh secret",
   "en":"Shhh! Listen! Caine has a SECRET… and you must be quiet as a tiny mouse to hear it! Shhhhh!",
   "fr":"Chut ! Écoutez ! Caine a un SECRET… et il faut être silencieux comme une petite souris pour l'entendre ! Chuuut !"},
 "countdown":{"cat":"Energy","label":"3-2-1 GO!",
   "en":"Are you ready, players? In three… two… one… HERE… WE… GOOO!",
   "fr":"Vous êtes prêts, les joueurs ? Dans trois… deux… un… C'EST… PARTIIII !"},
 "warmup":   {"cat":"Energy","label":"Shake it out",
   "en":"Time to wiggle out the glitches, players! Shake your arms, shake your legs, and… FREEZE! Ha-ha!",
   "fr":"Il est temps de chasser les bugs, les joueurs ! Secouez les bras, secouez les jambes, et… FIGEZ-VOUS ! Ha-ha !"},
 "cheer":    {"cat":"Energy","label":"Magnificent!",
   "en":"MAGNIFICENT, players! Absolutely MAGNIFICENT! Caine is SO very proud of you!",
   "fr":"MAGNIFIQUE, les joueurs ! Absolument MAGNIFIQUE ! Caine est si fier de vous !"},
 "wow":      {"cat":"Energy","label":"Ooooh!",
   "en":"OOOOH! Did you SEE that?! MAGNIFICENT! Again, again, do it again! Hee-hee-hee!",
   "fr":"OOOOH ! Vous avez VU ça ?! MAGNIFIQUE ! Encore, encore, recommencez ! Hi-hi-hi !"},
 "winner":   {"cat":"Energy","label":"We have a winner",
   "en":"We have a WINNER! Take a bow, magnificent player — the whole circus applauds YOU!",
   "fr":"Nous avons un GAGNANT ! Salue bien bas, magnifique joueur — tout le cirque t'applaudit !"},
 "joke1":    {"cat":"Jokes","label":"Gloink joke",
   "en":"Why did the Gloink cross the circus? To get to the OTHER side of the screen! Ah-ha-ha-haaa!",
   "fr":"Pourquoi le Gloink a-t-il traversé le cirque ? Pour aller de l'AUTRE côté de l'écran ! Ah-ha-ha-haaa !"},
 "joke2":    {"cat":"Jokes","label":"Windows joke",
   "en":"Why was the computer cold at the circus? Because it left all its WINDOWS open! Hee-hee!",
   "fr":"Pourquoi l'ordinateur avait-il froid au cirque ? Parce qu'il avait laissé toutes ses FENÊTRES ouvertes ! Hi-hi !"},
 "joke3":    {"cat":"Jokes","label":"Clown count",
   "en":"How many clowns does it take to run a circus? Just ONE… if that clown is CAINE! Ho-ho-hooo!",
   "fr":"Combien de clowns faut-il pour faire tourner un cirque ? Un seul… si ce clown, c'est CAINE ! Ho-ho-hooo !"},
 "almost":   {"cat":"Big moments","label":"Adventure soon",
   "en":"Players… something BIG is coming. The great adventure is almost here. Get… ready…!",
   "fr":"Les joueurs… quelque chose de GRAND arrive. La grande aventure est presque là. Préparez-vous… !"},
 "hype":     {"cat":"Big moments","label":"Hype the adventure!",
   "en":"Gather round, my magnificent players, gather round! Something INCREDIBLE is about to begin! The Amazing Digital Circus needs YOU for a grrrreat ADVENTURE — we will travel to magical worlds, gather four magic Gloinks, and unlock the greatest treasure of all! So tell me, players… ARE… YOU… READY… to go on an ADVENTURE?!",
   "fr":"Rassemblez-vous, mes magnifiques joueurs, rassemblez-vous ! Quelque chose d'INCROYABLE va commencer ! Le Cirque Numérique Fantastique a besoin de VOUS pour une grrrande AVENTURE — nous allons voyager dans des mondes magiques, rassembler quatre Gloinks magiques, et déverrouiller le plus grand trésor de tous ! Alors dites-moi, les joueurs… ÊTES… VOUS… PRÊTS… à partir à l'AVENTURE ?!"},
 "cake":     {"cat":"Big moments","label":"Cake time!",
   "en":"Do I smell… DELICIOUS magic?? It is CAKE TIME, players! Everybody, to the birthday cake!",
   "fr":"Est-ce que je sens… de la magie DÉLICIEUSE ?? C'est l'heure du GÂTEAU, les joueurs ! Tout le monde, vers le gâteau d'anniversaire !"},
 "birthday": {"cat":"Big moments","label":"Happy birthday",
   "en":f"Happy birthday, {STAR}! SEVEN years old — the most magnificent player in the whole circus! Hip, hip… HOORAY!",
   "fr":f"Joyeux anniversaire, {STAR} ! SEPT ans — la joueuse la plus magnifique de tout le cirque ! Hip, hip… HOURRA !"},
 "presents": {"cat":"Big moments","label":"Presents!",
   "en":f"Presents?! Caine LOVES presents! Gather round, players, while {STAR} opens her magnificent treasures!",
   "fr":f"Des cadeaux ?! Caine ADORE les cadeaux ! Rassemblez-vous, les joueurs, pendant qu'{STAR} ouvre ses magnifiques trésors !"},
 "photo":    {"cat":"Big moments","label":"Photo: say Gloink!",
   "en":"Freeze, players, and STRIKE A POSE! Three… two… one… say GLOOOINK! Magnificent!",
   "fr":"Figez-vous, les joueurs, et PRENEZ LA POSE ! Trois… deux… un… dites GLOOOINK ! Magnifique !"},
 "slide":    {"cat":"Big moments","label":"Slide is open",
   "en":"The great water slide is… OPEN! Splash, slide and play, my magnificent players! Wheeee!",
   "fr":"Le grand toboggan est… OUVERT ! Glissez, plongez et jouez, mes magnifiques joueurs ! Whiiii !"},
 "tidy":     {"cat":"Big moments","label":"Tidy up",
   "en":"A tidy circus is a HAPPY circus! Let us clean up faster than a glitch — ready… GO!",
   "fr":"Un cirque bien rangé est un cirque HEUREUX ! Rangeons plus vite qu'un bug — prêts… ALLEZ !"},
 "goodbye_all":{"cat":"Farewells","label":"Goodbye, everyone!",
   "en":"The circus must close for today, players… but you were ALL magnificent! Until next time… goodbye, goodbye!",
   "fr":"Le cirque doit fermer pour aujourd'hui, les joueurs… mais vous avez tous été magnifiques ! À la prochaine… au revoir, au revoir !"},
 "glitch":   {"cat":"Fun","label":"Bzzt glitch",
   "en":"Buzz! Buzz! Did somebody say… GLITCH?? Hee-hee, careful, players — the circus is feeling SILLY today!",
   "fr":"Buzz ! Buzz ! Quelqu'un a dit… BUG ?? Hi-hi, attention, les joueurs — le cirque est d'humeur FARCEUSE aujourd'hui !"},

 # Caine speaking to Bubble (YOU) — gives you cover to do the physical bits. Trigger from
 # the guide with EN / FR / BOTH buttons. cat groups them together on the soundboard.
 "bub_headsets":{"cat":"Caine → Bubble","label":"Hand out headsets",
   "en":"Bubble, my faithful assistant! Be a dear and hand a headset to each of my players, would you?",
   "fr":"Bubble, mon fidèle assistant ! Sois gentil et donne un casque à chacun de mes joueurs, veux-tu ?"},
 "bub_badges":{"cat":"Caine → Bubble","label":"Stick the badges",
   "en":"Bubble! While their eyes are closed, sneak around and press a character badge onto each little player!",
   "fr":"Bubble ! Pendant qu'ils ont les yeux fermés, faufile-toi et colle un badge de personnage sur chaque petit joueur !"},
 "bub_lead":{"cat":"Caine → Bubble","label":"Lead them on",
   "en":"Bubble, my friend — lead my magnificent players to the next world! Follow Bubble, everyone!",
   "fr":"Bubble, mon ami — conduis mes magnifiques joueurs vers le monde suivant ! Tout le monde, suivez Bubble !"},
 "bub_candy":{"cat":"Caine → Bubble","label":"Scatter the candy",
   "en":"Bubble, quick — scatter the candy across the kingdom for the bandit game! Chop-chop!",
   "fr":"Bubble, vite — éparpille les bonbons dans le royaume pour le jeu du bandit ! Allez, hop hop !"},
 "bub_burger":{"cat":"Caine → Bubble","label":"Set out burger",
   "en":"Bubble, lay out the burger pieces on the table — the manager is SO hungry!",
   "fr":"Bubble, dispose les morceaux du burger sur la table — la gérante a tellement faim !"},
 "bub_lights":{"cat":"Caine → Bubble","label":"Dim the lights",
   "en":"Bubble, be a dear and dim the lights for the spooky manor… ooooh, spooky!",
   "fr":"Bubble, sois gentil et baisse les lumières pour le manoir hanté… ouuuh, ça fait peur !"},
 "bub_torches":{"cat":"Caine → Bubble","label":"Lights off — find the stars!",
   "en":"Bubble, lights OFF! My fifteen glowing stars are hidden in the dark — send my players to find every last one!",
   "fr":"Bubble, lumières ÉTEINTES ! Mes quinze étoiles brillantes sont cachées dans le noir — envoie mes joueurs les trouver toutes !"},
 "bub_gloink":{"cat":"Caine → Bubble","label":"Gloink is hidden, start the hunt",
   "en":"Bubble, you magnificent helper — the next Gloink is hidden and waiting! Send my brave players off to FIND the shy little fellow!",
   "fr":"Bubble, magnifique assistant — le prochain Gloink est caché et il attend ! Envoie mes courageux joueurs TROUVER ce petit timide !"},
 "bub_gather":{"cat":"Caine → Bubble","label":"Gather at the door",
   "en":"Bubble, gather ALL of my players at the Exit Door — the grand finale is near!",
   "fr":"Bubble, rassemble TOUS mes joueurs devant la Porte de Sortie — le grand final approche !"},
 "bub_door":{"cat":"Caine → Bubble","label":"Open the door",
   "en":"Bubble, on my signal… push open the Exit Door and reveal the treasure!",
   "fr":"Bubble, à mon signal… ouvre grand la Porte de Sortie et révèle le trésor !"},
 "bub_water":{"cat":"Caine → Bubble","label":"Water round",
   "en":"Bubble! A round of water for my hard-working players, if you please!",
   "fr":"Bubble ! Un tour d'eau pour mes joueurs qui travaillent si fort, s'il te plaît !"},
 "bub_proud":{"cat":"Caine → Bubble","label":"Aren't they clever",
   "en":"Ooh, Bubble — look how clever these players are! Aren't they just magnificent?",
   "fr":"Ooh, Bubble — regarde comme ces joueurs sont malins ! Ne sont-ils pas tout simplement magnifiques ?"},

 # The STAKES — references "abstraction" as the danger. Play this at the start of the adventure
 # to make it feel important: finish together, or be abstracted forever.
 "stakes":{"cat":"⚠️ Story & stakes","label":"The stakes (abstraction!)",
   "en":"Listen VERY closely, players — this is important! There is one rule in the Amazing Digital Circus: you must finish the adventure TOGETHER. Because any player who gives up, or wanders off alone… gets ABSTRACTED — turned into a glitchy little scribble, FOREVER! Oooh! So be brave, stay together, gather the four Gloinks… and you will ALL get home heroes!",
   "fr":"Écoutez TRÈS attentivement, les joueurs — c'est important ! Il y a une seule règle dans le Cirque Numérique Fantastique : vous devez finir l'aventure TOUS ENSEMBLE. Car le joueur qui abandonne, ou qui part tout seul… se fait ABSTRAIRE — transformé en petit gribouillage qui bugue, POUR TOUJOURS ! Ouuuh ! Alors soyez courageux, restez ensemble, rassemblez les quatre Gloinks… et vous rentrerez tous à la maison en héros !"},
 "abstract_warn":{"cat":"⚠️ Story & stakes","label":"Abstraction warning!",
   "en":"Uh-oh, players — I feel a GLITCH coming! Stay TOGETHER, or it will ABSTRACT you into scribbles! Quick — stick together, be brave!",
   "fr":"Oh-oh, les joueurs — je sens un BUG arriver ! Restez ENSEMBLE, ou il va vous ABSTRAIRE en gribouillages ! Vite — serrez-vous les coudes, soyez courageux !"},
 "together":{"cat":"⚠️ Story & stakes","label":"Stay together!",
   "en":"Together, players, TOGETHER! That is how heroes beat the glitches! Caine believes in you!",
   "fr":"Ensemble, les joueurs, ENSEMBLE ! C'est comme ça que les héros battent les bugs ! Caine croit en vous !"},
 # Reusable hunt nudges — sprinkle while the kids search each station for its hidden Gloink.
 "gloink_hunt":{"cat":"🔍 Gloink hunt","label":"A Gloink is hiding — find him!",
   "en":"Oooh, players — I can feel it! A little Gloink is hiding very close by, the shy giggly fellow! He's not far at all… look high, look low, behind and underneath… FIND him!",
   "fr":"Ouuuh, les joueurs — je le sens ! Un petit Gloink se cache tout près, ce petit timide qui rigole ! Il n'est pas loin du tout… cherchez en haut, en bas, derrière et dessous… TROUVEZ-le !"},
 "gloink_warm":{"cat":"🔍 Gloink hunt","label":"Warmer… warmer!",
   "en":"Warmer… warmer… OOOH, you are SO close now — I can hear that little Gloink giggling! Keep looking, keep looking, you have almost got him!",
   "fr":"Ça chauffe… ça chauffe… OUUUH, vous êtes tout PRÈS maintenant — j'entends ce petit Gloink rigoler ! Continuez à chercher, continuez, vous l'avez presque !"},
 # Teleport DEPART cue — play it as you LEAVE a station and walk the kids over. The magic
 # "3-2-1 ZAP!" reveal lives on the console's next station step, so YOU trigger it on arrival.
 "teleport_go":{"cat":"🌀 Teleport","label":"Teleport — goggles down, follow Bubble",
   "en":"Goggles DOWN over your eyes, my players — into the swirly portal we go! Hold your Gloinks tight and follow Bubble… off to a brand-new world!",
   "fr":"Lunettes SUR LES YEUX, mes joueurs — on entre dans le portail magique ! Serrez bien vos Gloinks et suivez Bubble… direction un tout nouveau monde !"},

 # ---- 🧠 HUMAN TEST (trivia) — run AFTER surviving Station 4, BEFORE the last Gloink. ----
 # Bubble picks questions from the GUIDE (never shown on the kids' console). Each player must
 # get at least one right; then the others answer. 5 about the show + 15 general (7-10yo).
 "human_test":{"cat":"🧠 Human test","label":"Intro — prove you're human!",
   "en":"You SURVIVED my glitch — but wait, wait, WAIT! How do I know you are real HUMANS and not sneaky little glitches in disguise?? It is time for… THE HUMAN TEST! Answer my questions, my players, and PROVE you are human! Everybody must get at least one right!",
   "fr":"Vous avez SURVÉCU à mon bug — mais attendez, attendez, ATTENDEZ ! Comment savoir si vous êtes de vrais HUMAINS et pas de petits bugs déguisés ?? C'est l'heure du… TEST HUMAIN ! Répondez à mes questions, mes joueurs, et PROUVEZ que vous êtes humains ! Chacun doit en trouver au moins une !"},
 "human_correct":{"cat":"🧠 Human test","label":"Correct! (human confirmed)",
   "en":"CORRECT! Hee-hee-hee! A REAL human, confirmed — no glitch could ever be so clever!",
   "fr":"CORRECT ! Hi-hi-hi ! Un VRAI humain, c'est confirmé — aucun bug ne pourrait être aussi malin !"},
 "human_pass":{"cat":"🧠 Human test","label":"All human! (test passed)",
   "en":"MAGNIFICENT! Every single one of you is a REAL, marvellous HUMAN! You ALL passed the Human Test! Now… on to the very last Gloink!",
   "fr":"MAGNIFIQUE ! Vous êtes tous de VRAIS et merveilleux HUMAINS ! Vous avez TOUS réussi le Test Humain ! Maintenant… au tout dernier Gloink !"},
 # --- 5 about The Amazing Digital Circus / today's adventure ---
 "trivia_q1":{"cat":"🧠 Human test","label":"TADC: the ringmaster?",
   "en":"Tell me, human… who is the magnificent ringmaster of the Amazing Digital Circus?",
   "fr":"Dis-moi, humain… qui est le magnifique présentateur du Cirque Numérique Fantastique ?"},
 "trivia_q2":{"cat":"🧠 Human test","label":"TADC: 4 magic creatures?",
   "en":"Here's one… what do we call the four magic creatures you gathered on your adventure today?",
   "fr":"En voici une… comment appelle-t-on les quatre créatures magiques que vous avez rassemblées aujourd'hui ?"},
 "trivia_q3":{"cat":"🧠 Human test","label":"TADC: turned to a scribble = ?",
   "en":"Think hard… when a player gives up and gets turned into a glitchy little scribble, what is that called?",
   "fr":"Réfléchis bien… quand un joueur abandonne et se transforme en petit gribouillage qui bugue, comment ça s'appelle ?"},
 "trivia_q4":{"cat":"🧠 Human test","label":"TADC: first world today?",
   "en":"Remember now… what was the very FIRST world you teleported into today?",
   "fr":"Souviens-toi… quel a été le tout PREMIER monde où vous avez été téléportés aujourd'hui ?"},
 "trivia_q5":{"cat":"🧠 Human test","label":"TADC: how many Gloinks?",
   "en":"Count them up… how many Gloinks do you need to open the Exit Door?",
   "fr":"Compte bien… combien de Gloinks faut-il pour ouvrir la Porte de Sortie ?"},
 # --- 15 general (things 7-10 year olds know) ---
 "trivia_q6":{"cat":"🧠 Human test","label":"Spider legs?",
   "en":"Quick, human… how many legs does a spider have?",
   "fr":"Vite, humain… combien de pattes a une araignée ?"},
 "trivia_q7":{"cat":"🧠 Human test","label":"Blue + yellow = ?",
   "en":"A colour puzzle… what colour do you get when you mix blue and yellow?",
   "fr":"Une énigme de couleurs… quelle couleur obtient-on en mélangeant le bleu et le jaune ?"},
 "trivia_q8":{"cat":"🧠 Human test","label":"What do bees make?",
   "en":"Buzz buzz… what do bees make?",
   "fr":"Buzz buzz… que fabriquent les abeilles ?"},
 "trivia_q9":{"cat":"🧠 Human test","label":"Days in a week?",
   "en":"Easy one… how many days are there in a week?",
   "fr":"Une facile… combien de jours y a-t-il dans une semaine ?"},
 "trivia_q10":{"cat":"🧠 Human test","label":"Frozen water = ?",
   "en":"Brrr… what is frozen water called?",
   "fr":"Brrr… comment s'appelle l'eau gelée ?"},
 "trivia_q11":{"cat":"🧠 Human test","label":"Biggest planet?",
   "en":"Look to the stars… what is the biggest planet in our solar system?",
   "fr":"Regarde les étoiles… quelle est la plus grande planète de notre système solaire ?"},
 "trivia_q12":{"cat":"🧠 Human test","label":"Caterpillars become?",
   "en":"A wiggly one… what do caterpillars turn into?",
   "fr":"Une qui gigote… en quoi se transforment les chenilles ?"},
 "trivia_q13":{"cat":"🧠 Human test","label":"King of the jungle?",
   "en":"ROAR… which animal is called the king of the jungle?",
   "fr":"GROAR… quel animal est appelé le roi de la jungle ?"},
 "trivia_q14":{"cat":"🧠 Human test","label":"Colours in a rainbow?",
   "en":"After the rain… how many colours are in a rainbow?",
   "fr":"Après la pluie… combien de couleurs y a-t-il dans un arc-en-ciel ?"},
 "trivia_q15":{"cat":"🧠 Human test","label":"Baby dog = ?",
   "en":"Woof woof… what do you call a baby dog?",
   "fr":"Ouaf ouaf… comment appelle-t-on un bébé chien ?"},
 "trivia_q16":{"cat":"🧠 Human test","label":"Fastest land animal?",
   "en":"Zoooom… what is the fastest land animal?",
   "fr":"Vrooom… quel est l'animal terrestre le plus rapide ?"},
 "trivia_q17":{"cat":"🧠 Human test","label":"Sides on a triangle?",
   "en":"Shapes now… how many sides does a triangle have?",
   "fr":"Les formes… combien de côtés a un triangle ?"},
 "trivia_q18":{"cat":"🧠 Human test","label":"Planet we live on?",
   "en":"Home sweet home… what planet do we live on?",
   "fr":"À la maison… sur quelle planète vivons-nous ?"},
 "trivia_q19":{"cat":"🧠 Human test","label":"Star at centre = ?",
   "en":"Bright and warm… what do we call the star at the centre of our solar system?",
   "fr":"Brillante et chaude… comment s'appelle l'étoile au centre de notre système solaire ?"},
 "trivia_q20":{"cat":"🧠 Human test","label":"6 + 6 = ?",
   "en":"Last one, a bit of maths… what is six plus six?",
   "fr":"La dernière, un peu de calcul… combien font six plus six ?"},
 "presents_react":{"cat":"Big moments","label":"Ooh, a present!",
   "en":"Ooooh! What could be inside THIS one?! Open it, open it! The suspense is simply MAGNIFICENT!",
   "fr":"Ooooh ! Qu'est-ce qu'il peut y avoir dans CELUI-LÀ ?! Ouvre-le, ouvre-le ! Le suspense est tout simplement MAGNIFIQUE !"},

 # ---- Filler GAME clips (Run-of-Day) : each game has intro -> taunts -> conclusion ----
 "csays_intro":{"cat":"🎯 Game: Caine Says","label":"Intro / rules",
   "en":"OH-HO-HOOO! Time for a game of CAINE SAYS! Do EXACTLY what I say — but ONLY when I say 'Caine says' first! If I do NOT say 'Caine says' and you do it anyway… you get a teeny bit ABSTRACTED and you sit down! The last player standing is the CHAMPION! Everybody ready? Here… we… GO!",
   "fr":"OH-HO-HOOO ! C'est l'heure du jeu CAINE DIT ! Faites EXACTEMENT ce que je dis — mais SEULEMENT quand je dis « Caine dit » d'abord ! Si je ne dis PAS « Caine dit » et que vous le faites quand même… vous êtes un tout petit peu ABSTRAIT et vous vous asseyez ! Le dernier joueur debout est le CHAMPION ! Tout le monde est prêt ? C'est… parti !"},
 # One command per clip so Bubble can pace the game — play one, let the kids do it, play the next.
 "csays_cmd1":{"cat":"🎯 Game: Caine Says","label":"Caine says: JUMP",
   "en":"Caine says… JUMP like a kangaroo!",
   "fr":"Caine dit… SAUTE comme un kangourou !"},
 "csays_cmd2":{"cat":"🎯 Game: Caine Says","label":"Caine says: FREEZE",
   "en":"Caine says… FREEZE like a glitching statue!",
   "fr":"Caine dit… FIGE-TOI comme une statue qui bugue !"},
 "csays_cmd3":{"cat":"🎯 Game: Caine Says","label":"Caine says: ROAR",
   "en":"Caine says… spin around and ROAR like a lion!",
   "fr":"Caine dit… tourne sur toi-même et RUGIS comme un lion !"},
 "csays_cmd4":{"cat":"🎯 Game: Caine Says","label":"Caine says: nose",
   "en":"Caine says… touch your nose!",
   "fr":"Caine dit… touche ton nez !"},
 "csays_cmd5":{"cat":"🎯 Game: Caine Says","label":"Caine says: wiggle",
   "en":"Caine says… wiggle your bottom!",
   "fr":"Caine dit… remue les fesses !"},
 "csays_cmd6":{"cat":"🎯 Game: Caine Says","label":"Caine says: chicken",
   "en":"Caine says… flap your arms like a chicken!",
   "fr":"Caine dit… bats des bras comme une poule !"},
 "csays_cmd7":{"cat":"🎯 Game: Caine Says","label":"Caine says: tiptoe",
   "en":"Caine says… tiptoe on the spot, quiet as a little mouse!",
   "fr":"Caine dit… marche sur la pointe des pieds, silencieux comme une petite souris !"},
 "csays_cmd8":{"cat":"🎯 Game: Caine Says","label":"Caine says: wave",
   "en":"Caine says… WAVE your hands high in the air and say HELLOOO!",
   "fr":"Caine dit… AGITE les mains bien haut en l'air et dis BONJOUUUR !"},
 "csays_cmd9":{"cat":"🎯 Game: Caine Says","label":"Caine says: stomp",
   "en":"Caine says… STOMP your feet like a big circus elephant!",
   "fr":"Caine dit… TAPE des pieds comme un gros éléphant de cirque !"},
 "csays_cmd10":{"cat":"🎯 Game: Caine Says","label":"Caine says: tongue out",
   "en":"Caine says… stick out your tongue and make your silliest face!",
   "fr":"Caine dit… tire la langue et fais ta grimace la plus rigolote !"},
 "csays_cmd11":{"cat":"🎯 Game: Caine Says","label":"Caine says: hop",
   "en":"Caine says… HOP on one foot like a wobbly flamingo!",
   "fr":"Caine dit… SAUTILLE sur un pied comme un flamant rose tout bancal !"},
 # TRICK clips — Caine gives the order WITHOUT saying 'Caine says', then catches whoever did it.
 "csays_trick":{"cat":"🎯 Game: Caine Says","label":"⚡ TRICK: touch the ground",
   "en":"Now everybody… touch the ground! …AH-AH-AHHH! I did NOT say 'Caine says'! Buzz! Caught you, you cheeky little players! Hee-hee-hee!",
   "fr":"Maintenant, tout le monde… touchez le sol ! …AH-AH-AHHH ! Je n'ai PAS dit « Caine dit » ! Buzz ! Je vous ai eus, petits malins ! Hi-hi-hi !"},
 "csays_trick2":{"cat":"🎯 Game: Caine Says","label":"⚡ TRICK: clap your hands",
   "en":"Now… CLAP your hands! …OHHH-HO-HO! I did NOT say 'Caine says'! Gotcha! If you clapped, sit DOWN, tricked player! Hee-hee!",
   "fr":"Maintenant… TAPEZ des mains ! …OHHH-HO-HO ! Je n'ai PAS dit « Caine dit » ! Je vous ai eus ! Si vous avez tapé, ASSIS, joueur piégé ! Hi-hi !"},
 "csays_trick3":{"cat":"🎯 Game: Caine Says","label":"⚡ TRICK: spin around",
   "en":"Everybody… SPIN around! …Buzz! I did NOT say 'Caine says'! Hee-hee, dizzy little players — if you spun, down you sit!",
   "fr":"Tout le monde… TOURNE sur toi-même ! …Buzz ! Je n'ai PAS dit « Caine dit » ! Hi-hi, petits joueurs tout étourdis — si tu as tourné, assieds-toi !"},
 "csays_trick4":{"cat":"🎯 Game: Caine Says","label":"⚡ TRICK: jump up",
   "en":"Ready? JUMP up high! …AH-HA! No 'Caine says' that time! Caught you mid-air, you cheeky players — sit DOWN! Ho-ho-ho!",
   "fr":"Prêts ? SAUTE bien haut ! …AH-HA ! Pas de « Caine dit » cette fois ! Je t'ai eu en plein vol, petit malin — ASSIS ! Ho-ho-ho !"},
 "csays_trick5":{"cat":"🎯 Game: Caine Says","label":"⚡ TRICK: touch your head",
   "en":"Now… touch your head! …OOOH-NO! I did NOT say 'Caine says'! Buzz-buzz! Down you go, tricked players! Hee-hee-hee!",
   "fr":"Maintenant… touche ta tête ! …OOOH-NON ! Je n'ai PAS dit « Caine dit » ! Buzz-buzz ! Assis, joueurs piégés ! Hi-hi-hi !"},
 "csays_trick6":{"cat":"🎯 Game: Caine Says","label":"⚡ TRICK: say BANANA",
   "en":"Everybody shout… BANANA! …HA-HA! I did NOT say 'Caine says'! Gotcha, you silly wonderful players — take a seat! Hee-hee!",
   "fr":"Tout le monde crie… BANANE ! …HA-HA ! Je n'ai PAS dit « Caine dit » ! Je vous ai eus, adorables petits coquins — asseyez-vous ! Hi-hi !"},
 "csays_end":{"cat":"🎯 Game: Caine Says","label":"Conclusion",
   "en":"MAGNIFICENT playing, my players! Every single one of you is a CAINE SAYS champion! Take a great big bow — the whole circus is cheering for YOU!",
   "fr":"MAGNIFIQUE, mes joueurs ! Vous êtes tous des champions de CAINE DIT ! Saluez bien bas — tout le cirque vous applaudit !"},

 "hotgloink_intro":{"cat":"🎯 Game: Hot Gloink","label":"Intro / rules",
   "en":"Into a circle, players, for PASS THE HOT GLOINK! Pass it round and round while the music plays — quick, quick, do not hold it too long! When the music STOPS, whoever is holding the Gloink gets ABSTRACTED — buzz! — and becomes one of my Glitch Judges beside me! The last player still in the circle WINS! Music… GO!",
   "fr":"En cercle, les joueurs, pour LE GLOINK BRÛLANT ! Faites-le passer encore et encore pendant la musique — vite, vite, ne le gardez pas trop longtemps ! Quand la musique S'ARRÊTE, celui qui tient le Gloink se fait ABSTRAIRE — buzz ! — et devient un de mes Juges du Bug à côté de moi ! Le dernier joueur dans le cercle GAGNE ! La musique… C'EST PARTI !"},
 "hotgloink_taunt":{"cat":"🎯 Game: Hot Gloink","label":"Taunt (tick-tock)",
   "en":"Tick… tock… tick… tock… ooooh, I feel a GLITCH coming! Pass it faster, faster, FASTER, players!",
   "fr":"Tic… tac… tic… tac… ouuuh, je sens un BUG arriver ! Passez-le plus vite, plus vite, PLUS VITE, les joueurs !"},
 "hotgloink_out":{"cat":"🎯 Game: Hot Gloink","label":"Abstracted! (you're out)",
   "en":"Buzz! ABSTRACTED! Step out, brave player — you are a Glitch Judge now! Give me your very BEST 'buzz!' Hee-hee-hee!",
   "fr":"Buzz ! ABSTRAIT ! Sors du cercle, courageux joueur — tu es un Juge du Bug maintenant ! Donne-moi ton MEILLEUR « buzz ! » Hi-hi-hi !"},
 "hotgloink_end":{"cat":"🎯 Game: Hot Gloink","label":"Winner!",
   "en":"And we have a WINNER — the last player still un-glitched! MAGNIFICENT! Take a bow, champion of the Hot Gloink!",
   "fr":"Et nous avons un GAGNANT — le dernier joueur pas encore buggé ! MAGNIFIQUE ! Salue bien bas, champion du Gloink Brûlant !"},

 "balloon_intro":{"cat":"🎯 Game: Glitch Balloons","label":"Intro / rules",
   "en":"New challenge, players! These are GLITCH BALLOONS — do NOT let them touch the ground, or POOF, they abstract away! All together now — tap, tap, tap — keep every balloon in the air! How loooong can you last?",
   "fr":"Nouveau défi, les joueurs ! Voici des BALLONS-BUGS — ne les laissez PAS toucher le sol, sinon POUF, ils s'abstraient ! Tous ensemble — tap, tap, tap — gardez chaque ballon en l'air ! Combien de temps tiendrez-vous ?"},
 "balloon_taunt":{"cat":"🎯 Game: Glitch Balloons","label":"Faster! (taunt)",
   "en":"Ooooh, the glitches are getting STRONGER — tap faster, players, do not let a single balloon touch the floor! Keep them UP, keep them UP!",
   "fr":"Ouuuh, les bugs deviennent plus FORTS — tapez plus vite, les joueurs, ne laissez aucun ballon toucher le sol ! Gardez-les EN L'AIR, EN L'AIR !"},
 "balloon_end":{"cat":"🎯 Game: Glitch Balloons","label":"Winner!",
   "en":"TIME'S UP — and look at that, not one balloon abstracted! MAGNIFICENT teamwork, my wonderful players! Take a giant circus bow!",
   "fr":"LE TEMPS EST ÉCOULÉ — et regardez, pas un seul ballon abstrait ! MAGNIFIQUE travail d'équipe, mes merveilleux joueurs ! Saluez bien bas, comme au cirque !"},
}

# Personalized farewells — one clip per named player (replaces the old generic goodbye).
# Generated from the ROSTER so the names + characters always stay in sync.
for _kid in ROSTER:
    _nm, _ch = _kid["name"], _kid["character"]
    HOST[f"goodbye_{slug(_nm)}"] = {
        "cat": "Farewells", "label": f"Bye, {_nm}",
        "en": f"Goodbye, {_nm}! You were a MAGNIFICENT {_ch} today — the Amazing Digital Circus will miss you! Come back and play very soon, you wonderful player!",
        "fr": f"Au revoir, {_nm} ! Tu as été un MAGNIFIQUE {_ch} aujourd'hui — le Cirque Numérique Fantastique va te regretter ! Reviens jouer très vite, merveilleux joueur !",
    }

# Adventure step list (shared source of truth — the console's 14 steps, by index). The Party
# Server exposes this via /api/game so Bubble's remote can show "Step N · title" while it drives
# Nora's console over the network.
# Each step also carries `do` — the concise action for BUBBLE (the host). This shows on the
# Guide's adventure remote only; it is deliberately NOT on the kids' console.
ADV_STEPS = [
    {"id":"s01","title":"Headsets on",            "do":"Hand out eye-masks; kids put them ON (eyes covered). While they can't see, you + a helper quietly stick a character badge on each kid."},
    {"id":"s02","title":"Caine arrives",          "do":"Keep their eyes covered — tap Next straight through to the reveal."},
    {"id":"s03","title":"The reveal (eyes open)", "do":"Caine names each player + their character. Kids push masks up on \"EYES OPEN!\" and discover their badge."},
    {"id":"s04","title":"① Candy Canyon",         "do":"Walk everyone into the garden (goggles DOWN, follow Bubble). Tap NEXT on arrival → Caine fires the teleport '3-2-1 ZAP! Goggles UP'. Then run the Candy-Bandit catch game (grab the scattered candy to your base bucket in 120s; if the Bandit hand-tags you, back to base). Tap Next for the win."},
    {"id":"s05","title":"RED Gloink (hidden!)",   "do":"You HID the RED Gloink near Candy Canyon earlier — ALL the kids hunt for it. When it's found, Caine names Chloé its keeper → the kids hand it to her. Sprinkle the 🔍 Gloink-hunt nudges if they're stuck."},
    {"id":"s06","title":"② Fast-Food burger",     "do":"Lead them to the burger station (goggles DOWN; optionally play 🌀 Teleport-go). Tap NEXT on arrival → Caine's '3-2-1 ZAP! Goggles UP'. Then run the burger build. Tap Next when it's built."},
    {"id":"s07","title":"YELLOW Gloink (hidden!)","do":"YELLOW Gloink is HIDDEN here — all kids hunt; Caine names Hugo its keeper → hand it to him."},
    {"id":"s08","title":"③ Mildenhall Manor",     "do":"Lead them to the manor (goggles DOWN). Tap NEXT on arrival → Caine's '3-2-1 ZAP! Goggles UP'. Then run the dark-room hunt for all 15 glowing stars (90s); when found, tap Next so Caine reads the sock riddle for the hidden PURPLE Gloink."},
    {"id":"s09","title":"PURPLE Gloink (hidden!)","do":"PURPLE Gloink is HIDDEN here — all kids hunt; Caine names Leo its keeper → hand it to him."},
    {"id":"s10","title":"④ Don't get Abstracted", "do":"Lead them over (goggles DOWN). Tap NEXT on arrival → Caine's LAST '3-2-1 ZAP! Goggles UP'. Then run the freeze-tag — YOU (Bubble) are the glitch, hand-tag them; tagged = freeze till a friend high-fives them. Tap Next when they survive (→ Human Test from the guide)."},
    {"id":"s11","title":"BLUE Gloink — all 4!",   "do":f"BLUE Gloink is HIDDEN here — everyone hunts; Caine names {STAR} keeper of the winning Gloink → hand it to her. Then TELEPORT everyone UP to the Exit Door (the upstairs guest toilet): goggles down, march up; the 4 keepers carry their Gloinks."},
    {"id":"s12","title":"Teleport + the Code",    "do":f"Caine teleports them to the Exit Door, then the CODE puzzle: the kids must work out for themselves that the code = the ORDER they FOUND the Gloinks (RED→YELLOW→PURPLE→BLUE). Caine WON'T say it & the buttons are shuffled. No time limit; gentle hints if stuck (or tap NEXT to move on)."},
    {"id":"s13","title":"EXIT OPEN — find the treasure!","do":f"Code right → door opens. Let {STAR} PUSH it — you've ESCAPED! Now the kids HUNT for the hidden treasure chest of candy bags (you stashed it nearby). NO cake here."},
    {"id":"s14","title":"Treasure found → CAKE!", "do":f"Treasure found → Caine calls CAKE TIME. Lead everyone to the cake (set up separately); Sasha pops the popper; candles → Happy Birthday {STAR}!"},
]

def build_host_clips():
    """(basename, lang, text) for every host phrase, both languages -> host_<key>_<lang>."""
    out = []
    for key, d in HOST.items():
        for lang in ("en", "fr"):
            out.append((f"host_{key}_{lang}", lang, d[lang]))
    return out

def write_host_manifest():
    """Emit caine-host-phrases.js next to the Party Guide so it can render the soundboard
    (EN/FR buttons per phrase) without duplicating the text. Single source of truth = HOST."""
    import json
    data = [{"key": k, "cat": d["cat"], "label": d["label"], "en": d["en"], "fr": d["fr"]}
            for k, d in HOST.items()]
    path = os.path.abspath(os.path.join(HERE, "..", "caine-host-phrases.js"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.HOST_PHRASES = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    return path

def build_clips():
    """Returns list of (basename, lang, text)."""
    clips = []
    def add(base, langs, src):
        for lang in langs: clips.append((f"{base}_{lang}", lang, src[lang]))
    add("s01", ["en","fr"], GENERAL["s01"])
    add("s02", ["en","fr"], GENERAL["s02"])
    add("s03_intro", ["en","fr"], REVEAL_INTRO)
    for kid in ROSTER:
        for lang in (["en","fr"] if kid["bilingual"] else ["fr"]):
            clips.append((f"s03_{slug(kid['name'])}_{lang}", lang, kid_intro(kid, lang)))
    add("s03_outro", ["en","fr"], REVEAL_OUTRO)
    for sid in ["s04","s05","s06","s07","s08","s09","s10","s11","s12","s13","s14"]:
        add(sid, ["en","fr"], GENERAL[sid])
        if sid in CARRIERS:
            c = CARRIERS[sid]; add(f"{sid}_carry", (["en","fr"] if c["bilingual"] else ["fr"]), c)
    clips += build_host_clips()        # Caine's whole-party host phrases (soundboard)
    return clips

# A tiny test phrase — generate just this to quickly check a clip / model / accent.
TEST = {"en": "Welcome to the Amazing Digital Circus, Nora! Are your friends here? Are you ready to go on an adventure?",
        "fr": "Bienvenue au Cirque Numérique Fantastique, Nora ! Tes amis sont là ? Es-tu prête à partir à l'aventure ?"}
def build_test_clips():
    return [("test_en", "en", TEST["en"]), ("test_fr", "fr", TEST["fr"])]

# ----------------------------------------------------------------------------
# Reference clips & paths
#   English ref:  caine_ref.wav   (->  caine_ref_vocals.wav after isolation)
#   French ref:   caine_ref_fr.wav (optional, -> caine_ref_fr_vocals.wav)
# ----------------------------------------------------------------------------
HERE    = os.path.dirname(os.path.abspath(__file__))
OUTROOT = os.path.abspath(os.path.join(HERE, "..", "caine-console", "audio"))
REF_TXT = os.path.join(HERE, "caine_ref.txt")        # transcript, for F5 only

# ----------------------------------------------------------------------------
# Big rebuildable stuff (per-model environments + downloaded model weights) lives on a
# roomy drive, NOT under the project folder — those venvs are multi-GB each and
# would otherwise fill C: and sync to the cloud. Default to D:\AI\cache\audio when a D:\AI
# folder exists; override with CAINE_CACHE_ROOT. HF_HOME/PIP_CACHE_DIR are pointed at the
# same drive so model downloads (HuggingFace) and pip wheels don't land on C: either.
# ----------------------------------------------------------------------------
CACHE_ROOT = os.environ.get("CAINE_CACHE_ROOT") or (
    r"D:\AI\cache\audio" if os.path.isdir(r"D:\AI") else HERE)
VENV_ROOT  = os.path.join(CACHE_ROOT, "venvs")
try:
    os.makedirs(VENV_ROOT, exist_ok=True)
except Exception:
    CACHE_ROOT, VENV_ROOT = HERE, HERE          # fall back to local if the drive is unwritable
os.environ.setdefault("HF_HOME",       os.path.join(CACHE_ROOT, "huggingface"))
os.environ.setdefault("PIP_CACHE_DIR", os.path.join(CACHE_ROOT, "pip"))

def load_secrets():
    """Load KEY=VALUE secrets (e.g. HF_TOKEN for gated HuggingFace models) from SECRETS.env
    next to this script into the environment, without overwriting anything already set. Keeps
    tokens out of the code. SECRETS.env is private — don't share/commit it."""
    path = os.path.join(HERE, "SECRETS.env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
load_secrets()

KNOBS_FILE = os.path.join(HERE, "knobs.json")
def load_knob_overrides():
    """Per-model knob tweaks saved by the Studio: {model: {knob: {lang: value}}}."""
    try:
        import json
        return json.load(open(KNOBS_FILE, encoding="utf-8"))
    except Exception:
        return {}
_KNOB_OVERRIDES = load_knob_overrides()

def knob(model, name, lang="en"):
    """Effective value of a knob for a language: the Studio's saved override if present,
    otherwise the per-language default from KNOBS (falling back to the 'en' default)."""
    spec = KNOBS.get(model, {}).get(name, {})
    default = spec.get("default", {})
    val = default.get(lang, default.get("en")) if isinstance(default, dict) else default
    try:
        ov = _KNOB_OVERRIDES[model][name]
        o = ov.get(lang, ov.get("en")) if isinstance(ov, dict) else ov
        if o is not None:
            val = o
    except Exception:
        pass
    return int(round(float(val))) if spec.get("int") else float(val)

# Push-to-talk uses OmniVoice too, but its settings are SEPARATE from the generation knobs above:
# the live mic prizes SPEED over polish, so we default to far fewer diffusion steps. Stored in
# knobs.json under the "talk" namespace (edited from the Studio's Push-to-Talk panel); the slider
# ranges/type come from the omnivoice knob spec so the same controls work.
TALK_DEFAULTS = {"steps": {"en": 16, "fr": 16}, "guidance": {"en": 2.0, "fr": 3.0}}
def talk_knob(name, lang="en"):
    """Effective PUSH-TO-TALK OmniVoice setting (independent of the generation knob): the Studio's
    saved 'talk' override if present, otherwise the fast TALK_DEFAULTS."""
    spec = KNOBS.get("omnivoice", {}).get(name, {})
    default = TALK_DEFAULTS.get(name, {})
    val = default.get(lang, default.get("en"))
    try:
        ov = _KNOB_OVERRIDES["talk"][name]
        o = ov.get(lang, ov.get("en")) if isinstance(ov, dict) else ov
        if o is not None:
            val = o
    except Exception:
        pass
    return int(round(float(val))) if spec.get("int") else float(val)

P = lambda *a: os.path.join(HERE, *a)
EN_RAW, EN_VOC, EN_MUS = P("caine_ref.wav"), P("caine_ref_vocals.wav"), P("caine_ref_music.wav")
FR_RAW, FR_VOC, FR_MUS = P("caine_ref_fr.wav"), P("caine_ref_fr_vocals.wav"), P("caine_ref_fr_music.wav")
# A SHORT clip (<=~11s) + a transcript that matches ONLY that clip, built just for F5.
# F5 clips any reference over ~12s but keeps the full transcript, so a long clip makes
# its audio:text ratio wrong and the output comes out garbled / way too fast. See make_f5_ref().
F5_REF_WAV = P("caine_ref_f5.wav")
F5_REF_TXT = P("caine_ref_f5.txt")

REFS = {"en": EN_RAW, "fr": EN_RAW}   # set properly in main()
FR_NATIVE = False                      # True if a real French ref clip is used
ONLY_CLIP = None                       # --only=<basename>: (re)generate just that one clip (e.g. s05_fr)
LANG = None                            # --lang=en|fr: restrict generation to one language (None = both)

def pip(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *pkgs])

class _Tee:
    """Write everything printed to BOTH the console and a log file."""
    def __init__(self, *streams): self.streams = streams
    def write(self, s):
        for st in self.streams:
            try: st.write(s); st.flush()
            except Exception: pass
    def flush(self):
        for st in self.streams:
            try: st.flush()
            except Exception: pass

def start_log():
    logdir = os.path.join(HERE, "logs"); os.makedirs(logdir, exist_ok=True)
    path = os.path.join(logdir, time.strftime("caine_%Y%m%d-%H%M%S.log"))
    f = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, f)
    sys.stderr = _Tee(sys.__stderr__, f)
    print(f"[log] writing this run to: {path}")
    return path

# Models that clash with Chatterbox's 'transformers' version get their OWN auto-built
# virtual environment, so they "just work" from the Studio without breaking anything.
ISOLATED_ENVS = {
    # coqui-tts / f5-tts do NOT pull in PyTorch automatically, so we install torch
    # + torchaudio explicitly. coqui-tts also breaks on transformers>=5 (it removed
    # 'isin_mps_friendly'), so we pin transformers<5. 'check_code' must run cleanly
    # for the env to be considered ready (and repairs a wrongly-built env).
    # coqui-tts needs transformers<5 (5.x removed isin_mps_friendly) AND torch<2.9
    # (2.9 dropped built-in audio IO and demands the fiddly torchcodec). The check
    # verifies those versions so a wrongly-built env gets auto-repaired.
    "xtts": {"dir": ".venv_xtts",
             "pip": ["torch<2.9", "torchaudio<2.9", "coqui-tts", "soundfile", "transformers<5"],
             "check_code": "import torch,transformers,TTS; v=torch.__version__.split('.'); "
                           "assert (int(v[0]),int(v[1]))<(2,9); assert int(transformers.__version__.split('.')[0])<5"},
    "f5":   {"dir": ".venv_f5",
             "pip": ["torch<2.9", "torchaudio<2.9", "f5-tts"],
             "check_code": "import torch, f5_tts; v=torch.__version__.split('.'); assert (int(v[0]),int(v[1]))<(2,9)"},
    # Qwen3-TTS (Apache-2.0): clean pip package, voice clone + natural-language style, EN+FR.
    "qwen3": {"dir": ".venv_qwen3",
              "pip": ["torch<2.9", "torchaudio<2.9", "qwen-tts", "soundfile", "huggingface_hub"],
              "check_code": "import torch, qwen_tts"},
    # OpenAudio / Fish-Speech S1-mini (CC-BY-NC-SA, fine for personal use): ~0.5B, ~4GB VRAM
    # (CPU possible but slow), supports French + inline (emotion) tags. Same 3-stage CLI the S2
    # path used — we just point the weights at the small open model. (S2/s2-pro needs ~24GB GPU.)
    "openaudio": {"dir": ".venv_openaudio",
              "pip": ["torch<2.9", "torchaudio<2.9", "huggingface_hub", "soundfile"],
              "repo": "https://github.com/fishaudio/fish-speech.git", "repo_dir": "fish-speech",
              "weights": {"fishaudio/openaudio-s1-mini": "checkpoints/openaudio-s1-mini"},
              "weights_sentinel": "codec.pth",   # gated; a partial fail leaves README/.cache behind
              "check_code": "import torch"},
    # OmniVoice (k2-fsa, Apache-2.0): clean pip package, ~2.45GB weights, NATIVE French (600+
    # langs), ~6-8GB GPU (CPU slow). Best French candidate. Language is inferred from the text.
    "omnivoice": {"dir": ".venv_omnivoice",
              "pip": ["torch<2.9", "torchaudio<2.9", "omnivoice", "soundfile", "huggingface_hub"],
              "check_code": "import torch, omnivoice"},
    # CosyVoice2-0.5B (FunAudioLLM, Apache-2.0): clone + natural-language style (instruct2), ~4GB
    # GPU. Current cards DO list French. git repo (+ Matcha-TTS submodule). WINDOWS CAVEAT: its
    # requirements pull pynini/WeTextProcessing, which has no Windows wheels — the auto-build may
    # fail and need the manual conda-forge pynini step (see README); the run then just 'skips'.
    "cosyvoice": {"dir": ".venv_cosyvoice",
              "pip": ["torch<2.9", "torchaudio<2.9", "modelscope", "huggingface_hub", "soundfile"],
              "repo": "https://github.com/FunAudioLLM/CosyVoice.git", "repo_dir": "CosyVoice",
              "recursive": True, "install": "requirements",
              "requirements_skip": ["pynini", "WeTextProcessing", "openai-whisper"],  # no Windows wheels / build needs isolation off
              "pip_no_isolation": ["openai-whisper"],   # CosyVoice imports `whisper`; build it against venv setuptools<81
              "weights": {"FunAudioLLM/CosyVoice2-0.5B": "pretrained_models/CosyVoice2-0.5B"},
              "check_code": "import torch"},
    # IndexTTS-2 (bilibili licence, non-commercial OK): emotion-controllable clone, ENGLISH/Chinese
    # ONLY (no French), ~8-12GB GPU. git repo + ~4.7GB weights. Officially installed with 'uv sync';
    # we try 'pip install -e .' (often works) — if it fails the run skips (see README).
    "indextts2": {"dir": ".venv_indextts2",
              "pip": ["torch<2.9", "torchaudio<2.9", "huggingface_hub"],
              "repo": "https://github.com/index-tts/index-tts.git", "repo_dir": "index-tts",
              "install": "editable",
              "weights": {"IndexTeam/IndexTTS-2": "checkpoints"},
              "weights_sentinel": "config.yaml",   # the repo ships a non-empty checkpoints/ (pinyin.vocab)
              "check_code": "import torch"},
    # Higgs Audio v2 (Boson AI, Apache-2.0 code): expressive clone via a ChatML prompt. ENGLISH-
    # focused (no official French), HEAVY: ~24GB GPU, effectively CUDA-only. Weights (~14GB) auto-
    # download from the Hub at runtime, so no pre-download here. git repo + editable install.
    "higgs": {"dir": ".venv_higgs",
              "pip": ["torch<2.9", "torchaudio<2.9", "torchvision", "huggingface_hub", "soundfile"],
              "repo": "https://github.com/boson-ai/higgs-audio.git", "repo_dir": "higgs-audio",
              "install": "requirements+editable",   # repo deps (transformers etc.) live in requirements.txt
              "requirements_skip": ["torch", "torchaudio", "torchvision"],  # keep our cu128 build, don't let pip swap it
              "check_code": "import torch"},
}

def _venv_python(vdir):
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return os.path.join(vdir, sub, exe)

# --- GPU / CUDA torch -------------------------------------------------------
# Plain `pip install torch` gives a CPU-ONLY wheel on Windows, so the models run on
# CPU even with an NVIDIA card. When a GPU is present we install torch from the CUDA
# wheel index instead. Override the CUDA build with CAINE_TORCH_CUDA=cu126 (etc.) if
# your driver is older; set CAINE_TORCH_CUDA=cpu to force CPU.
def cuda_index():
    forced = os.environ.get("CAINE_TORCH_CUDA")
    if forced == "cpu":
        return None
    if not forced:
        try:
            subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT)
        except Exception:
            return None                       # no NVIDIA GPU -> CPU wheels
    return f"https://download.pytorch.org/whl/{forced or 'cu128'}"

def _is_torch_pkg(req):
    return req.split("<")[0].split(">")[0].split("=")[0].strip().lower() in ("torch", "torchaudio", "torchvision")

def _pkg_name(req):
    return req.split("<")[0].split(">")[0].split("=")[0].strip()

def install_deps(py, spec):
    """Install a spec's pip deps, fetching torch/torchaudio from the CUDA wheel index
    (when a GPU is present) and everything else from PyPI."""
    idx = cuda_index()
    torch_pkgs = [p for p in spec["pip"] if _is_torch_pkg(p)]
    others     = [p for p in spec["pip"] if not _is_torch_pkg(p)]
    if torch_pkgs:
        if idx:
            print(f"   installing GPU PyTorch from {idx} ...")
            subprocess.check_call([py, "-m", "pip", "install", "--index-url", idx, *torch_pkgs])
        else:
            subprocess.check_call([py, "-m", "pip", "install", *torch_pkgs])
    if others:
        subprocess.check_call([py, "-m", "pip", "install", *others])

def ensure_cuda_torch(py, spec):
    """If a GPU is present but this env has a CPU-only torch, swap it for the CUDA build.
    Repairs envs that were built before GPU support (e.g. an old `torch==…+cpu`)."""
    idx = cuda_index()
    torch_pkgs = [p for p in spec["pip"] if _is_torch_pkg(p)]
    if not idx or not torch_pkgs:
        return
    has_cuda = subprocess.call([py, "-c", "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    if not has_cuda:
        print(f"   GPU detected but '{spec['dir']}' has CPU-only torch — installing the CUDA build...")
        subprocess.check_call([py, "-m", "pip", "uninstall", "-y", *[_pkg_name(p) for p in torch_pkgs]])
        subprocess.check_call([py, "-m", "pip", "install", "--index-url", idx, *torch_pkgs])

def ensure_venv(spec):
    vdir = os.path.join(VENV_ROOT, spec["dir"])
    py = _venv_python(vdir)
    if not os.path.exists(py):
        print(f"   [one-time] creating isolated env '{spec['dir']}'...")
        subprocess.check_call([sys.executable, "-m", "venv", vdir])
    # Is the env actually usable? (also repairs an env with the wrong deps/versions.)
    ready = subprocess.call([py, "-c", spec.get("check_code", "import sys")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    if not ready:
        print(f"   installing/repairing dependencies in '{spec['dir']}' (incl. PyTorch — the")
        print(f"   first time downloads a few hundred MB and can take several minutes)...")
        # setuptools+wheel: fresh venvs no longer bundle them. Pin setuptools<81 because 81
        # REMOVED pkg_resources, which older sdists (e.g. openai-whisper) import at build time.
        subprocess.check_call([py, "-m", "pip", "install", "-U", "pip", "setuptools<81", "wheel"])
        install_deps(py, spec)
        # verify the pins took; show the real error if not (don't hide it)
        rc = subprocess.run([py, "-c", spec.get("check_code", "import sys")],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if rc.returncode != 0:
            print(f"   !! env '{spec['dir']}' still not ready after install:\n{(rc.stdout or '').strip()[-1200:]}")
        else:
            print(f"   env '{spec['dir']}' is ready.")
    ensure_cuda_torch(py, spec)   # upgrade a CPU-only torch to the CUDA build when a GPU exists
    if spec.get("repo"):
        ensure_repo(py, vdir, spec)
    return py

def ensure_repo(py, vdir, spec):
    """Clone a model's git repo (+ optional submodules), install it, and download its HF
    weights into the isolated env. Used by repo-based models (openaudio, cosyvoice,
    indextts2, higgs). Spec keys:
       repo        git URL
       repo_dir    subdir name under the venv (default: repo basename)
       recursive   git clone --recursive (submodules)               [default False]
       install     'editable' (pip install -e .) | 'requirements'
                   (pip install -r requirements.txt) | None         [default 'editable']
       weights     {hf_id: subdir} to snapshot_download into <repo>/<subdir>
                   (omit if the model auto-downloads its weights at runtime, e.g. higgs)."""
    name = spec.get("repo_dir") or os.path.splitext(os.path.basename(spec["repo"].rstrip("/")))[0]
    repo_dir = os.path.join(vdir, name)
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        print(f"   cloning {spec['repo']} ...")
        clone = ["git", "clone", "--depth", "1"]
        if spec.get("recursive"): clone.append("--recursive")
        subprocess.check_call(clone + [spec["repo"], repo_dir])
        how = spec.get("install", "editable")   # "editable" | "requirements" | "requirements+editable"
        if "requirements" in how:
            subprocess.check_call([py, "-m", "pip", "install", "-U", "setuptools<81", "wheel"])  # <81 keeps pkg_resources
            req = os.path.join(repo_dir, "requirements.txt")
            skip = {s.lower() for s in spec.get("requirements_skip", [])}
            if skip and os.path.exists(req):   # drop deps that don't build on Windows / would swap our CUDA torch
                def _pkg(ln):                  # exact package name (so 'torch' doesn't match 'vector_quantize_pytorch')
                    s = ln.strip()
                    for sep in "<>=!~[ ;":
                        s = s.split(sep)[0]
                    return s.strip().lower()
                lines = open(req, encoding="utf-8").read().splitlines()
                kept = [ln for ln in lines if _pkg(ln) not in skip]
                req = os.path.join(repo_dir, "requirements.caine.txt")
                open(req, "w", encoding="utf-8").write("\n".join(kept))
                print(f"   (skipping {', '.join(sorted(skip))} in requirements)")
            if os.path.exists(req):
                subprocess.check_call([py, "-m", "pip", "install", "-r", req])
        if "editable" in how:
            subprocess.check_call([py, "-m", "pip", "install", "-e", repo_dir])
    # Extra packages that must build against the venv's OWN setuptools (no build isolation) —
    # e.g. openai-whisper, whose old sdist imports pkg_resources at build time (removed in
    # setuptools 81). Run every time; pip is a no-op once they're installed.
    for pkg in spec.get("pip_no_isolation", []):
        subprocess.check_call([py, "-m", "pip", "install", "--no-build-isolation", pkg])
    weights = spec.get("weights")
    items = weights.items() if isinstance(weights, dict) else \
            ([(weights, os.path.join("checkpoints", os.path.basename(weights)))] if weights else [])
    sentinel = spec.get("weights_sentinel")   # a file that proves the weights are really present
    for wid, sub in items:
        dest = os.path.join(repo_dir, sub)
        have = os.path.isdir(dest) and (os.path.exists(os.path.join(dest, sentinel)) if sentinel
                                        else bool(os.listdir(dest)))
        if not have:
            print(f"   downloading weights {wid} -> {sub} (large, one-time)...")
            subprocess.check_call([py, "-c",
                "from huggingface_hub import snapshot_download as d; "
                f"d({wid!r}, local_dir={dest!r})"])

def isolate_file(src, voc_out, mus_out, force=False):
    if not os.path.exists(src): return False
    if os.path.exists(voc_out) and not force:
        print(f"   exists: {os.path.basename(voc_out)}"); return True
    try:
        import demucs  # noqa
    except Exception:
        print("   installing Demucs..."); pip("demucs")
    print(f"   isolating {os.path.basename(src)} ...")
    tmp = tempfile.mkdtemp()
    subprocess.check_call([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-o", tmp, src])
    voc = glob.glob(os.path.join(tmp, "**", "vocals.wav"), recursive=True)
    nov = glob.glob(os.path.join(tmp, "**", "no_vocals.wav"), recursive=True)
    if not voc: print("   !! no vocals produced"); return False
    shutil.copy(voc[0], voc_out)
    if nov: shutil.copy(nov[0], mus_out)
    return True

def to_wav(src, dst):
    """Convert an audio file (e.g. .mp3) to .wav (44.1 kHz mono). Cached."""
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst
    try:
        import imageio_ffmpeg
    except Exception:
        print("   installing a small ffmpeg helper (one time)..."); pip("imageio-ffmpeg")
        import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    print(f"   converting {os.path.basename(src)} -> {os.path.basename(dst)}")
    subprocess.check_call([ff, "-y", "-i", src, "-ar", "44100", "-ac", "1", dst])
    return dst

def find_clean(stem):
    """A PRE-CLEANED reference (already voice-only) named <stem>.wav or <stem>.mp3.
    If found, returns a .wav path (converting from mp3 if needed). Bypasses isolation."""
    wav = os.path.join(HERE, stem + ".wav")
    mp3 = os.path.join(HERE, stem + ".mp3")
    if os.path.exists(mp3):
        return to_wav(mp3, wav)           # convert mp3 -> wav (or reuse cached wav)
    if os.path.exists(wav):
        return wav
    return None

def best_ref_audio():
    """The best available copy of the reference voice to transcribe from."""
    c = find_clean("caine_ref_clean")
    if c: return c
    if os.path.exists(EN_VOC): return EN_VOC
    return EN_RAW

def transcribe(force=False):
    """Auto-write caine_ref.txt by transcribing the reference clip with faster-whisper
    (a fast, CPU-friendly Whisper — no torch needed). Used so F5 'just works'."""
    if os.path.exists(REF_TXT) and not force:
        print(f"   caine_ref.txt already exists ({os.path.basename(REF_TXT)}).")
        return open(REF_TXT, encoding="utf-8").read().strip()
    src = best_ref_audio()
    if not os.path.exists(src):
        print("   no reference audio found to transcribe."); return None
    try:
        from faster_whisper import WhisperModel
    except Exception:
        print("   installing faster-whisper (one-time, small)..."); pip("faster-whisper")
        from faster_whisper import WhisperModel
    print(f"   transcribing {os.path.basename(src)} with Whisper (model: base)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")   # fast on CPU
    segments, info = model.transcribe(src, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    if not text:
        print("   Whisper produced no text — is the clip silent?"); return None
    open(REF_TXT, "w", encoding="utf-8").write(text)
    print(f"   detected language: {getattr(info,'language','?')}")
    print(f"   wrote caine_ref.txt -> \"{text[:90]}{'...' if len(text)>90 else ''}\"")
    return text

def trim_wav(src, dst, seconds):
    """Copy the first `seconds` of a .wav to `dst` (same rate/width/channels). Pure
    stdlib (no ffmpeg) — REFS["en"] is always a .wav so this is all we need for F5."""
    import wave
    with wave.open(src, "rb") as w:
        fr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        n = min(w.getnframes(), int(round(seconds * fr)))
        frames = w.readframes(n)
    with wave.open(dst, "wb") as o:
        o.setnchannels(ch); o.setsampwidth(sw); o.setframerate(fr)
        o.writeframes(frames)

def make_f5_ref(force=False, max_sec=11.0):
    """Build F5's reference: a SHORT clip (<=~max_sec) whose transcript matches it.

    F5 estimates the output length from the ref_audio:ref_text ratio and clips any
    reference longer than ~12s — but keeps the FULL transcript. Pairing a 46s
    transcript with a 12s-clipped clip makes F5 think speech is ~4x faster than it is,
    so every line comes out crammed/garbled. Fix: cut the clip to whole transcript
    segments that fit in ~11s, and hand F5 exactly that clip + exactly that text.
    Returns (wav_path, text) or (None, None) on failure. Runs in the PARENT env."""
    src = REFS["en"]
    if not force and os.path.exists(F5_REF_WAV) and os.path.exists(F5_REF_TXT):
        # Reuse the cached short reference UNLESS the source clip is newer than it. The short ref is
        # derived from a static caine_ref.wav, so a plain --force on the CLIPS must NOT re-transcribe
        # it every run — only rebuild when you actually changed your reference recording.
        if not (os.path.exists(src) and os.path.getmtime(src) > os.path.getmtime(F5_REF_WAV)):
            return F5_REF_WAV, open(F5_REF_TXT, encoding="utf-8").read().strip()
    if not os.path.exists(src):
        print("   no English reference audio to build the short voice reference from."); return None, None
    try:
        from faster_whisper import WhisperModel
    except Exception:
        print("   installing faster-whisper (one-time, small)..."); pip("faster-whisper")
        from faster_whisper import WhisperModel
    print(f"   building the short matched voice reference (<= {max_sec:.0f}s, shared by OmniVoice/F5/Qwen3/…) from {os.path.basename(src)}...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(src, vad_filter=True)
    picked, end = [], 0.0
    for s in segments:
        if picked and s.end > max_sec:     # keep WHOLE segments so audio & text stay aligned
            break
        picked.append(s.text.strip()); end = s.end
        if end >= max_sec:
            break
    if not picked:
        print("   Whisper produced no segments — is the clip silent?"); return None, None
    end = min(end, 12.0)                    # never exceed F5's own ~12s clip threshold
    text = " ".join(t for t in picked if t).strip()
    trim_wav(src, F5_REF_WAV, end)
    open(F5_REF_TXT, "w", encoding="utf-8").write(text)
    print(f"   F5 ref ready: {end:.1f}s, \"{text[:80]}{'...' if len(text) > 80 else ''}\"")
    return F5_REF_WAV, text

def clone_ref(lang):
    """Best (wav_path, ref_text) for a clone model. Prefers the SHORT matched clip
    (caine_ref_f5.wav/.txt, ~4-11s) — most clone models (Qwen3 'a 3-second clone',
    OmniVoice/F5/etc.) clone BETTER from a short clip and several explicitly warn that a
    long (>20s) reference degrades quality. Falls back to the full per-language reference
    + its transcript (text may be '' if no transcript exists). The short clip is English;
    for French lines with no French reference it's still the cleanest option we have."""
    if os.path.exists(F5_REF_WAV) and os.path.exists(F5_REF_TXT):
        return F5_REF_WAV, open(F5_REF_TXT, encoding="utf-8").read().strip()
    txt = open(REF_TXT, encoding="utf-8").read().strip() if os.path.exists(REF_TXT) else ""
    return REFS[lang], txt

def write_audit_html():
    rows = [
        ("English — PRE-CLEANED clip (used as-is, no Demucs)", "caine_ref_clean.wav"),
        ("French — PRE-CLEANED clip (used as-is, no Demucs)", "caine_ref_fr_clean.wav"),
        ("English clip — original", "caine_ref.wav"),
        ("English clip — VOICE ONLY (Demucs, used)", "caine_ref_vocals.wav"),
        ("English clip — removed music", "caine_ref_music.wav"),
        ("French clip — original", "caine_ref_fr.wav"),
        ("French clip — VOICE ONLY (Demucs, used)", "caine_ref_fr_vocals.wav"),
        ("French clip — removed music", "caine_ref_fr_music.wav"),
    ]
    cards = ""
    for label, fn in rows:
        exists = os.path.exists(os.path.join(HERE, fn))
        state = "" if exists else " (not found)"
        cards += f'<div class="r"><div class="l">{label}{state}</div><audio controls preload="none" src="{fn}"></audio></div>\n'
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Caine reference audit</title>
<style>body{{font-family:system-ui,Arial;margin:24px;max-width:680px}}h1{{font-size:20px}}
.r{{padding:12px;border:1px solid #ddd;border-radius:10px;margin:10px 0}}
.l{{font-weight:600;margin-bottom:6px}} audio{{width:100%}} .note{{color:#666;font-size:14px}}</style></head>
<body><h1>🤡 Caine reference audit</h1>
<p class="note">Listen to each. The <b>VOICE ONLY</b> files should be clean speech (no music). The
<b>removed music</b> files should be just the backing — that confirms the isolation worked.
Re-run <code>python make_caine_voice.py --isolate</code> after changing a clip, then refresh this page.</p>
{cards}</body></html>"""
    open(os.path.join(HERE, "audit.html"), "w", encoding="utf-8").write(html)
    print(f">> Open this in a browser to LISTEN/AUDIT:  {os.path.join(HERE, 'audit.html')}")

def pick_device():
    import torch
    if torch.cuda.is_available(): return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available(): return "mps"
    return "cpu"

# ---------------- per-model generators -------------------------------------
def gen_chatterbox(clips, outdir, force):
    try:
        import torchaudio as ta
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except Exception:
        pip("chatterbox-tts")
        import torchaudio as ta
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    dev = pick_device()
    print(f"   device={dev}; loading Chatterbox Multilingual...")
    model = ChatterboxMultilingualTTS.from_pretrained(device=dev)
    print(f"   exaggeration={EXAGGERATION}  temperature={TEMPERATURE}  cfg_override={CFG_OVERRIDE}")
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        if CFG_OVERRIDE is not None:  cfg = CFG_OVERRIDE
        elif lang == "fr":            cfg = 0.3 if FR_NATIVE else 0.0   # EN ref -> 0 avoids accent on FR
        else:                         cfg = CFG_EN
        gkw = dict(language_id=lang, audio_prompt_path=REFS[lang], exaggeration=EXAGGERATION, cfg_weight=cfg)
        try:
            wav = model.generate(text, temperature=TEMPERATURE, **gkw)   # newer chatterbox
        except TypeError:
            wav = model.generate(text, **gkw)                            # older chatterbox (no temperature arg)
        ta.save(out, wav.detach().cpu() if hasattr(wav,"detach") else wav, model.sr)
        print(f"   [{n}/{len(clips)}] {base}")

def gen_xtts(clips, outdir, force):
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    try:
        from TTS.api import TTS
    except Exception:
        pip("coqui-tts", "soundfile")
        from TTS.api import TTS
    dev = "cuda" if pick_device() == "cuda" else "cpu"
    print(f"   device={dev}; loading XTTS v2...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(dev)
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        tts.tts_to_file(text=text, speaker_wav=REFS[lang], language=lang, file_path=out)
        print(f"   [{n}/{len(clips)}] {base}")

def gen_f5(clips, outdir, force):
    # Use the SHORT, transcript-matched reference (built by make_f5_ref in the parent).
    # Falling back to the full clip + full transcript is what caused the garbled output,
    # so only do that if the short ref is somehow missing.
    ref_wav  = F5_REF_WAV if os.path.exists(F5_REF_WAV) else REFS["en"]
    txt_path = F5_REF_TXT if os.path.exists(F5_REF_TXT) else REF_TXT
    if not os.path.exists(txt_path):
        raise RuntimeError("F5 needs a transcript (caine_ref_f5.txt / caine_ref.txt). Skipping.")
    ref_text = open(txt_path, encoding="utf-8").read().strip()
    try:
        from f5_tts.api import F5TTS
    except Exception:
        pip("f5-tts")
        from f5_tts.api import F5TTS
    print(f"   loading F5-TTS  (ref: {os.path.basename(ref_wav)}, matched ref_text {len(ref_text)} chars)...")
    f5 = F5TTS()
    print(f"   knobs: nfe={knob('f5','nfe','en')} cfg={knob('f5','cfg','en')} speed={knob('f5','speed','en')} (EN); "
          f"nfe={knob('f5','nfe','fr')} cfg={knob('f5','cfg','fr')} speed={knob('f5','speed','fr')} (FR)")
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        f5.infer(ref_file=ref_wav, ref_text=ref_text, gen_text=text, file_wave=out,
                 nfe_step=knob("f5", "nfe", lang), cfg_strength=knob("f5", "cfg", lang), speed=knob("f5", "speed", lang))
        print(f"   [{n}/{len(clips)}] {base}")

def styled(base):
    """Global character + per-line emotion, as one instruction string."""
    e = clip_desc(base)
    return (VOICE_DESC + (". " + e + "." if e else "")).strip()

def gen_qwen3(clips, outdir, force):
    """Qwen3-TTS Base (Apache-2.0): faithful voice CLONE from your sample. EN+FR.

    The reference voice is encoded ONCE (create_voice_clone_prompt) and that prompt is
    reused for every line — faster, and keeps the cloned timbre consistent across clips.
    'instruct'/voice-description does NOT apply to the clone path (the qwen-tts API only
    accepts 'instruct' on generate_custom_voice / generate_voice_design, which use a
    built-in or designed voice rather than cloning yours), so we do a clean clone that
    actually uses caine_ref + caine_ref.txt. non_streaming_mode=True renders each line in
    a single pass (cleaner than chunked streaming for offline files). If the prebuilt
    prompt path ever errors we fall back to the proven per-clip reference call."""
    import torch, soundfile as sf
    from qwen_tts import Qwen3TTSModel
    use_cuda = pick_device() == "cuda"
    print(f"   loading Qwen3-TTS-1.7B-Base (clone), cuda={use_cuda}...")
    model = None
    for kw in ([dict(device_map="cuda:0", dtype=torch.bfloat16)] if use_cuda else []) + [dict(device_map="auto"), {}]:
        try:
            model = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-Base", **kw); break
        except Exception as e:
            print(f"   load attempt {kw} failed: {str(e)[:70]}")
    if model is None:
        raise RuntimeError("Could not load Qwen3-TTS-Base.")
    # Qwen3 is literally "a 3-second voice clone" — feeding it the full ~46s reference is
    # almost certainly why fidelity felt weak, so clone from the SHORT matched clip.
    ref_path, ref_text = clone_ref("en")
    if not ref_text:
        raise RuntimeError("Qwen3 clone needs a transcript (caine_ref_f5.txt / caine_ref.txt).")
    print(f"   reference: {os.path.basename(ref_path)} ({len(ref_text)} chars of matched text)")
    langmap = {"en": "English", "fr": "French"}

    # Build the clone prompt ONCE (single short reference) and reuse it for every line (T1).
    prompt_cache = {}
    def get_prompt():
        if "p" not in prompt_cache:
            try:
                prompt_cache["p"] = model.create_voice_clone_prompt(ref_audio=ref_path, ref_text=ref_text)
            except Exception as e:
                print(f"   (prebuilt clone prompt unavailable, using per-clip reference: {str(e)[:60]})")
                prompt_cache["p"] = None
        return prompt_cache["p"]

    def synth(text, lang, prompt):
        lid = langmap.get(lang, "Auto")
        if prompt is not None:
            return model.generate_voice_clone(text, language=lid, voice_clone_prompt=prompt,
                                              non_streaming_mode=True)
        return model.generate_voice_clone(text, language=lid, ref_audio=ref_path,
                                          ref_text=ref_text, non_streaming_mode=True)

    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        prompt = get_prompt()
        try:
            try:
                wavs, sr = synth(text, lang, prompt)
            except Exception as e_prompt:
                if prompt is not None:   # disable the prompt path and retry with the proven call
                    print(f"   (clone-prompt path failed: {str(e_prompt)[:60]}; falling back to per-clip ref)")
                    prompt_cache["p"] = None
                    wavs, sr = synth(text, lang, None)
                else:
                    raise
            wav = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
            sf.write(out, wav, sr); print(f"   [{n}/{len(clips)}] {base}")
        except Exception as e:
            # leave the clip blank on failure — never fake it with another model's audio
            print(f"   [{n}/{len(clips)}] {base}  FAILED (left blank): {str(e)[:90]}")

def gen_openaudio(clips, outdir, force):
    """OpenAudio / Fish-Speech **S1-mini** (CC-BY-NC-SA, fine for a private party): inline
    (emotion) tags, EN+FR, ~4GB VRAM (CPU possible but slow). 3-stage CLI: (1) encode the
    reference voice to tokens, (2) text2semantic with that reference prompt, (3) decode to wav.
    On any failure the clip is left blank (never faked). Needs the reference transcript."""
    repo = os.path.join(VENV_ROOT, ".venv_openaudio", "fish-speech")
    mdir = os.path.join(repo, "checkpoints", "openaudio-s1-mini")   # the model checkpoint dir
    codec = os.path.join(mdir, "codec.pth")                         # the DAC codec weights
    py = sys.executable   # we run inside the openaudio venv
    ref_wav, ref_text = clone_ref("en")   # short matched clip + its transcript (prompt must match)
    if not os.path.exists(codec):
        raise RuntimeError("OpenAudio weights not found — env setup may have failed (see log).")
    # Step 1: VQ tokens from the reference voice (once) -> fake.npy
    subprocess.check_call([py, "fish_speech/models/dac/inference.py", "-i", ref_wav,
                           "--checkpoint-path", codec], cwd=repo)
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        # S1 emotion markers are parenthesised, e.g. "(excited) ..." (best-effort in French).
        tagged = f"({clip_desc(base)}) {text}" if clip_desc(base) else text
        try:
            subprocess.check_call([py, "fish_speech/models/text2semantic/inference.py",
                                   "--text", tagged, "--prompt-text", ref_text,
                                   "--prompt-tokens", "fake.npy",
                                   "--checkpoint-path", mdir], cwd=repo)
            subprocess.check_call([py, "fish_speech/models/dac/inference.py",
                                   "-i", "codes_0.npy", "--checkpoint-path", codec], cwd=repo)
            shutil.copy(os.path.join(repo, "fake.wav"), out); print(f"   [{n}/{len(clips)}] {base}")
        except Exception as e:
            # leave the clip blank on failure — never fake it with another model's audio
            print(f"   [{n}/{len(clips)}] {base}  FAILED (left blank): {str(e)[:90]}")

def gen_omnivoice(clips, outdir, force):
    """OmniVoice (k2-fsa, Apache-2.0): multilingual zero-shot clone with **native French**.
    The target language is inferred from the text itself — there is NO language argument, we
    just pass the French/English line. The reference transcript (ref_text) is optional but
    avoids an extra Whisper pass, so we hand it over when we have it. ~2.45GB weights, 24kHz."""
    import torch, soundfile as sf
    from omnivoice import OmniVoice
    dev = pick_device()
    device_map = {"cuda": "cuda:0", "mps": "mps"}.get(dev, "cpu")
    dtype = torch.float16 if dev == "cuda" else torch.float32
    print(f"   loading OmniVoice (device={device_map}, dtype={dtype})...")
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device_map, dtype=dtype, load_asr=False)
    # OmniVoice warns that a reference >20s degrades quality, so use the SHORT matched clip.
    ref_audio, ref_text = clone_ref("en")
    ref_text = ref_text or None
    # ONE generation config for ALL clips (the EN knob). OmniVoice infers the language from the text,
    # and French actually renders BETTER with the EN settings (lower guidance) than with a separate,
    # higher-guidance "FR" config — the cross-lingual French over-constrains and degrades. So we do NOT
    # pass a French-specific config; English and French both use the EN knob.
    gcfg = None
    try:
        from omnivoice.models.omnivoice import OmniVoiceGenerationConfig
        gcfg = OmniVoiceGenerationConfig(num_step=knob("omnivoice", "steps", "en"),
                                         guidance_scale=knob("omnivoice", "guidance", "en"))
    except Exception as e:
        print(f"   (could not set generation config: {str(e)[:60]})")
    print(f"   reference: {os.path.basename(ref_audio)}  "
          f"(one config for EN+FR: guidance={knob('omnivoice','guidance','en')}/{knob('omnivoice','steps','en')}st)")
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        try:
            t0 = time.time()
            kw = {"generation_config": gcfg} if gcfg else {}
            audio = model.generate(text=text, ref_audio=ref_audio, ref_text=ref_text, **kw)
            gen_s = time.time() - t0
            wav = audio[0] if isinstance(audio, (list, tuple)) else audio
            if hasattr(wav, "detach"): wav = wav.detach().cpu().numpy()
            sf.write(out, wav, 24000)
            dur = len(wav) / 24000.0
            print(f"   [{n}/{len(clips)}] {base}  (gen {gen_s:.1f}s for {dur:.1f}s audio, {gen_s/dur:.2f}x realtime)")
        except Exception as e:
            print(f"   [{n}/{len(clips)}] {base}  FAILED (left blank): {str(e)[:90]}")

def gen_cosyvoice(clips, outdir, force):
    """CosyVoice2-0.5B (FunAudioLLM, Apache-2.0): clone + natural-language STYLE in one call
    via inference_instruct2 (timbre from your clip, delivery from the instruction). The current
    model cards list French among 9 languages, so we generate EN and FR. Windows needs the
    pynini/WeTextProcessing workaround (see README); if normalisation is missing we retry with
    text_frontend=False. On any failure the clip is left blank (never faked)."""
    import sys as _sys, torchaudio
    repo = os.path.join(VENV_ROOT, ".venv_cosyvoice", "CosyVoice")
    mtcha = os.path.join(repo, "third_party", "Matcha-TTS")
    # CosyVoice isn't pip-installed — it's imported from the repo. Put the repo ROOT (the
    # 'cosyvoice' package) AND its bundled Matcha-TTS on the path.
    for p in (mtcha, repo):
        if p not in _sys.path: _sys.path.insert(0, p)
    from cosyvoice.cli.cosyvoice import CosyVoice2
    mdir = os.path.join(repo, "pretrained_models", "CosyVoice2-0.5B")
    print("   loading CosyVoice2-0.5B (clone + instruct)...")
    cosy = CosyVoice2(mdir, load_jit=False, load_trt=False, fp16=(pick_device() == "cuda"))
    ref_wav, _ = clone_ref("en")          # short matched clip for the timbre prompt
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        instruct = styled(base) + "<|endofprompt|>"               # global character + per-line emotion
        try:
            try:
                chunks = list(cosy.inference_instruct2(text, instruct, ref_wav, stream=False))
            except Exception:   # text normalisation (pynini) unavailable -> bypass it
                chunks = list(cosy.inference_instruct2(text, instruct, ref_wav, stream=False, text_frontend=False))
            if not chunks: raise RuntimeError("no audio produced")
            # int16 PCM (like the other models) — float WAV can be flaky in iPad Safari.
            torchaudio.save(out, chunks[0]["tts_speech"], cosy.sample_rate,
                            encoding="PCM_S", bits_per_sample=16)
            print(f"   [{n}/{len(clips)}] {base}")
        except Exception as e:
            print(f"   [{n}/{len(clips)}] {base}  FAILED (left blank): {str(e)[:90]}")

def gen_indextts2(clips, outdir, force):
    """IndexTTS-2 (bilibili licence; non-commercial OK): emotion-controllable zero-shot clone.
    **English/Chinese ONLY** — it does not speak French, so French clips are left BLANK (never
    faked). Audio-only clone (no transcript). Emotion comes from a natural-language description
    (emo_text + emo_alpha). Needs ~8-12GB GPU; CPU is very slow."""
    import torch  # noqa: F401  (ensures torch is importable / device set up)
    from indextts.infer_v2 import IndexTTS2
    ckpt = os.path.join(VENV_ROOT, ".venv_indextts2", "index-tts", "checkpoints")
    use_fp16 = pick_device() == "cuda"
    print(f"   loading IndexTTS-2 (fp16={use_fp16})...")
    tts = IndexTTS2(cfg_path=os.path.join(ckpt, "config.yaml"), model_dir=ckpt,
                    use_fp16=use_fp16, use_cuda_kernel=False)
    ref_wav, _ = clone_ref("en")          # short matched clip (IndexTTS-2 is audio-only)
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        # French is NOT an official output language for IndexTTS-2, but we still attempt it
        # (it pronounces the French text with an English/Chinese accent — judge it by ear).
        emo = clip_desc(base) or "theatrical, larger-than-life"
        try:
            tts.infer(spk_audio_prompt=ref_wav, text=text, output_path=out,
                      use_emo_text=True, emo_text=emo, emo_alpha=knob("indextts2", "emo_alpha", "en"),
                      use_random=False)
            print(f"   [{n}/{len(clips)}] {base}")
        except Exception as e:
            print(f"   [{n}/{len(clips)}] {base}  FAILED (left blank): {str(e)[:90]}")

def gen_higgs(clips, outdir, force):
    """Higgs Audio v2 (Boson AI, Apache-2.0 code): expressive zero-shot clone via a ChatML prompt
    (system 'scene' description + reference transcript turn + reference-audio turn + the new
    line). English-focused (no official French; best-effort) and HEAVY — needs ~24GB GPU and is
    effectively CUDA-only. On any failure the clip is left blank. Needs the reference transcript."""
    import base64, torch, torchaudio
    from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine
    from boson_multimodal.data_types import ChatMLSample, Message, AudioContent
    ref_wav, ref_text = clone_ref("en")   # short matched clip + its transcript
    if not ref_text:
        raise RuntimeError("Higgs needs a transcript (caine_ref_f5.txt / caine_ref.txt).")
    dev = "cuda" if pick_device() == "cuda" else "cpu"
    print(f"   loading Higgs Audio v2 (device={dev}; ~24GB GPU recommended, weights ~14GB)...")
    engine = HiggsAudioServeEngine("bosonai/higgs-audio-v2-generation-3B-base",
                                   "bosonai/higgs-audio-v2-tokenizer", device=dev)
    with open(ref_wav, "rb") as f:
        ref_b64 = base64.b64encode(f.read()).decode("utf-8")     # reference clip as base64
    for n,(base,lang,text) in enumerate(clips,1):
        out = os.path.join(outdir, base+".wav")
        if os.path.exists(out) and not force: continue
        scene = (VOICE_DESC + (". " + clip_desc(base) if clip_desc(base) else "")).strip()
        sysmsg = "Generate audio following instruction.\n\n<|scene_desc_start|>\n" + scene + "\n<|scene_desc_end|>"
        msgs = [Message(role="system", content=sysmsg),
                Message(role="user", content=ref_text),                                   # ref transcript
                Message(role="assistant", content=AudioContent(raw_audio=ref_b64, audio_url="placeholder")),
                Message(role="user", content=text)]                                       # new line to speak
        try:
            resp = engine.generate(chat_ml_sample=ChatMLSample(messages=msgs),
                                   max_new_tokens=1024, temperature=0.3, top_p=0.95, top_k=50,
                                   stop_strings=["<|end_of_text|>", "<|eot_id|>"])
            torchaudio.save(out, torch.from_numpy(resp.audio)[None, :], resp.sampling_rate)
            print(f"   [{n}/{len(clips)}] {base}")
        except Exception as e:
            print(f"   [{n}/{len(clips)}] {base}  FAILED (left blank): {str(e)[:90]}")

MODELS = {"chatterbox": gen_chatterbox, "xtts": gen_xtts, "f5": gen_f5,
          "qwen3": gen_qwen3, "openaudio": gen_openaudio,
          "omnivoice": gen_omnivoice, "cosyvoice": gen_cosyvoice,
          "indextts2": gen_indextts2, "higgs": gen_higgs}

# Clone-from-wav models that need the reference TRANSCRIPT (the short ref's .txt, or caine_ref.txt
# as a fallback). cosyvoice (instruct2) and indextts2 (audio-only) don't use a transcript.
TRANSCRIPT_MODELS = ("qwen3", "openaudio", "higgs", "omnivoice")
# Models that clone BEST from a SHORT reference (~3-10s). They reuse the short matched clip
# caine_ref_f5.wav/.txt (built by make_f5_ref) via clone_ref(), instead of the full ~46s clip —
# Qwen3 is "a 3-second clone" and OmniVoice/others warn a long reference degrades quality.
SHORT_REF_MODELS = ("f5", "qwen3", "omnivoice", "openaudio", "cosyvoice", "indextts2", "higgs")

def run_one_model(key, clips, outdir, force, test_only):
    """Run a model here, unless it needs an isolated env — then auto-build it and
    re-invoke this script inside that env (so the Studio 'just works')."""
    in_parent = not os.environ.get("CAINE_IN_VENV")
    if in_parent:
        if key in SHORT_REF_MODELS:
            # Build the short matched reference (caine_ref_f5.wav/.txt) these models clone from — once,
            # and only rebuilt when caine_ref.wav itself changes (NOT on every clip --force). It is the
            # shared short clone clip, not F5-specific work.
            swav = make_f5_ref()[0]
            if not swav and key == "f5":
                raise RuntimeError("Couldn't build the short voice reference (transcription failed).")
        if key in TRANSCRIPT_MODELS and not os.path.exists(REF_TXT):
            # Fallback transcript (used only if the short ref above couldn't be built).
            print(f"   {key} needs a transcript of your clip — auto-transcribing with Whisper...")
            if not transcribe():
                raise RuntimeError("Couldn't auto-transcribe; add caine_ref.txt manually.")
    spec = ISOLATED_ENVS.get(key)
    if spec and not os.environ.get("CAINE_IN_VENV"):
        py = ensure_venv(spec)
        ca = [os.path.abspath(__file__), f"--model={key}", "--no-isolate", f"--voice-desc={VOICE_DESC}"]
        if force: ca.append("--force")
        if test_only: ca.append("--test")
        if ONLY_CLIP: ca.append(f"--only={ONLY_CLIP}")
        if LANG in ("en", "fr"): ca.append(f"--lang={LANG}")     # pass the language filter into the venv
        print(f"   running {key} inside isolated env '{spec['dir']}'...")
        subprocess.check_call([py] + ca, env=dict(os.environ, CAINE_IN_VENV="1"), cwd=HERE)
    else:
        MODELS[key](clips, outdir, force)

def main():
    global REFS, FR_NATIVE, EXAGGERATION, TEMPERATURE, CFG_OVERRIDE, VOICE_DESC, ONLY_CLIP, LANG
    start_log()
    try: write_host_manifest()                # keep the Party Guide's soundboard in sync
    except Exception: pass
    args = sys.argv[1:]
    force = "--force" in args
    for a in args:
        if a.startswith("--only="):
            ONLY_CLIP = a.split("=", 1)[1].strip(); force = True   # regenerate that single clip
    selected = list(MODELS.keys())
    j = 0
    while j < len(args):
        a = args[j]
        if a.startswith("--model="):        selected = [a.split("=",1)[1]]
        elif a.startswith("--models="):      selected = a.split("=",1)[1].split(",")
        elif a == "--model"  and j+1 < len(args):  selected = [args[j+1]];            j += 1
        elif a == "--models" and j+1 < len(args):  selected = args[j+1].split(",");   j += 1
        elif a.startswith("--exaggeration="): EXAGGERATION = float(a.split("=",1)[1])  # chatterbox
        elif a.startswith("--temperature="):  TEMPERATURE  = float(a.split("=",1)[1])  # chatterbox
        elif a.startswith("--cfg="):          CFG_OVERRIDE = float(a.split("=",1)[1])  # chatterbox
        elif a.startswith("--voice-desc="):   VOICE_DESC   = a.split("=",1)[1]          # qwen3/openaudio
        elif a.startswith("--lang="):
            _v = a.split("=",1)[1].strip().lower();  LANG = _v if _v in ("en","fr") else None   # else = both
        j += 1
    selected = [m.strip() for m in selected if m.strip() in MODELS]

    # --- auto-transcribe the reference clip into caine_ref.txt (for F5) ---
    if "--transcribe" in args:
        transcribe(force=force)
        return

    # --- vocal isolation (for clips that have background music) ---
    if "--isolate" in args or "--reisolate" in args:
        print(">> Isolating voice from reference clips (Demucs)...")
        got_en = isolate_file(EN_RAW, EN_VOC, EN_MUS, force=True)
        got_fr = isolate_file(FR_RAW, FR_VOC, FR_MUS, force=True)
        if not got_en and not got_fr:
            print("!! No caine_ref.wav (or caine_ref_fr.wav) found to isolate."); sys.exit(1)
        write_audit_html()
        print("\n>> Open audit.html in a browser and LISTEN to confirm the voice is clean.")
        print("   Then run:  python make_caine_voice.py\n")
        return

    use_raw  = "--raw" in args
    skip_iso = use_raw or "--no-isolate" in args

    # ---- English reference ----
    # Priority: a PRE-CLEANED clip you provide (caine_ref_clean.mp3/.wav) -> used as-is,
    # isolation bypassed. Otherwise caine_ref.wav, cleaned with Demucs (unless skipped).
    clean_en = find_clean("caine_ref_clean")
    if clean_en:
        REFS["en"] = clean_en
        print(f">> English: using your pre-cleaned clip (isolation bypassed): {os.path.basename(clean_en)}")
    elif os.path.exists(EN_RAW):
        if not skip_iso:
            print(">> Cleaning the English voice (Demucs)...")
            isolate_file(EN_RAW, EN_VOC, EN_MUS, force=force)
        REFS["en"] = EN_VOC if (not use_raw and os.path.exists(EN_VOC)) else EN_RAW
        print(f">> English ref: {os.path.basename(REFS['en'])}")
    else:
        print("!! No English reference found. Put ONE of these in this folder:")
        print("     caine_ref_clean.mp3   (already voice-only — used directly)")
        print("     caine_ref.wav         (will be cleaned with Demucs)")
        sys.exit(1)

    # ---- French reference (optional) ----
    clean_fr = find_clean("caine_ref_fr_clean")
    if clean_fr:
        REFS["fr"] = clean_fr; FR_NATIVE = True
        print(f">> French: using your pre-cleaned clip: {os.path.basename(clean_fr)}")
    elif os.path.exists(FR_RAW):
        if not skip_iso and not os.path.exists(FR_VOC):
            print(">> Cleaning the French voice (Demucs)...")
            isolate_file(FR_RAW, FR_VOC, FR_MUS, force=force)
        REFS["fr"] = FR_VOC if (not use_raw and os.path.exists(FR_VOC)) else FR_RAW
        FR_NATIVE = True
    else:
        REFS["fr"] = REFS["en"]; FR_NATIVE = False

    write_audit_html()

    print("\n=== Caine Voice — multi-model generator ===")
    print(f"   English ref: {os.path.basename(REFS['en'])}")
    print(f"   French  ref: {os.path.basename(REFS['fr'])}" + ("" if FR_NATIVE else "  (no French clip — French will carry an English accent; add caine_ref_fr.wav to fix)"))
    print("   Models:", ", ".join(selected),
          f"|  chatterbox: exaggeration={EXAGGERATION} temperature={TEMPERATURE}\n")

    test_only = "--test" in args
    if ONLY_CLIP:
        # Regenerate a single clip. Pick it from the test set if it's test_en/test_fr, else the full set.
        base_clips = build_test_clips() if ONLY_CLIP.startswith("test_") else build_clips()
        clips = [(b, l, t) for (b, l, t) in base_clips if b == ONLY_CLIP]
        if not clips:
            print(f"!! --only={ONLY_CLIP}: no such clip."); sys.exit(1)
        print(f">> SINGLE CLIP: regenerating only '{ONLY_CLIP}'.\n")
    elif test_only:
        clips = build_test_clips()
        print(">> TEST MODE: generating only the welcome phrase (test_en / test_fr).\n")
    else:
        clips = build_clips()
        with open(os.path.join(HERE, "lines_generated.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["basename","lang","text"])
            for b,l,t in clips: w.writerow([b,l,t])

    if LANG in ("en", "fr") and not ONLY_CLIP:        # --lang=en|fr : regenerate just one language
        clips = [(b, l, t) for (b, l, t) in clips if l == LANG]
        print(f">> LANGUAGE: generating {LANG.upper()} only ({len(clips)} clips).\n")

    in_venv = bool(os.environ.get("CAINE_IN_VENV"))
    done = []
    for key in selected:
        outdir = os.path.join(OUTROOT, key); os.makedirs(outdir, exist_ok=True)
        print(f">> MODEL: {key}  ->  {outdir}")
        try:
            run_one_model(key, clips, outdir, force, test_only)
            done.append(key); print(f"   OK: {key} done.\n")
        except Exception as e:
            print(f"   !! {key} skipped: {e}")
            print(f"      (See the messages above for the real reason.)\n")
            if in_venv:
                sys.exit(1)   # so the parent knows this model truly failed

    print("=== Finished ===")
    print("Generated models:", ", ".join(done) if done else "(none)")
    print(f"Audio root: {OUTROOT}")
    print("Open caine-console/index.html, use the VOICE switcher to A/B models.\n")

if __name__ == "__main__":
    main()
