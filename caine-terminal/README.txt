C.A.I.N.E. TERMINAL — iPad page for Nora's Digital Circus party
=================================================================

WHAT IT IS
A tiny one-page website (the simple standalone version — the main party
uses the caine-console app with audio + 3D Caine). The kids tap the 4
Gloink colours and the screen plays a "SYNCING... EXIT UNLOCKED"
celebration with confetti.

NOTE: the live party flow has since changed — the code is now the ORDER
the kids FOUND the Gloinks (they must work it out themselves), the door
opens to an ESCAPE, then they hunt a HIDDEN treasure, and only then is it
cake time (cake is set up upstairs, not behind the door). This legacy
terminal still uses the old fixed-order screen; for the real party use
the caine-console app.

PUT IT ON DREAMHOST (recommended)
1. Log in to DreamHost. Open the file manager (or use SFTP / FTP).
2. Go to your domain's web folder (e.g. /home/USER/yourdomain.com/).
3. Upload the WHOLE "caine-terminal" folder into it.
4. On the iPad's Safari, go to:  https://yourdomain.com/caine-terminal/
5. Add it to the Home Screen (Share -> Add to Home Screen) so it opens
   full-screen with one tap on the day.

NO INTERNET AT THE PARTY?
The page is fully self-contained. If you prefer, you can also just
open index.php's logic locally, OR skip the iPad entirely and open the
door manually on Caine's cue — the iPad is a fun bonus, not required.
(Note: opening a .php file directly without a server only shows code,
so for offline use rename index.php to index.html — it still works,
because all the logic is in the browser.)

CHANGE THE CODE
Open index.php, find this line near the top:
    $EXIT_CODE = ['red','yellow','purple','blue'];
Reorder the colours to whatever you like. Make sure the printed
Exit Door card shows the same order so the kids can follow it.

TEST IT BEFORE THE PARTY
Tap a wrong order on purpose: it "glitches" and shakes, and after two
tries it shows the hint. Tap the right order: confetti + EXIT UNLOCKED.
The "Reset terminal" button puts it back for the next try.
