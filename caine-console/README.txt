C.A.I.N.E. CONSOLE — the talking iPad for the adventure
=======================================================

WHAT IT IS
A full-screen app for the iPad. It walks through the whole adventure
step by step. Each step shows the words and PLAYS CAINE'S VOICE saying
them. You hold the iPad, play "Bubble" (Caine's helper), and press
NEXT to move the adventure along. The exit-code screen is built in near
the end, and it flows into the cake.

If you haven't made the voice audio yet, the console still works — it
just shows the words for you to read aloud. (See the caine-voice folder
to generate Caine's voice with the kids' names baked in.)

SETUP
1. Generate the voice audio (see caine-voice/README.md) and put the
   "audio" folder inside this "caine-console" folder. Audio is organised
   by voice model, so you have e.g.:
       caine-console/index.html
       caine-console/audio/chatterbox/s01_en.wav  s01_fr.wav ...
       caine-console/audio/xtts/...   (if you generated it too)
   Each step plays ENGLISH first, a short pause, then FRENCH.
   (Skip this to test — the console works without audio, showing the words.)

   VOICE SWITCHER: the buttons at the top (OmniVoice / IndexTTS-2 / F5) let you
   play whichever voice you like best. A greyed-out button means that
   model's audio isn't in the folder.

   WHO'S COMING: edit the ROSTER near the top of index.html and set
   present:true/false for each child (Nina, Max, Theo). The reveal names
   only present kids. Audio for everyone is already there — no regenerating.

2. Open it on the iPad:
   - EASIEST (offline): copy the caine-console folder to the iPad (e.g.
     via Files / AirDrop / a USB) and open index.html in Safari. Works
     with no internet.
   - OR upload the caine-console folder to DreamHost and open
     https://yourdomain.com/caine-console/ in Safari.
   - Add it to the Home Screen (Share -> Add to Home Screen) for a clean
     full-screen tap-to-open on the day.

3. The FIRST time, tap "▶ Play Caine" once (Safari requires one tap
   before it will auto-play sound). After that, each step auto-plays.

USING IT ON THE DAY (you = Bubble)
- Big NEXT button advances the story. Back arrow goes back.
- Each step has a little "You (Bubble)" note telling you what to do
  (hand out masks, run the game, lead the Gloink hunt, etc.).
- The colour-code screen near the end: the kids must work out the code
  themselves = the ORDER they found the Gloinks. Caine never says it and
  the buttons are shuffled. No time limit; it never opens by itself
  (tap NEXT on the remote if you ever need to move on). Then they ESCAPE,
  hunt the hidden treasure, and Caine calls cake time.

EDIT NAMES ON SCREEN
Open index.html in any text editor and change the line near the top:
    const STAR = "Nora";
(The spoken audio gets its names from lines.csv when you generate it.)
