# TASlation detailed manual

日本語: [MANUAL.ja.md](MANUAL.ja.md)

This is a translation. The Japanese text, [MANUAL.ja.md](MANUAL.ja.md), is the original, and it prevails where the two differ.

Everyday use is explained in the app, under "Menu > Help > How to use...". This manual gathers the detailed explanations: the settings, the command line and so on.

TASlation does real-time translation: you read the book in its viewer as it is, and each page you turn there is lettered in your language over the viewer's window.
There is no account to make and no limit on the pages it translates. Nothing of your books leaves this computer: the pages are read and translated on it
(see "Checking for yourself that it works offline").

## How to use

1. Open the book in the viewer and show the page where you want to start.
2. Start TASlation from "TASlation" in the Start menu. TASlation has no window of its own on the screen: it lays its lettering over the viewer's window
   and puts two side panes on the viewer's ground beside the page (see "The side panes").
3. At every start, after the legal notice (and the box that comes when the GPU's memory is short), TASlation asks which window is the viewer: a small dialog
   with a "Viewer" list of the windows on the screen, each named as its taskbar button is (a browser window by its tab's title and the browser's name;
   a long name is shortened in the middle). TASlation never chooses a window by itself. It carries no list of stores or viewers: the viewer you chose before
   comes first in the list and is already selected, so Enter or "OK" is enough; then come the windows whose titles look like a viewer's (without the viewer you chose before, the first of them
   is selected), then the rest. A browser window is listed by the title of the tab in front, so when the book is in a browser, bring its tab to the front first (the line under the list says so).
   When none looks like one, nothing is selected and "OK" is greyed until you choose the viewer's window in the list. "List again" lists the windows again
   (a window opened while the dialog is up comes into the list by itself too), and "Quit" ends TASlation. Nothing of any window is followed, shown or read
   before you press "OK"; then the right pane's foot says "Viewer: <title>" for as long as that window is followed. When the viewer's window is closed, the lettering and the side panes go
   and the same dialog comes again, saying so: a new window of the same viewer is selected in it, not chosen by itself. "Menu > Viewer..." opens the dialog
   to choose another window (its last button is then "Close"). A browser window is judged by its tab title without the browser's name. In a browser-based reader,
   the part that is the page, without the tabs, the address bar and the reader's own frame, is found automatically, and only that part is read. If that does not work, use "Menu" > "Set area..." once
   and drag a rectangle around the page on the picture it shows (it is remembered per window). The area you set is treated as an outer frame,
   and the page part is looked for and read inside it as well (the part found is shown with a dashed line). The rectangle is resized with its eight handles, moved by dragging inside it,
   and drawn again by dragging outside it. Enter confirms, Esc cancels, and "Clear area" goes back to finding the page automatically.
4. Read in the viewer as it is: turn the pages there, with its own keys, buttons or clicks. TASlation presses no key and sends no click to the viewer,
   turns no page by itself, and reads only the page the viewer shows. "Auto" is on from the start: each page you turn is translated, or lettered from the cache.
   "Translate" in the left pane processes the page on show by hand (when the page is in the cache, it is lettered from there); the circular arrow at the right end of its row
   translates it again without using the cache (see "Editing: correcting the page"). If you press Translate while the OCR model is still loading, for example, it runs as soon as it can.
   "Lettering" hides TASlation's lettering, so that the page shows as the viewer has it, and shows it again.

The lettering lies in a window of its own over the viewer's. In Reader mode it takes no click and no key: every click and key goes to the viewer, as without TASlation,
Insert alone excepted, which adds a text area while the viewer is in front. While editing (as TASlation starts), the mouse over the viewer's window is TASlation's and the keys
stay the viewer's (Delete excepted while a region is selected: it drops it): turn the pages with the keys (see "Editing: correcting the page"). Each piece of the lettering belongs to the pixels
it was made from, and shows only while the viewer shows those very pixels there: when you turn the page, the old lettering goes at the first picture of the new page,
and where the viewer draws something over the page (a bar, a menu, a panel) or another window lies over it, the lettering there is left out.
A page whose translations are all in the cache is lettered as soon as the viewer shows it.
With a viewer that has drawn a blurred picture first, though, a blurred picture is left as it is, and the page is lettered from the cache as soon as the sharp picture arrives
(on a blurred picture only some of the bubbles are found, and the translations would sit off their places). While editing,
once the picture has settled (no new picture for 0.4 seconds), the page is read once more and the bubbles not in the cache are added.
While the viewer is in front, each new picture it draws is looked at (and it is looked at every 0.7 seconds besides); while another program is in front, it is not looked at
(after a move, a resize or a tab switch it is looked at once). Windows tells it which window is in front, so it does not read the contents of other windows.
With `follow = "poll"` in `taslation.toml`, it always looks every 0.7 seconds.
A picture to wait out (a loading screen, half of a spread, a faded preview) starts nothing. While the viewer shows its own bars over the page (a toolbar or a page slider,
which most viewers hide again by themselves after a moment), the page is read only once they have stayed 3.5 seconds, with their rows left out; once they have gone,
the bubbles they cut are read again.
A page that is not in the cache is read from the first new picture, without waiting for the picture to settle.
As soon as it has been read, and a look has found the picture still the same, the model is asked for its translations, and the picture is
watched while the model answers. What it translates is kept in the cache only once the picture has stayed the same for 0.8 seconds (twice the
`settle_ms` setting, the same for every viewer). If the picture changes before that (a page sliding in, a blurred picture replaced by the sharp one),
the request is stopped, what was read from the picture is dropped and the page is read again from the new picture.
A sharp picture that replaces a blurred one later than that drops what was kept from the blurred picture too: while its translation still runs,
and with a viewer that has drawn a blurred picture first, up to 2 seconds after it is done.
With `early_start = false` in `taslation.toml`, a page is read only once its picture has stayed the same for `settle_ms`, as in earlier versions.
A page turned while another is being translated shows at once as the viewer draws it, with nothing of the other page's lettering over it;
that translation is stopped only once the new picture has stayed the same for a moment (0.15 seconds; a black flash or a loading indicator stops
nothing, and back on that page, its lettering shows again), and the new page is read then. A page already translated and on show,
whose work is only to get its next showing ready, gives way at once.
The bubbles the stopped page had translated by then stay in the cache, the page marked as not finished (only when its picture had stayed the same for 0.8 seconds, as above):
back on it, they are lettered at once and only the rest is read and translated. A page stopped with "Stop" in the left pane keeps nothing.

An untranslated page fills in while you look at it. The bubbles are translated in the order the page's bubbles are read, each with the lines before it as context.
Each bubble is lettered as soon as its translation is ready.
A line goes to the translator as soon as it is read, before the rest of the page is read, so the first bubbles come sooner; once the page is read,
a bubble translated that early may be replaced (for example when the reading order turned out different): it shows without lettering for a moment and is lettered again. At the end,
names spelled differently from the series sheet are made consistent mechanically, so a few bubbles may change. A translation that does not fit its bubble is set in smaller letters
(the model is not asked to shorten it).
The right pane (with "Indicators" on) says how far the page is ("This page: 3 of 7 lines"). Only when no bubble is lettered 1 second after you look at the page
does it also say "Loading the model...", "Reading the page..." or "Translating...", and that goes when the first bubble is lettered. A page that could not be translated
gets "This page could not be translated." there while that page is on show (Translate tries again), and a page with nothing to read gets "Nothing to read on this page." for 4 seconds.

### The side panes

TASlation's controls and indicators lie in two panes on the viewer's ground beside the page, at the left and right edges of the capture area, or nearer the page where that edge is far from it: a pane is never more than 300 pixels (at 100 % scaling) from the widest page shown in that window, on an ultrawide monitor too.
Where you set the capture area yourself ("Set area...") and it leaves room beyond its left or right edge, the pane on that side stands outside the area, never inside it.
A pane never lies over the page on show: one that would hides until there is room for it beside that page.
The panes stand still while you read: once a two-page spread has been shown, they stay where the spread put them on single pages too, however far a single page is from them. Only a page wider than any shown before in a window of that size (the first spread after a cover) moves them, once, and only as far as it must; a window of another size starts afresh.
They take their colours from that ground (light on a dark ground, dark on a light one) and their size from the scaling of the viewer's monitor, and they move with the viewer's window.

* **The left pane** holds the controls: "Translate" ("Stop" while a page is being translated), with the circular arrow at the right end of its row that translates the page on show again;
  "Auto"; the target language (a click lists every language at the right side of the pane, and a click on one takes it at once; a click elsewhere, or Esc, closes the list with no change); "Lettering"; "Indicators"; "Reader mode" (checked: the mouse is the viewer's; unchecked: editing);
  "Add area" (or Insert while the viewer is in front; see "Editing: correcting the page"); "Settings..."; "Menu"; "Quit". A click on a control never takes the keyboard from the viewer, and in Reader mode a click between the rows goes to the viewer.
* **The right pane** (while "Indicators" is on) shows, at its top, the bubble last under the pointer (see "The bubble under the pointer"); under it what changes: the lines of the setup
  (what is missing and how to fix it), the status line and how many pages turned past are still to do. Its foot keeps its rows in their places whatever the rest says:
  how far the page on show is, the mode ("Editing: turn pages with the keys" or "Reader mode"), where the translator runs (on the GPU or the processor; and the OCR, where it runs elsewhere),
  the viewer followed ("Viewer: <title>", a long title shortened in the middle), and, where there is room, the target language with the book's name. What does not fit above the foot is left out,
  the oldest lines first and the warnings last. In Reader mode, clicks on it go to the viewer, except on the bubble's three buttons. With "Indicators" off ("Indicators at the right of the viewer" in "Settings...", `see_through_indicators`),
  the right pane is not shown, and the lines of the setup come in a small dialog of their own while there is something to say.
* **"Menu"** opens the rest: "Viewer...", "Set area...", "Series and Volume...", "Saved translations...", "Names rendered in more than one way...", "Release the model now",
  "Copy a report" (see "Reporting a problem"), "Language" and "Help" ("How to use...", "Legal notice...", "Check for updates...", "About TASlation"). While editing, the editing comes first (see "Editing: correcting the page").
  While the setup has something TASlation can fix for you ("Start translator again", "Download model", "Show viewer"), those buttons come first in the Menu.

A pane needs room beside the page: one that would come near the page, or that the viewer's ground is too short for, hides rather than cover the page
(beside a two-page spread in a 1920 x 1080 window there is room; in a narrow window, or beside a wide page, there may be none). The panes also hide while the viewer is minimised or hidden,
and where another window lies over them.
Once the viewer is in sight again and there is room beside the page, the panes come back within about half a second, with no page turned (a viewer brought in front with its bars over the page too). While the left pane has no room, a click on TASlation's button on the taskbar opens the Menu at the pointer,
with the left pane's controls ("Translate", "Auto", "Translate into" (the list of the target languages), "Lettering", "Add area"), "Settings..." and "Quit" added. The taskbar button is the way to the program at any time;
closing it there (from the button's menu, or with Alt+F4) quits TASlation as "Quit" does.

TASlation's dialogs open over the viewer, on the viewer's monitor. A dialog you asked for takes the keys while it is open; once it closes, the keys go back to the viewer at once.
A dialog that comes by itself while you read (a warning, a question after a change of the series sheet, the name of a book you opened, the box about the GPU's memory) stays in sight over the viewer but leaves the keys with it: the keys keep turning the pages, and a click on the dialog gives it the keys to answer.

### The bubble under the pointer: the original, and copying the Japanese

Rest the pointer on a bubble, and after a moment (`hover_delay_ms`, 450 milliseconds by default; "Delay under the pointer" in "Settings...", 0 to 3000, 0 at once)
its lettering gives way to the original lettering in its place. The lettering comes back once the pointer leaves the bubble.
The pointer is only read: the viewer keeps the keyboard, and in Reader mode a click there goes to the viewer as ever (while editing, the bubble's box gets a stronger outline and its lettering gives way to the original in the same way; a click selects it, a double click opens the region editor).

With "Indicators" on, the right pane shows that bubble at its top: "Copy the Japanese", "Copy the translation" and "Ask again", then its Japanese and its translation
(up to five lines each). It stays after the pointer has left the bubble, so that the pointer can go to the pane, until another bubble is under the pointer or the viewer shows another page.
"Ask again" asks the translator for that bubble's line alone, anew, and letters the answer (as the model's answer, not as your correction).
The translation of a target language written from right to left or shaped (Arabic, Hebrew, Hindi, Bengali) is not shown in the pane; "Copy the translation" copies it all the same.

For a page read in this session the Japanese is in memory. A page shown from the cache has none (the cache keeps no Japanese), so once its bubble has been in the pane for a moment
(0.3 seconds), the bubble's part of the capture in memory is read again. The Japanese read is kept in memory with the page only, never written to disk or to a log.
TASlation writes the clipboard only when you press a Copy button. A line of the book you copied stays on the clipboard until you copy something else, and other programs can read it there.

### Pages you turn past

While you read, TASlation goes on reading and translating the pages you have turned past.
This work runs at a lower priority than the programs you use, so that turning a page, and the page you are on, come first.
The right pane says how many pages and lines are still to go, and how many pages were turned too fast to be taken; turn back to such a page in the viewer and it is read like any other.
Back on a page done behind you, its lettering shows as soon as the viewer shows it.
TASlation never shows a page from its memory as a page to read, and sends nothing to the viewer.

### A single screen and the viewer's full screen

You do not need a second monitor: TASlation lies over the viewer itself.
The viewer can be a window of any size, maximised, or on its own full screen (switch it there yourself, inside the viewer; TASlation never does): the lettering and the panes follow it.
TASlation never moves or resizes the viewer's window. The panes need some of the viewer's ground beside the page ("The side panes").

Keep some of the viewer in sight while you read. Some viewers stop drawing while other windows cover them wholly, and a browser stops while an opaque window covers it completely;
the page cannot be read then (see "How the viewer is read").

### More than one monitor, and the viewer's window resized

With more than one monitor it is the same: put the viewer on any of them, move it from one to another or across two, and the lettering and the panes follow it
(the panes hide while the viewer's window moves or changes its size, and come back a moment after it stops).
TASlation's dialogs open on the monitor that holds most of the viewer; the region editor and a number plate's entry open beside their bubble, on the monitor where the bubble is. A pane that would run off the screen, or that a window lies over, hides.
TASlation's taskbar button is wherever Windows shows it (with one taskbar, on the main monitor's).

While you drag an edge or a corner of the viewer's window, the lettering and the panes hide and nothing is taken from the viewer. Once you let go, they come back at the new size: the panes a moment later, the lettering at once where the page was shown at that size before, else within a second or two.
Snapping the window to half the screen, maximising it and restoring it work the same way.
An open region editor stays where it is and goes on with its bubble at the new size; should it now lie over the bubble, it moves beside it.
When the window becomes too narrow for the panes beside the page, they hide and the Menu comes from a click on TASlation's taskbar button; make it wider and they come back.

### Starting a book: the setup and the book's name

Each page is translated when you open it (what "Auto" and "Translate" do), with only the few pages just before it as context, and the pages you turn past go on being read and translated in the background ("Pages you turn past" above).

When something translating needs is missing (Ollama not running, the model or the OCR models not installed),
the right pane says what is missing and how to fix it, and checks again every 10 seconds until it is fixed (with "Indicators" off, a small dialog says it).

**The buttons of the setup's lines.** A line gets a button when it is something TASlation can fix for you; the buttons are the Menu's first entries (and the small dialog's).

| The line says | Button | Pressing it |
|---|---|---|
| The translation program (Ollama) is not running | Start translator again | Starts Ollama there and then, and checks the setup again |
| The translation model the target language needs is not installed | Download model | Asks whether to download it, showing its size (it asks even if you answered "Not now" before) |
| The viewer's window is minimised | Show viewer | Restores the viewer to its size (no key is pressed, and the focus does not move) |
| The viewer stays black | Show viewer | Brings the viewer's window in front of the other windows. Click the book and reload it |

If, at start, translation turns out to run on the processor (CPU) (judged by whether Ollama's log names a graphics card),
the right pane shows once roughly how many seconds a page takes to translate. Its "Close" in the Menu removes it for the rest of that session.

When the viewer window's title gives the book no name, a small dialog asks for the book's name on its first page.
The cache and the series sheet are saved under this name. Some viewers read in a browser have a tab title that is only the viewer's name, whatever book is open,
and with such a title it always asks (a viewer's or a browser's name is never used as the book's name).
Which part of a title is the viewer's name is learned on this computer: when you choose a second book in the same viewer, or type the book's name without the viewer's part in "Menu > Series and Volume...". From then on that part is left out of the book's name. For the first book the whole title may show in the "Series" field; correct the name there. A browser-based viewer whose tab shows only its own name asks for the book's name first, and your answer teaches it that the title names no book.
What is learned (the titles and program file names of the windows you chose as the viewer, and which parts of titles are a viewer's or a book's) is kept only in `~/.taslation/viewers.json` on this computer. It never goes into a cache export or a log, and it is never sent anywhere. Deleting the file only means choosing the viewer once more.
A book you have named once is recognised from its translated pages, whatever capture area you read it with, and its name is filled in. If several books look alike, the candidates are offered in the box's list,
and if it cannot tell, the name last given with the same viewer is filled in ("Last time with this viewer: ...").
Even after you resize the viewer's window, the book is recognised from its pages the next time you open it (if the two pages of a spread are both close to different pages of the same book, it is taken to be that book). Old caches are matched the way pages were cut out at the time, so they still work as they are.
Closing the dialog without a name reads nothing, and it asks again on the next page, since nothing can be kept without a name.

The pages you translate are also checked for the same character's name written more than one way in the translations ("竜司" split into "Ryuji" and "Ryūji", for example).
"Menu > Names rendered in more than one way..." lists such names.
Each name is listed with its spellings and how many lines use each; choose the spelling to keep, or type one in "Other:", and press "Apply": the lines with the other spellings are changed to it.
If "Keep it in the series sheet" is ticked (the default), it also goes into the character's rendering in the series sheet, and later translations use that spelling.
Nothing is changed until you press "Apply". Only the name itself is changed, and only in the lines whose Japanese has that name; the rest of the line, the review flags, the notes to the reader and the positions stay as they are.
"Take back" restores both the lines and the series sheet (while editing, "Undo" in the Menu can also take back the lines alone; pressing "Take back" after that restores the series sheet too).
The names are found by fixed rules; no model is used. Only names that carry an honorific such as "さん", "くん" or "様" in the Japanese (2 or more katakana, or 2 to 4 kanji) are considered,
and a name is listed only when the translations write it in two or more ways, each in separate lines, that look like spellings of the same name (missing a case is preferred to making a wrong suggestion).
It lists nothing for translations in languages without capital letters (Chinese, Korean, Thai and so on).
The Japanese lines are only kept in memory while TASlation is open, and are written nowhere. So it covers only the lines of the pages translated in this session (at most some 3,000 lines, the oldest going first; a page shown from the cache has no Japanese to look at).

When the model answers nothing for a while, TASlation asks it again, and the right pane says so.
While TASlation is open, the screen does not switch off and the computer does not sleep (because the viewer stops redrawing when the screen switches off).
It cannot prevent closing the lid, putting the computer to sleep by hand, or locking it. Quitting TASlation puts this back as it was.

The translations an earlier version saved by reading a whole book first stay in the cache, and show as any page translated before.

### How the viewer is read

The viewer's screen is taken with Windows.Graphics.Capture. A window can be read even behind other windows; the picture taken is only the latest one,
in memory, and is not saved to disk. Where this is not available, it switches to PrintWindow automatically (`taslation doctor`
shows which one is in use). Drawing stops when the display switches off, so the display is kept on while TASlation is open.

TASlation reads the viewer's window at the size it has; it never moves or resizes it, and it presses no key. The larger the viewer's window, the better it is read.
Versions up to 1.0.1 enlarged a viewer's window that was smaller than the monitor's work area. A window such a version left enlarged (it ended without closing)
is put back at the next start, if it still has the size it was given (kept in `ui.json` in the state folder).
When a page in the cache is shown, the status line says "Looking at the page..." rather than "Translating...".

Some viewers stop drawing while they are hidden. When you choose the viewer and it is completely hidden by other windows,
TASlation asks it to redraw without pressing any key (the same request Windows makes when another window is moved away), checks whether it draws while still hidden,
and records that per viewer in `profiles.json`; when nothing comes, it brings the viewer to the front for a moment to look (with no key press and no change of focus)
and puts it back in its place in the order at once. The same look is taken once when the viewer's picture has stayed blank for 3 seconds (`page_turn_wait_ms`) while other windows lie over it.
A viewer that draws nothing while it is covered is said so in the right pane: keep some of it in sight. A viewer that is even partly visible goes on drawing.
Browsers follow a published rule: they stop drawing only when they are completely covered by an opaque window. So browsers are not checked.

### When the viewer stays black

A viewer read in a browser can get stuck on its loading screen, or stay black. When the capture area stays black, TASlation does the following. It never presses a key.

1. **Wait**: loading may just be slow, so it waits for `black_wait_s` (30 seconds by default). After about 8 seconds it says the viewer is "still loading".
   Meanwhile it only checks in memory, about once a second, whether a new frame has arrived (when capturing with PrintWindow, it captures once every 2 seconds).
2. **Tell you**: if it is still black, it tells you, once, in the right pane, to reload the book in its own window: click the book, then press that window's reload key
   (F5 in a browser). "Show viewer" in the Menu brings the viewer's window in front of the other windows.

TASlation goes on waiting, and when a page appears, it continues from the page shown at that moment. It never translates or caches a black screen. A page that really is all black cannot be told from a stalled loading screen, so it is treated the same way.

### The book's name: series and volume

A book's name is given in two fields, "Series" and "Volume" (in "Menu > Series and Volume...", in the dialog at the start of a book, and in the colophon's offer).
The translations, the information attached to pages and the series sheet are saved under the one name these two make. As they are joined in only one way,
"3巻", "３" and "第三巻" no longer make three books that differ only in how the volume was written.

* Series: the name the volumes share. An edition such as "完全版" belongs here too. The series sheet is saved under this name.
* Volume: a number (half-width digits, no leading zeros; a decimal such as 10.5 is allowed). Full-width digits, circled numbers such as ① or ❸ and kanji numerals from 一 to 九百九十九 can be typed as well,
  and "第3巻", "3巻", "Vol. 3", "#3" and "(3)" all become 3 (when you leave the field, it shows the way the volume is saved).
  The only volumes that are not numbers are 上, 中, 下, 前編 and 後編 (上巻, 前篇 and the like count as the same). Anything else is refused, with the reason shown.
  For a book of one volume, leave it empty.
* The name is "series volume" (one half-width space), or the series alone when there is no volume. Full-width letters and digits become half-width, and runs of spaces become one.

A name that arrives as one string, such as a viewer window's title or the name of an older cache, is split into the two fields by finding the volume at its end (written as above,
or before an imprint such as "(見本コミックス)"). A title that ends in a digit with no separator ("Some Title13" and the like), a four-digit number with no volume mark
(a year, for example) and brackets with no volume before them stay part of the title. If the split is wrong, correct the fields. A split you corrected
(for example "Gate 51" as the series with no volume) is remembered in `~/.taslation/ui.json` on this computer, and that name is treated that way from then on.

Translations saved before this version under a spelling such as "Some Title 3巻" are found as they are when the fields say "Some Title" and "3", and are read and written under their old name
(the same series and the same volume make the same book). Nothing is renamed by itself. For such a book, once each time TASlation starts,
it offers to rename the book to the one spelling. "Rename" moves the translations, the information attached to pages and the series sheet, as the colophon's rename does (next section;
if the series sheets disagree, the table to answer comes first). With "Not now" the old name stays, and everything works as before.
Whether the book was in Reader mode carries over after the rename. A series sheet that an earlier version kept under a whole name with a kanji volume
("第一巻" and the like) as its series is found and used too, and moves along when the book is renamed.

On the command line, `--series` and `--volume` name the book the same way. A name given with `--book` is split as one string by the same rules
and put in the one spelling (if translations were saved under an older spelling, they are read and written under that name).

### The colophon and renaming the book

Near the end of a volume, TASlation reads the colophon (title, volume, author, publisher, ISBN), saves it in the cache's header,
and offers the colophon's title as the book's name, once per book. The offer shows the name in its "Series" and "Volume" fields, so you can correct it. Choose "Use" or "Keep".

When there are files under the book's current name (the name you typed first, or an old cache saved under the viewer's name), "Use" renames the book.
The translations in every language and the information attached to pages, and the series sheet too if the new name belongs to another series, are moved to the new name,
and the status line shows what was moved and how much.

If that series already has a series sheet (when you renamed an earlier volume to its full title, for example), this book's series sheet is merged into it.
What is added is taken in as it is. Where the two disagree (a term's rendering, a character's first-person pronoun, a policy in the style guide and so on),
the series' value and this book's value are shown side by side, one item at a time, before anything is moved,
and you choose "Keep the series'" or "Take this book's" (you can also choose for all at once). "Rename" renames the book following those answers;
with "Cancel" the name stays as it is, and the colophon's title is offered again next time. This table appears only while editing. In Reader mode it does not ask, and merges keeping the series' value in every row.
If there is nothing to answer, it merges at once and shows how many entries were added, how many were taken from this book, and how many were kept as the series had them.

The series' defaults (see "Book settings...") follow too when the new name belongs to another series. If the new series has none yet, the old series' defaults are moved to it,
or copied when other volumes are still kept under the old series, so that those keep theirs. If the new series already has defaults of its own, they stay as they are, and so do the old series'.
A book that was following its series keeps the values that were in force for it: if the new series' defaults (or none, for a name without a volume) would give it others,
the values it took from the old series become its own, and it no longer follows a series.

Nothing else is overwritten. If translations or page information under the new name already exist, nothing is moved,
and the files in the way are shown.

### TASlation's language

At the first start, it asks which country you are in and TASlation's language (see "The notice at start"), and remembers them in `~/.taslation/notice.json` and
`~/.taslation/ui.json`. The language can be changed at any time in "Menu > Language",
and the country with "Menu > Help > Legal notice...". They can also be set with `--ui-language ja` or with
`ui_language` in the settings file.

There are 17 built-in languages: English, 日本語, Español, Português (Brasil), Français, Deutsch,
Italiano, Nederlands, Polski, Русский, Türkçe, Bahasa Indonesia, Tiếng Việt, 简体中文,
繁體中文, 한국어, ไทย. This is the language of the panes, the menus, the dialogs and the messages, not of the translations.
Translations can be into any of the 20 languages of the left pane's language row.
"Menu > Help > About TASlation" shows the version, the licence,
the folder where the cache, series sheets and settings are kept, and where the README and docs/THIRD_PARTY.md are.

### Editing: correcting the page

TASlation starts editing. "Reader mode" in the left pane (checked: you only read) switches editing off, and unchecked again, on. It stays as you left it for each book (a book you have not chosen for
starts editing, or in Reader mode with "Start in Reader mode" in "Settings...", `--role reader` or `role = "reader"` in the settings file); until the book's choice is known,
a moment after its name is, the lettering takes no clicks and shows no boxes. While editing, every region of the page on show
is outlined over the viewer in its colour, with its number in the reading order on a small plate of that colour (green: translated, orange: not translated, blue: a region you marked yourself,
red: translated but flagged for review). A translated region whose lettering is not on the screen at the moment (the picture on show is not quite the page that was read,
for example) is outlined with a dashed line in its colour. The right pane's foot says "Editing: turn pages with the keys" or "Reader mode".

* **The viewer takes the keys only**: while editing, the mouse over the viewer's window is TASlation's, and the keys stay the viewer's (Insert excepted, "Adding a text area", and Delete while a region is selected, "The mouse on the boxes", below).
  Turn the pages with the keys; to use the mouse in the viewer (its buttons, its page slider, the wheel), check "Reader mode". The wheel reaches nothing while editing,
  and the viewer's bars do not come up under the pointer (bars already up go when the viewer hides them by itself). While a dialog of TASlation's (the region editor among them) is open, the keys are the dialog's.
* **Adding a text area** works while editing and in Reader mode: press "Add area" in the left pane (it shows pressed), or Insert while the viewer is in front,
  and drag a rectangle around text that was not detected. It is read, translated and added to the page (later readings use it too), and the page goes back to
  reading as before. Until the rectangle is drawn, the whole page takes the mouse; a click without a drag, a right click, Insert again or "Add area" again gives it up.
  A text area can be added once the page on show is translated, with "Lettering" on and the book named (the status line says what is missing).
  While editing, a rectangle dragged on the page's empty ground adds a text area in the same way, and "Add a text area" in the Menu's "Page" does the same as "Add area".
  TASlation takes Insert only while the viewer is the window in front: not while another program or a dialog of TASlation's is, nor while the viewer
  is minimised. Only Insert alone is taken (Shift+Insert and Ctrl+Insert stay the viewer's). "Insert adds a text area" in "Settings..." (`add_area_key`) turns it off,
  and Insert then stays the viewer's. Where another program holds Insert already, the key does nothing and "Add area" still works (the log says so once).
  The only other key TASlation takes is Delete, in the same way and only while a region is selected ("The mouse on the boxes", below).

* **The mouse on the boxes**: a click on a box selects it: it gets a stronger outline with its corner handles. A double click opens the region editor beside it.
  Like shapes in office software, a region is moved by dragging and resized with its corner handles (a corner of any box resizes it),
  and it is read again only when the new frame covers a larger area (a right click during a drag gives the drag up). Shift+click adds a box to the selected regions,
  or takes it out; dragging one of the selected regions moves them all together (the whole group stops when one of them reaches the edge of the page).
  Delete drops the selected regions ("Undo" brings them back). TASlation takes Delete only while a region is selected and the viewer is the window in front,
  and lets it go as soon as nothing is selected: at all other times Delete is the viewer's (with the region editor open, the editor's).
  The box under the pointer gets a stronger outline and the right pane shows its words; after the same delay as in Reader mode its lettering gives way to the original
  (not while you drag it, nor for the region open in the editor). A click on the empty ground clears the selection.
* **The number plates**: a click on a box's number opens a small field over it to type the region's place in the reading order (1 to the number of regions on show).
  Enter takes it: the regions are numbered anew, and the lines whose earlier lines changed (from the first place that changed on) are translated again, your own corrections kept;
  "Undo" takes the new order and those translations back in one step. Esc, or a click anywhere else, gives it up. A drag from the number moves the box.
  On a spread, a region stays on its own page: a place that belongs to the facing page puts it first or last on its own page, whichever is nearer
  (the order is kept page by page, so the next reading keeps it).
  A region added later to a page whose order you set by hand takes its place by its position, the others keeping the order you gave.
  "Reading order" (click the regions in order) and "Place in reading order..." stay in the Menu and work the same way: the lines whose earlier lines changed are translated again,
  and "Undo" takes it all back in one step.
* **The Menu** has the editing while editing: "Undo" and "Redo"; "Page" ("Reading order", "Add a text area", "Skip page"; then, for the chosen regions, "Set kind...",
  "Set text size...", "Place in reading order...", "Copy format", "Paste format", "Paste format on every region of this kind...", "Copy region", "Paste region",
  "Drop the chosen regions" and "Ignore this area on all pages of this book"; and "Use these areas for the series"); and "Review...", "My corrections...", "Lines to review...",
  "Find and replace...", "Series sheet..." and "Book settings...", each a dialog of its own. A click on a box chooses that region.

* **Copying and pasting formatting**: as with a word processor's format painter, "Copy format" remembers the formatting of the chosen region (font, size, bold and italic,
  alignment, line and letter spacing, slant, text direction, text colour and outline), and "Paste format" gives it to the regions chosen then
  ("Undo" takes it back in one step). The kind (speech, thought, shout and so on) is premise information the model is told when it translates, so it is not copied with the formatting.
  "Paste format on every region of this kind..." applies the copied formatting to every region of this book of the same kind as the chosen region
  (it shows how many and asks first; the kinds are held by the book's premises, so it also applies to regions on pages not shown yet;
  when the kind is "(not set)", the regions of translated pages are the ones covered). Whatever page is shown, one "Undo" takes back the whole of it.
  "Copy region" remembers the chosen region itself (frame and formatting), and "Paste region" on another page with the same layout
  adds a region at the same place, then reads and translates it (it does not add one where there already is a region, or when the page's size differs).

* **Regions**: every text region has a box with its number (a region of your own is added with "Add area": "Adding a text area", above).
  On the drawing, only the lettering inside a region is erased and the drawing under it filled in (by the inpainting model where it runs, otherwise from the drawing around the strokes);
  in a bubble or on a flat box, the rectangle is wiped on its paper, and the outline and the drawing beyond it stay.
  A slant is set in the region editor ("Slant"); a slanted region keeps its slant when it is moved or resized.
  "Drop the chosen regions" removes them, and a removed region is remembered as "not text" on that page, so a false detection never comes back.
* **Areas ignored on every page**: for things that appear at the same place on every page and that you do not want translated, such as watermarks, page numbers or a band printed on every page, choose the region and
  then "Ignore this area on all pages of this book": that place (the region's frame, slightly widened) is then ignored on every page of the book.
  When you remove a region at the same place as one you removed on another page, the same is asked after the removal is saved (a place you answered "Only this page" for
  is not asked about again until TASlation closes; removing a region you added yourself does not ask). A detection that falls almost entirely (70% or more of its area) inside such an area
  is treated as not found, and left as drawn. Regions you added yourself stay, even inside the area.
  An area set on a page of a spread applies to the pages on that side (right or left) and to pages shown one at a time; an area set on a page shown one at a time applies to every
  page; neither applies to pages of a very different shape (a spread made into a single image and the like). Adding one can be taken back with one "Undo",
  whatever page is shown. The translations inside the area stay in the cache, so taking it back brings them back as they were. All that is saved is the area's four numbers,
  the side of the spread and the page's aspect ratio.
* **Editing a region**: a double click on its box opens the region editor beside it (a click selects the box). The formatting fields are folded into the "Formatting" button when the region has no formatting of its own. You can change the **speaker** (chosen from the series sheet's names), the **kind** (Speech,
  Thought, Shout, Narration, Sound effect, Handwritten, Erase only), whether the **sentence continues in the next bubble**, the **hint for the model** (a pun, who is addressed),
  and the translation. Enter starts a new line (the lettering keeps that line break too), and Ctrl+Enter saves.
  A **sound effect** is lettered at the slant the drawing gives it, as large as it fits, in the series sheet's lettering for sound effects.
  TASlation finds the sound words lettered on the drawing itself (from its own list of Japanese sound words): "(not set)" keeps what it found, and another kind turns it off.
  Into English, a sound word PLaMo gets wrong is given TASlation's own rendering of it ("Ba-dump" for ドキッ), unless the series sheet has one.
  PLaMo 3 Translate (the model of every target language but Brazilian Portuguese and Turkish, see "Choosing the model") follows a hint only sometimes (about half the time in a test), and the editor says so under it:
  it works best for how a name or a term is read and for who or how many are meant; names and terms that must always come out the same belong in the series sheet. Qwen3.5 4B and a model of your own are given the hint with the bubble.
  A hint can change the wording of its own line even where it does not need to, but it never reaches another line: the request that translates a bubble together with the next one as one sentence carries no hint, and "Ask again" asks the bubble alone, with its hint.
  With the kind set to "Erase only", the region's original lettering is only erased, and nothing is lettered there (as soon as you choose it, the lettering over the viewer shows it erased).
  It is not sent for translation, and it is counted neither as flagged for review nor as untranslated. The earlier translation stays in the cache, so setting the kind back letters it again.
  The change can be taken back with "Undo".
  Where the original letters part of the bubble larger than the rest and that part was found in the translation ("Settings...", `size_emphasis`), those words show larger in the translation's box.
  They follow your typing; an edit that touches them letters the bubble at one size again. "Set larger" and "One size" on the formatting bar set and clear them.
  "Ask again" looks for the part in the new answer too.
  At the top of the editor, the region as it originally looks is shown, cut out of the captured screen (an image in memory only, saved nowhere); "Show original", held down,
  shows the viewer's original in place of the region's lettering.
  A page shown from the cache has no Japanese (the cache keeps only translations), so "Read the Japanese" reads it again there and then;
  "Read as:" then appears, and "Ask again" can be used too (if you press "Ask again" without having read it, it reads first).
  Where the Japanese was misread, correct it in the "Read as:" field: "Ask again" translates your reading, and so does everything that reads that bubble again in this session
  (translating again, reading it again from the cache, moving it). Where nothing was read, the field appears after a reading, to type the Japanese in.
  Your reading stays in memory only and is never saved; "Save" keeps only the translation, and "Undo" takes back the translation, not the reading.
  "Previous (Alt+↑)" and "Next (Alt+↓)" move to editing the region before or after in reading order. If you changed something, it is saved before moving, as "Save" does
  ("Undo" takes it back as one change); if you changed nothing, nothing is written.
  If you try to close it with Esc or the editor's close button with changes made, it asks whether to discard them ("Keep editing" is the default).
  The "Cancel" button closes without asking.
* **Formatting bar**: the formatting bar above the translation works like a word processor's text box.
  It has "Bold" and "Italic" ("Auto" goes back to what the series sheet sets for the kind), **Font** (the fonts installed on this computer;
  a computer without that font uses the automatically chosen font; at the top of the list come the fonts you starred with the ☆ beside them, then the fonts used recently
  (the last 10); pressing ★ again removes the star; you can also move to it with Tab and press it with Space; only the font's family name is remembered,
  saved in this computer's ui.json), **Size** ("Auto" is the largest size that fits; a fixed size is not shrunk,
  and text that does not fit is cut off at the bubble's edge, which is shown), "Condense to fit" (automatic under 14 points),
  "Set larger" (the words selected in the translation are lettered larger than the rest, as many times larger as the original's larger part where it was measured, else 1.5 times; the box shows them larger) and "One size" (the whole translation at one size),
  align left, centre and right, and align top, middle and bottom, **Line spacing**, **Letter spacing**, **Slant** (the angle, anticlockwise; "Auto" keeps the original lettering's slant), **Text direction** (as in a Word text box: Auto (across; in a tall, narrow bubble where across would come out small, the line turned as Rotate all text 90° turns it, as "Fitting lettering into bubbles" in "Settings..." says), Horizontal, Rotate all text 90° (reads from the top down, the direction of an English book's spine), Rotate all text 270° (reads from the bottom up), and Stacked (vertical writing: the letters are stacked downward, and the columns run from right to left; the long-vowel mark "ー", dashes, "…" and brackets take their vertical forms, small kana and punctuation sit in their vertical positions, and Latin letters are stacked upright one at a time; horizontal-in-vertical (tate-chū-yoko) and ruby are not supported); combined with a slant, the text in the chosen direction is slanted together with its frame), **Text colour** and **Outline colour** (Auto, Black, White, Custom...; with Custom, you choose any colour in Windows' colour dialog, and clicking the colour swatch beside it lets you choose again; nothing is asked of the network), **Outline** (Auto, With outline, No outline), and "Reset formatting". "Auto" for the colours and the outline follows the colour and outline the series sheet set for that kind; if it set none, the text is black or white to suit the background, the outline is drawn only on art and screentone, and the outline colour is the opposite of the text's. Colours and outlines do not change the text's size or line breaks. "Copy format" (Ctrl+Shift+C) remembers the bar's formatting, and "Paste format" (Ctrl+Shift+V) puts it into the bar of another region's editor (confirmed with "Save").
  After a change, the lettering over the viewer follows a moment later. The formatting is saved with the book's page information.
* **Into the series sheet**: when your edit replaces a name or term that the series sheet renders differently, it asks whether to make yours the series sheet's rendering,
  and replaces it on the pages already translated as well (replacing the translations is one change that "Undo" takes back; the series sheet's rendering does not go back).
* "Reading order": when the order decided automatically is wrong, choose "Reading order" and click the boxes in reading order, then choose "Finish order" in the Menu
  ("Cancel the reading order" leaves the order as it was). Split sentences, and who answers whom, are decided by this order.
  To correct the place of a single region, choose that region and, with "Place in reading order...",
  enter which place it should have (with several chosen, they are put at that place in their present order; the order of the other regions
  does not change; on a spread each stays on its own page, as with the number plates; "Undo" takes it back).
  Either way, the lines whose earlier lines changed are translated again, as after a place typed on a number plate.
  "Skip page" marks a page with nothing to translate, such as an advertisement or the viewer's own panel, and the circular arrow (not using the cache) translates the page again with the current premises.
  The translations you corrected yourself (in the editor, or with Find and replace) stay as they are and are not sent to the model;
  tick "Replace the lines I corrected too" in its question to have them translated again as well.
* "My corrections..." lists the translations you corrected yourself in this book, page by page, from the saved translations alone.
  Selecting one says which page it is on; nothing is sent to the viewer, so you turn to that page yourself.
  The model's answer to "Ask again", saved as it came, is not your correction; a spelling made consistent by the series sheet or the name check leaves a line as it was.
* "Lines to review..." lists every line of this book worth a look, page by page, from the saved translations alone: the lines flagged for review as they were translated
  (the reasons are those of "Review...", as `taslation review` lists them) and those with a note to the reader. For the page on show it also lists what the checks of its lettering found
  (those are worked out as a page is lettered and are not saved, so other pages show only their flags). "Show:" narrows the list to one reason, and a click on the
  "Page" or "Why" heading sorts it. Selecting a line says which page it is on; nothing is sent to the viewer, so you turn to that page yourself and edit it there with "Review...".
  The list follows each translated page and each change.
* "Review..." lists the regions on that page worth a look (flagged for review, untranslated, or with a note to the reader).
  It also lists the regions whose automatic lettering could not be set well: letters touching the bubble's edge, the text
  off the bubble's centre (as when one translation for two joined bubbles is set in one of them), a word split with a
  hyphen, a short word alone on a line, a line much narrower than those round it, or letters hard to see on their ground.
  "Ask again" in the editor has the model translate that bubble again, with the lines before it as context (there is no feature that lists alternatives);
  in its answer too, names and terms spelled differently from the series sheet are made consistent mechanically.
  A translation reused from an earlier identical line says so in the editor ("Reusing short lines"); "Ask again" gives a fresh one.
  Translations that contain a word the dictionary does not know can be flagged as well, with the spellcheck setting (`spellcheck = true` in the settings file; off by default).
  Its word lists are an optional extra that TASlation does not install: the Python package `pyspellchecker` (MIT licence; word lists for English, Spanish, French, Portuguese, German, Italian, Russian and Dutch, kept on disk),
  and the check runs only where it has been added to TASlation's Python. The series sheet's names and renderings are exempt.
  When the setting is on but the word lists are not installed, the editor says so once, the first time you open it, with where to turn the setting off
  ("Open settings file" in "Settings..."). Nothing is fetched from the network.
* "Undo" takes back the changes to the page on show, newest first (edits of translations and notes; moving, resizing, adding and removing regions (a change made to several regions at once
  counts as one); saved formatting; setting kinds and text sizes;
  "Skip page"; setting the reading order; translating the page again),
  and "Redo" applies them again. Changes on other pages can be taken back when that page is shown again.
  Taking back a translation of the page again brings back the page's earlier translations. One that ended without translating anything (a stop, for example) is not something to take back.
* "Find and replace..." searches and replaces across all the translations of the current book in the current language
  (and, if you choose so under "Look in:", in the other volumes of its series too).
  Use it, for example, to correct a wrong character name throughout a volume at once. You can keep reading the book with its dialog open, and as you type, the matches
  are listed with their page numbers and the text around them (the match is between `«` and `»`; the page number is not the book's printed page number,
  but the order in which the page entered the cache). "Match case" and "Whole word" narrow the search. "Whole word" does not look for word boundaries next to
  scripts that put no spaces between words, such as Japanese, Chinese, Korean and Thai.
  Nothing is written until you press a replace button. "Replace selected" replaces only the matches selected in the list (Ctrl and Shift select several),
  and "Replace all" replaces every match (the list shows only the first 500, but the count and "Replace all" cover them all).
  The page on show is lettered again at once, and other pages show the new translations the next time they are shown.

  Only the translations change. Review flags, notes to the reader, draft marks, marks of unfinished pages and the bubbles' positions stay as they are.
  A part of a translation set larger moves with its words; where the replacement touches it, that bubble is lettered at one size.
  The lines were not looked at and corrected one by one, so, unlike an edit of a region, it does not clear review flags. A bubble whose translation would become empty is not replaced, and this is said.
  A replacement is one change as a whole: while it is the book's latest change, "Undo" takes it back on all pages at once, whatever page is shown,
  and "Redo" applies it again (in the Find and replace dialog, Ctrl+Z and Ctrl+Y do the same). If you edit another page after it, that edit must be taken back first.
  A bubble whose content changed because it was translated again is no longer part of what is taken back.

  The series sheet does not change on its own. Only when the words replaced with "Replace all" were a rendering in the series sheet does it ask, once, as for a region edit,
  whether to use the new rendering. When only some lines were replaced, it does not ask. Undoing does not take back a change to the series sheet.
  Nothing can be replaced while a page is being processed. Press it again once that is over.

  "Look in:" says where "Replace all" replaces: "This book" (what the dialog starts with every time it opens) or "All volumes of the series".
  With the second, the list still shows this book, and "Replace all" first counts the matches in the other volumes of the book's series kept in the same language
  (found as `taslation glossary apply` finds them: by the series name), shows the count volume by volume, and asks.
  "Replace in all volumes" replaces in this book as "Replace all" does ("Undo" takes it back) and in each other volume, where the change is saved at once
  and "Undo" does not reach it. Before a volume is changed, a copy of its file as it was is kept beside it (`<file>.before-replace.<date>.json`, protected as the cache is);
  to take the change back, replace the other way round in all volumes, or put that copy back in place of the file. The lines replaced there are marked as your corrections too.
  "Replace selected" always stays in this book.
* "Book settings..." saves the detection and OCR values that suit this book (thresholds, text-block detection, sound effects) and this book's lettering size
  ("Lettering size" and "Largest size"; "As in Settings" and an empty box mean the values in "Settings..."), together with the book's premises,
  without changing your own settings. "Apply to this book" re-sets the page on show from the cache (nothing is translated again).
  "Reading direction" says which page of a two-page spread and which bubble come first: "Right to left (Japanese books)", the default,
  or "Left to right"; "Clear all" leaves it as it is.
  "Clear all" shows how many settings will go and asks before clearing them (the default button is "Keep them"),
  and leaves the dialog open. Meanwhile "Undo" brings the cleared settings back. Below that, the areas ignored on every page of this book are listed
  with the pages they apply to (All pages, Right-hand pages, Left-hand pages) and their position (in % of the page's width and height), and "Remove area" (or the Delete key in the list)
  removes the selected area at once (text is looked for there again). "Undo" takes back the last thing done in this dialog (Clear all, or removing an area).

  The volumes of a series can share these values. "Save as the series' default" applies the values shown to this book and keeps them (the choices, the sizes, the other settings and the reading direction) as its series' defaults;
  "Use these areas for the series", beside the areas (and in "Page" in the Menu, greyed while the book has no series), keeps the areas listed as the series' areas. A volume opened for the first time (nothing of its own kept yet) starts from its series' defaults and follows them wherever it has no value of its own:
  such a value is marked "(the series' default)", "As the series' default" or "(series' default: ...)", a value set for the volume always wins, and "Clear all" goes back to the series' defaults (your own settings where the series has none).
  The areas are the series' list as a whole until you remove or add one in the volume; then the volume keeps its own list. The series is the Series field of a book that has a volume number (letter case and spaces aside);
  a book without a volume has no series defaults, and a book whose annotations were kept before goes by its own values as before. Areas are kept relative to the page and its shape, so they fit a volume captured at another size,
  and a volume whose pages have another shape is left alone. The series' defaults are kept in `~/.taslation/annotations/series/`, protected as the annotations are.
* "Series sheet..." keeps, for each series, terms (the term and its rendering or spelling), characters (gender, age, first-person pronoun, way of speaking, role, how they address other characters)
  and a style guide (the policy on honorifics, tone, house rules, the lettering font the series suggests, and per kind the typeface and the text colour, outline and outline colour). The colours and outline per kind become "Auto" for the regions of that kind, and a colour and outline set for a region in the editor take precedence over them. Everything except the typefaces
  is told to the model before it translates. Only facts go in, never the book's dialogue. The lettering font is given by its family name, such as Comic
  Neue (it can also be set with `taslation glossary font`; the lettering-font and per-kind typeface boxes can also be chosen from a list,
  where, as in the editor, the starred fonts and the recently used fonts come first, and the ☆ beside one stars it);
  if that font is installed on this computer, it is used wherever it has the glyphs; if not, this is said and the automatically chosen font is used.
  "Remove selected" for terms and characters shows how many and which will be removed, and asks first (the default button is "Keep them").
  "Undo" at the bottom takes back the last change made in this dialog (an addition, update, removal or saved style guide), one step.
  When you change the rendering or spelling of a term or character (also when you bring one back with "Undo"), it shows how many translated lines use the old rendering,
  and asks whether to give them the new one. "Apply to the {n} line(s)" replaces it, word by word, in that book's translations in that language in the cache (changing "Miyu"
  leaves "Miyuki" alone; the page on show is lettered again at once). The replacement is one change as a whole, and "Undo" in the Menu takes it back, as with Find and replace.
  If a page is being processed, it asks once that is over.
  When other volumes of the series kept in the same language use the old rendering too, the question lists them with their lines, and its box
  "All volumes of the series" (unticked at first) gives them the new one as well; when only other volumes use it, it asks about them alone.
  The other volumes are saved at once and "Undo" does not reach them; a copy of each file as it was is kept beside it (`<file>.before-replace.<date>.json`).
  To take it back, change the rendering back and apply it to all volumes, or put that copy back. These lines are not marked as your corrections, in this book or in the others.

The speaker, kind, continuation mark and note go with each bubble, and the series sheet is placed before the bubbles, when they are given to the model. They are saved in
`~/.taslation/annotations/<book>.json` and
`~/.taslation/glossary/<series>.json` (names that would give the same file name get `<name>-<hash>.json`),
and hold only positions, facts and policies. Neither the text nor the translations go in. Both are saved protected, as the translation cache is (see "The translation cache and backups").

The effect of the premises can be measured without a book with
`python tools/premises_eval.py` (it translates test lines with and without a series sheet and scores names, pronouns, honorifics,
split sentences and ways of speaking). With the default model, the series sheet raised the pass rate from 58% to 90%. Translating a real volume again
with a series sheet whose facts had been checked against the book brought character-name errors from 208 to 0, and in a blind evaluation with context,
the new translation was preferred for 51% of the changed bubbles and the old one for 36% (`docs/OFFLINE_VERIFICATION.md`).
Check the facts first. A series sheet written from the model's own guesses was no better than none.

### Page fingerprints

A page fingerprint is a 320-bit perceptual hash of the page's content area (a 16x16 gradient hash and an 8x8 brightness hash of the shrunken page),
not a hash of a file. The same page captured at another size or zoom gives nearly the same bits, and a difference of up to 36 bits counts as "the same page".
At another window size the content area itself can come out otherwise (a page whose edges are black art, read with a sliver of the viewer's background beside it; a line a pixel thick at the page's edge; a page shown alone in a window too narrow for its spread).
So a page the cache does not hold as it is read now is also looked for as it is read at other sizes, within the same 36 bits: a page translated at one window size is shown from the cache at another without asking the model again.
The page cannot be rebuilt from its fingerprint. Similar pages (blank pages, an advertisement that recurs) are told apart by their aspect ratio and their place in the order.

### Reading in a browser: give the book's tab its own window

A browser window is recognised by its title, but a browser window's title is that of its active tab.
If the book's tab shares a window with other tabs, TASlation can see the book only while that tab is in front.

The fix is needed only once. Drag the reader's tab out of the window (or right-click the tab and choose "Move tab to new window")
to give it a window of its own. Leave that window open behind your other work. It may be hidden, but do not minimise it.
A desktop viewer is an app of its own, so it does not need this. A window other than a browser, such as an image viewer, is treated as the book as long as the same window stays open, even if its title (a file name or page number)
changes with every page you turn, and a change of title does not make it wait. Only when the window is hidden or minimised
does the status line say so and wait for it to come back.

If the window shows another tab even so, nothing of that tab is captured, lettered, cached or learned.
The side panes stay, and the right pane says in one line "The viewer's window shows another tab." (with "Auto" on, the status line says so too).
Once the book's tab is in front again, the reading goes on by itself. A page of the book that was being translated is finished meanwhile.
A tab with another book of the same viewer (its title starts or ends with the viewer's name, or ends as a window chosen before did, with another book before that) is read as the book's tab, under the name its title gives.
When you drag the book's tab out into a window of its own, TASlation finds that window and reads on there, under the same book name.

In the dialog that chooses the viewer, a browser window is listed by the title of the tab in front.
Bring the book's tab to the front first, then press "List again" (the line under the list says so). A window chosen while another tab is in front is taken with that tab as the book's,
but only on trial: nothing of that tab is read until the picture it shows looks like a page of a book -
drawings in panels, with text in speech bubbles - and nothing of the window is remembered for the next start until text on such a page has been read in the tab chosen.
A viewer known on this computer is never on trial: one you set a capture area for ("Menu" > "Set area..."), or one a book was read in before (its tab's title was chosen before, or starts or ends with a viewer's name learned, or ends as a window chosen before did).
This is judged from the picture alone, before anything is read: only a blank tab or a page of text with no picture is taken for no page of a book at once.
Where one page cannot tell (no panels, no bubbles, a page in colour, a black page, a picture, a shop's grid of items), TASlation waits for the next page you turn to; "Translate" reads the page on show whatever it looks like, and when text is read and lettered there, the trial ends.
Until then, a tab you bring to the front that looks like a reader (it starts or ends with a viewer's name learned before, it was chosen before, or its title has a word such as "book") is taken as the book's tab in its place.
If the tab chosen shows no page of a book, the right pane says "No page with text found in this tab." and how to choose the window again in "Menu" > "Viewer..." - at once,
or after about 5 seconds where the page cannot tell or looks like a page still loading (a pale or blank page). The side panes stand in the viewer's window then, even with no page to stand beside.
With another tab in front meanwhile, the right pane says how to have that tab read.

When the reading reaches the end of the volume, some viewers show an end-of-book panel (ratings, the next volume). The arrow keys may not get you out of this panel,
so then close it with "x" and go back to the first page. Text that looks like part of the viewer itself or of a colophon page (horizontal lines of Latin letters and numbers:
prices, addresses, ratings, dates of publication, the record of where each chapter first ran) is taken as print, not dialogue, and left as it is, and so are the title and the author's name on a title page.
A chapter's label and the words of a contents page (第3話, 第十二章, 最終話, 番外編, 目次, あとがき and the like) are translated wherever they stand: set across, on a band, beside a page number,
and a contents list row by row. Japanese read surely beside digits or Latin letters (3年B組, a heading with a subtitle in Latin letters) is translated too; a subtitle on a line of its own in Latin letters
is left as it is. A paragraph set across (an explanation page, a foreword) is read and lettered as one, not in pieces.

### The translation cache and backups

The cache is in `~/.taslation/cache/<book>.json`,
one file per target language (the book's name comes from the viewer window's title and can be changed in "Menu > Series and Volume..."; books that give the same file name, such as "My:Book 1" and "My
Book 1", get `<book>-<hash>.json`). "Menu > Saved translations..."
lists and deletes caches (the list shows each book as its series and volume, with its pages, bubbles, the file's size, language and last change,
and under it how many files, pages and bytes there are in all). A click on a heading sorts the list by that column, a second click the other way round;
at first it goes by series, volume and language. Ctrl+click and Shift+click choose several rows, Ctrl+A all of them. "Delete" moves only the files of the chosen rows' books, each in its row's language, to the Windows Recycle Bin
(the translations in other languages stay), after one question that names the book, or how many and which. The confirmation's default button is "Keep them", and the files can be restored from the Recycle Bin. When a file cannot be moved to the Recycle Bin
(on a drive without one, for example), it is not deleted, and this is said. On the command line, `taslation cache delete` deletes all languages, as before.
"Rename..." gives the one book chosen a new name in its Series and Volume fields; the rename then goes as every rename of a book does (the review first where the series sheets
say otherwise), its translations in every language, page information and series sheet moving along, and the list follows once it is done. A file holds the translations, the normalised shapes and positions of the bubbles, the page fingerprints and the notes to the reader (and, for a bubble with a part set larger, that part's place in its translation),
what the colophon says of the book (title, volume, author, publisher, ISBN) and the translations of short lines kept for reuse, each under a keyed hash of the line's Japanese, never the Japanese itself ("Reusing short lines"); it holds no page image.
Everything TASlation keeps is listed in "Menu > Help > How to use..." under "Your data".
The model never writes notes about the story to keep (note files that an old version wrote in
`~/.taslation/series` are left as they are, unread; delete them if you do not need them).

The cache, page-information and series-sheet files (with the copies kept beside them, and an old version's note files) are saved protected with Windows' own data protection (DPAPI),
and only your Windows user on this computer can open them. There is no passphrase. Copied to another computer, or opened by another Windows user, they cannot be read.
But a program running as your Windows user can open them, as TASlation does. The file names still end in `.json`, but what is inside is no longer JSON,
so a text editor shows no translations. To see what they hold, use `taslation cache list`, `taslation review` and `taslation glossary show`.
Files saved by an earlier version are replaced one by one by their protected form when TASlation starts (the status line and the log give only the counts).
A file that another program holds and that could not be replaced is read as it is and tried again at the next start. `taslation cache protect` replaces them too,
and `taslation audit` shows whether any file is left unprotected. TASlation versions before this one cannot read the protected files (they keep them beside as unreadable).
What an earlier version saved unprotected, and files you delete, may still be recoverable from the disk.

A cache, page-information or series-sheet file that TASlation cannot read (a broken one, one written by a newer version, or one saved by another Windows user or on another computer) is not overwritten.
It is kept beside as `<name>.unreadable-<date>.json`, a line is printed on the console, and a new file takes its place.
When there are files that cannot be opened on this computer, TASlation says at its start how many and how to move the translations (only when the number changes).
Deleting the book or the series deletes such copies too.

A book's cache can be made into a file encrypted with a passphrase, as a backup for yourself or to move it to another computer of your own ("Saved translations...",
or `taslation cache export` and `taslation cache import`). The file contains the translations, with the book's page information
(the rectangles you added or skipped, speakers and notes, the book's settings and the order of its pages), the series sheet the book reads in that language
and its series' defaults (one copy for all the volumes of a series in the file), so keep it to yourself. Without the passphrase, no one, TASlation included, can open it, and a forgotten passphrase cannot be recovered.
One file can hold several books: in "Saved translations...", every row chosen; on the command line, a whole series (`--series NAME`: every cached volume of the series in the target language) or every book (`--all`).
It holds no page images and no line read from the pages, only what the saved files themselves hold.
Since the saved files cannot be read on another computer even when copied, this is the only way to move translations, page information, series sheets and series' defaults.
When an administrator resets your Windows password (changing it yourself is fine), when you move to a new Windows profile,
or when Windows is reinstalled, the protected files can no longer be opened. If the translations matter to you, keep an exported file.
Files exported by an earlier version (one book's translations) can still be imported. An earlier version cannot import a file exported by this one:
it says the file comes from a newer version and imports nothing. Imported files are saved protected as well.

* Export and import each start with a warning. An exported file is for you alone (even if the book is yours, giving it to someone else infringes the author's rights),
  and you import only files you made yourself, on your own computer. "Cancel" there stops before you choose a file.
* While you type the passphrase, what it still lacks is shown, and "Show" unmasks it. A full-width space is treated as an ordinary space.
  Without the extra package `cryptography`, export and import are greyed out.
* An import into a book that already has translations here merges them by default. The file's pages are added or take the place of yours,
  but a translation you corrected here stays where the file's line for that bubble is the model's (or where the file has none),
  unless you take the file as it is (`--take-file`; `--replace` replaces the whole cache). Before writing, the import says
  how many pages it adds and replaces, and how many of your corrections it keeps.
* Page information you already have here stays unless you take the file's, and so do series' defaults you already have here. A series sheet you already have is joined with the file's,
  as a rename joins two sheets: what the file adds is added, and where the two say different things, yours stays unless you take the file's.
* In "Saved translations...", an import of a file that holds several books, or that meets corrections, page information, series' defaults or sheet values of your own,
  first shows what the file holds and what the import would do, and nothing is written until you press "Import": you choose the books,
  "Keep my corrections" (the default) or "Take the file as it is", "Keep mine" or "Take the file's" for the page information and for the series' defaults, and for each place where the series sheets differ.
* `cache import FILE --list` lists the books a file holds without importing anything, and `--book NAME` (again for several) imports only those.
* Each import keeps every file it changes (cache, page information, series sheet, series' defaults) beside it as `<name>.before-import.<date>.json`,
  so you can go back by hand. A wrong passphrase, a broken file, a file too large (a book's cache over 5,000 pages,
  or over 500 bubbles on a page; over 1,000 books or 100,000 pages in one file), or parts made by a newer version of TASlation: in these cases it refuses without writing anything.
  An export too large to be read back from one file is refused as well: export fewer books at a time.
* `cache export` does not overwrite an existing file unless you add `--force`.

`cache export` and `cache import` only print what the file is for to standard error before asking for the passphrase,
and ask nothing more, so they can run unattended from a script. With `--confirm` they ask "Continue? [y/N]",
and anything but yes ends with exit status 1, reading and writing nothing. An import whose file meets corrections, page information, series' defaults or sheet values of your own
prints on standard error what it will do with them and, with `--confirm`, asks once more. The passphrase is asked for without being shown. The environment variable
`TASLATION_PASSPHRASE` is for scripts only, because PowerShell's PSReadLine writes a line such as
`$env:TASLATION_PASSPHRASE = "…"` to its history file (its filter for secrets reacts to
"password" but not to "passphrase"). The safe way is to type it at the command's prompt.
If you use the variable even so, do not write the value on the command line; have the shell ask for it:

```
$env:TASLATION_PASSPHRASE = Read-Host -MaskInput               # PowerShell 7
read -rs TASLATION_PASSPHRASE && export TASLATION_PASSPHRASE   # bash, zsh
```

### Reusing short lines

A short line already translated in the same book, or in another volume of the same series, gets that translation again
without the model being asked (the setting `reuse_lines`, on by default; "Reuse the translation of a short line seen
before" in "Settings..."). The same cry, reply or name called out comes back page after page: reusing its
translation saves a request and keeps the line the same each time. It applies to lines of at most 10 characters, once
differences that change no reading are evened out (full-width and half-width forms, spaces, "……" and "...", "〜" and
"ー", "!?" and "！？！", a final "。"). A line whose sentence goes on in the next bubble or comes from the one before, and a
line with a hint for the model, are always translated. The speaker and the kind you gave a line in the region editor are
part of it: the same words said by someone else, or marked as a thought, are another line. Only translations made by
the same model into the same language are reused, and never those of another series. The series is the one the
series sheet goes by: the Series field, so a volume still kept under a name typed before the two fields ("Some Title
3巻") shares its lines with "Some Title 4".

* A translation you corrected yourself wins: later identical lines get your text. "Ask again" in the editor
  asks the model; its answer, once saved, counts as your correction here (not in "My corrections"). When a translation
  was reused from an earlier identical line, the editor says so. "Undo" on a correction also takes back the line it kept.
* Translating the page again (the circular arrow) asks the model for every line but those you corrected (unless you
  ask for them to go too), and the new answers replace the model's earlier ones (never your corrections).
* What is kept is spelt as the series sheet spells, as the page shows it. Before it is reused, a kept translation is
  held to the series sheet as it is now: a name spelt another way is put right, as in a translation just made, and a
  translation that still misses a rendering the sheet asks for is not reused (the model is asked).
* On OpenMantra's five short works, the lines this rule reuses were 3.5 % of the lines and saved about 3.5 % of the
  translation time with all pages translated in one pass (4.0 % and 3.8 % page by page). Translated afresh, those lines came no
  measurably closer to the professional translations than the reused ones, and the other lines of their pages were
  translated as well as without reuse (`docs/OFFLINE_VERIFICATION.md`, "Line reuse"). A longer book has more repeats.
  What reuse risks: a first translation that misses comes back wherever the line does, until you correct it once (or
  translate the page again).

What is kept: in the book's cache file, for each such line, a keyed hash of the line (HMAC-SHA-256 with a random key of
the book's own, kept in the same file) and its translation; the Japanese is not written. It is protected like the rest
of the file, counted by `taslation cache list` ("line(s) kept for reuse"), deleted with the book's translations,
carried by the encrypted export and brought back by an import (an import into a cache that has its own lines adds only
the lines it lacks). Since the key is in the file, whoever can open the file (your Windows user, or anyone with an
export and its passphrase) can test whether a line they guess was in the book, and a short exclamation is easy to
guess. With the setting off nothing is reused or kept from then on; what was kept stays in the cache until the book's
translations are deleted. The "System" page of "Settings" shows how many lines this session reused.

### Translating into other languages

The target language is chosen in the language row of the left pane (or with `--language`, or the setting `target_language`).
The cache and the series sheet are saved per language, and the lettering switches to a font for that script. The model that translates is decided by the target language
(see "Choosing the model"). The quality depends on how good the model is in that language. Only translation into English has been measured (see "Choosing the model");
the models used now have not been measured in the other target languages.
Hindi and Bengali are shaped with HarfBuzz (the `uharfbuzz` package that install.cmd installs): conjuncts, vowel signs
and the reph are set as the font forms them. Where that package is missing, their letters are drawn one by one, and
the right pane says so (run install.cmd again). Everything else is set correctly too, including Arabic and
Hebrew, which are written from right to left; only Hebrew's vowel points, which translations seldom have, may sit on
the letter next to theirs.

### Command line

```
taslation                      start TASlation over the viewer (the same as `taslation gui`)
taslation gui --window "<title>"   start with the viewer chosen (Auto on; --no-auto starts with it off)
taslation windows              list the windows that can be captured
taslation doctor               check the models, fonts, Ollama, the network guard, and whether each stage runs on the GPU or the CPU
taslation notice [--country CODE] [--reset]   show the legal notice of the start for a country (ISO code); --reset shows it again at the next start
taslation cache export <book> --out FILE [--force] [--confirm]   export the book's translations, page information, series sheet and series' defaults to a file encrypted with your own passphrase (a backup for yourself, or for another computer of yours); --force overwrites an existing FILE
taslation cache export --series NAME | --all --out FILE   every cached volume of a series in the target language, or every book, in one file
taslation cache import FILE [--list] [--book NAME] [--take-file] [--replace] [--confirm]   read that file back (merged with what is there, your corrections, page information, series' defaults and sheet values kept unless --take-file; --replace replaces the cache); --list only lists the books it holds
taslation read --window "<title>" --book "My Book 1"   capture the window once as it is, translate and show the result
    (it takes the book's name from the viewer window's title; a title with no book's name in it, such as
     "<viewer> - <browser>" with only the viewer's name, is refused, so give --book NAME)
taslation read --window "<title>" --series "My Book" --volume 1   the book's name as its series and volume (--volume 第1巻, ① and 一 are 1 too; a book of one volume: --series alone)
    (read, gui, review and translate take them; --volume goes with --series, never with --book)
taslation translate page.png --show    translate an image file of your own (writes nothing)
taslation translate page.png --translator echo --no-translate   detection and OCR only
taslation review --book <book> | --series S --volume V [--notes] [--corrections]   cached translations flagged for review (could only be set small, a rendering missing, much longer or shorter than the Japanese, the OCR unsure, a word not in the dictionary); --notes also lists the notes to the reader; --corrections lists the translations you corrected yourself instead
taslation cache list | delete <book> | path
taslation cache protect        protect the saved files that are not protected yet, and show the counts (also done at every start)
taslation glossary list | show <series> | set <series> <term> <rendering> [--note ..] | delete <series> [term]
taslation glossary apply <series> --rename OLD=NEW [..] [--dry-run]   replace OLD with NEW in what is already translated
taslation glossary font <series> "Comic Neue" | --clear   the lettering font the series suggests (checks whether this PC has it)
taslation glossary lettering <series> thought|shout|narration|handwritten|sfx [--family NAME] [--italic|--no-italic] [--bold|--no-bold] [--reset]
taslation gui --role reader       start in Reader mode
taslation audit page.png       run the processing and show every network connection made (and at the end, whether any saved file is left unprotected)
taslation annotations list [--json]          list the books that have a notes file on this PC (pages, frames, memos, skipped pages, reading orders; no text is shown)
```

Global options: `--model NAME` (the default is the setting `ollama_model = "auto"`: the target language decides the model; see "Choosing the model"), `--ollama-url http://127.0.0.1:11434`,
`--margins L,T,R,B`, `--font path.ttf`, `--uppercase`, `--language German`,
`--models-dir DIR`, `--config taslation.toml`.

`gui` options of earlier versions that were for TASlation's own window (`--on-top`, `--full-screen`, `--reading`) are accepted and ignored
(the log says so), so a shortcut or a script that still has them goes on working. There is no `keys` command any more: TASlation sends no key to the viewer.
`read` reads the viewer's window at the size it has; it never moves or resizes it.

`--window` is matched against, in this order: the window's whole title; in a browser, the tab's whole title; the beginning of the tab's title; part of a tab title that looks like a viewer;
part of the window's title. When several windows match, it does not guess: it shows the candidates and exits (exit code 2).
Give a somewhat longer title. `gui --window` brings no viewer dialog at the start: the window named is chosen as soon as it is there,
and again when it is opened anew after it was closed.

### Choosing the model

By default (`ollama_model = "auto"`), the target language decides the model.

| Target language | Model (Ollama name) | Download | Licence | How it translates |
|---|---|---|---|---|
| Every language except Brazilian Portuguese and Turkish | PLaMo 3 Translate 2B (Preferred Networks; `taslation-plamo3-translate-2b`, Q4_K_M) | 1.8 GB | PLaMo Community License | One line at a time |
| Brazilian Portuguese, Turkish | Qwen3.5 4B (`qwen3.5:4b`) | 3.3 GB | Apache-2.0 | About 30 lines at a time |

PLaMo 3 Translate is a model made only for translation. TASlation builds its PFML3 prompt itself and sends it as it is to Ollama's `/api/generate`
(the form the model's card recommends for production use; the model's own chat template is not used: the template in the earlier revision's file could not be told
the target language through Ollama, and ended up translating back into Japanese, and the one in the current file builds the same prompt as TASlation). Each line is one request,
which carries the earlier lines and their translations, the series sheet as reference information (for a line with a speaker set, that speaker too), and, as a glossary, the series sheet's renderings that appear in that line.
The earlier lines grow from page to page and are cut back to the newest 20 only once they pass 60, so that each request's prompt begins with the one before it and Ollama does not compute that part again
(when they moved on by a page at every page, the first request of each page took about 1,050 ms instead of 142).
A region's hint for the model goes into the reference information of that line alone: in a test with invented lines it was followed in 38 of 78 answers (17 without it) and spoilt none,
but never for the register or for who is addressed, and hints that should change nothing changed the wording of 5 of 30 answers (docs/OFFLINE_VERIFICATION.md); the region editor says so.
The context is 8192 tokens, and it takes about 1.9 GB of GPU memory. On OpenMantra (Japanese to English, whole books, three runs each with fixed seeds),
its chrF was 5.9 higher than Qwen3.5 4B's (a bootstrap interval of roughly +4.7 to +7.2), and it was about twice as fast.
It cannot write Brazilian Portuguese or Turkish (it answers in another language), so for these two only, Qwen3.5 4B translates, in the JSON chat format.

You only need to install the one your target language needs. install.cmd asks for the target language in its first question and fetches that language's model.
Answer with a number from the list or with the English name (a language not in the list can also be chosen by name, if PLaMo or Qwen can write it). Enter means
the language last chosen in TASlation, otherwise the language that matches this PC's display language, otherwise English. If `taslation.toml` has `target_language`,
that is used without asking. If you choose a language other than the one shown, TASlation also starts with that language (it is written to `ui.json`).
install.cmd's questions are shown in Japanese if Windows' display language is Japanese (the translations are in `installer-texts.json`, and other languages can be added;
a language without a translation gets English).
When you choose a language in the left pane that needs the other model, TASlation offers to download that model (showing its size) and to remove the one no longer needed.
TASlation installs only one translation model at a time. For a model TASlation did not install (a `qwen3.5:4b` you had installed yourself, for example),
it asks separately whether to remove it, and keeps it by default. The first time PLaMo is installed, it first asks for your agreement to its licence (the PLaMo Community License as revised on November 9, 2026;
the main points are in `docs/THIRD_PARTY.md`). A PLaMo installed after agreeing to the earlier text goes on working as it is; agreement to the revised text is asked the next time PLaMo is installed.
When the publisher's server refused the download or no longer has the file, trying again will not help, so it tells you to update TASlation or to see the project's issues page.
On the command line, `--language` asks the same, and `python setup_models.py --translator-for "Turkish"` installs it too.
When `ollama_model` names a model of your own, nothing is offered.
When PLaMo is not installed but Qwen is, it translates with Qwen meanwhile, and the right pane says so.
When the model the target language needs is not installed and there is nothing to stand in for it, the right pane says that model is not installed. In both cases,
"Download model" in the Menu installs it there and then, without running install.cmd again.
If `ollama_model` names another model, that model is used with the chat prompts (what follows is the record of such choices).

Both models only translate. No further requests are made of the model, such as writing translation notes on the volume, reviewing translations, shortening translations that are too long,
or offering alternatives (removed on 2026-11-06). Only lines returned in Japanese as they were, and lines left out, are asked again automatically.

What follows is the record of how Qwen3.5 4B, the default until November 2026, was chosen.

The OCR models read the lettering, so what the language model sees is text. No pixels at all are sent to the language model. A text-only model will do. The vision weights of the models that take images (Gemma 4,
Qwen 3.5/3.6, Ministral 3) are a small burden at 4B and a large one at 9B and above. Besides translation quality,
translation needs a long context, support for a wide range of languages, and the ability to follow a glossary.

The candidates are open, text-only models that run on an ordinary PC, chosen from
[JP-TL-Bench](https://github.com/shisa-ai/jp-tl-bench), the only public benchmark that specialises in scoring Japanese-to-English translation (pairwise comparison by an LLM,
an "LT" score from 0 to 10; the figures are for the JA→EN direction in [the paper](https://arxiv.org/abs/2601.00223)).

| Model (Ollama name) | JA→EN LT | Download | Context | Licence |
|---|---|---|---|---|
| `qwen3:30b-a3b-instruct-2507-q4_K_M` (highest quality) | 9.77 | 19 GB | 256K | Apache-2.0 |
| `hf.co/XpressAI/shisa-v2.1-unphi4-14b-GGUF:Q4_K_M` | 9.36 | ~9 GB | 16K | MIT |
| `hf.co/XpressAI/shisa-v2.1-qwen3-8b-GGUF:Q4_K_M` | 9.02 | ~5 GB | 40K | Apache-2.0 |
| `qwen3:8b` | 7.94 | 5.2 GB | 40K | Apache-2.0 |
| `qwen3:4b-instruct-2507-q4_K_M` | not listed (the 4B base: 5.34) | 2.5 GB | 256K | Apache-2.0 |
| **`qwen3.5:4b`** (the default for Brazilian Portuguese and Turkish) | not listed | 3.3 GB | 256K | Apache-2.0 |

`qwen3.5:4b` won a knockout among 4B-class
models on a real volume ("Lighter models compared" and "A knockout among the 4B models" in `docs/OFFLINE_VERIFICATION.md`).
Translated the way the whole-book run of earlier versions translated, its translations are as close to the 30B's as those of the best build of Qwen3 4B (chrF 45.7 over 401 lines;
Qwen3 4B 46.2 at Q6_K, 44.5 at Q4_K_M), it follows the series sheet about as well (39 of 45 checks; the 30B 41),
and it is the fastest model among them. With Ollama's KV cache quantised (see "Installation"), it generates 60 tokens a second on a 6 GB
GPU while keeping a 16K context, about four times as fast as the 30B on the same machine. Its vision weights are not used,
and thinking mode is turned off for every request. In a blind evaluation with the 30B as judge,
Qwen3 4B came out slightly below the 30B (of 162 lines, the 30B's translation was preferred for 89, Qwen3 4B's for 63).

For the highest quality, use `qwen3:30b-a3b-instruct-2507-q4_K_M`. It is an MoE with 3B active parameters, and
needs about 20 GB of RAM, but uses little GPU memory. On the development machine it generates 17 tokens a second with a short context,
and 11 tokens a second with a 32K context. If you have RAM to spare, fetch it and set `ollama_model` and
`ollama_num_ctx = 32768`. The other candidates fared as follows.

* Shisa V2.1 8B (tuned for Japanese-English; other target languages are not intended) matches the 30B in quality, but it is a dense model,
  so with a practical context it does not fit on a 6 GB card.
* Hy-MT2 (`kaelri/hy-mt2`; translation only) is even faster at 1.8B but clearly worse,
  and the 7B mixes up bubbles in long requests.
* TranslateGemma 4B does not follow structured requests (one decent translation in 40 requests).
* Index-Translate (`hf.co/IndexTeam/Index-Translate-2B-GGUF:Q4_K_M` and the 9B) lost too. The 2B leaves one line in eight untranslated,
  and the 9B does not fit on a 6 GB card, is five times slower, and does not come close to the 30B.
* The only model higher than these on JP-TL-Bench is `ministral-3:14b` (9.88), but it includes vision weights,
  and needs a 12 GB GPU to be comfortable. Gemma 4, Qwen 3.5 and TranslateGemma are
  not on JP-TL-Bench. On Nejumi 4, a general Japanese leaderboard, Qwen3.5-9B (0.749) is well above Gemma 4
  E4B (0.669).

Switch models with `--model NAME` or `ollama_model` in the settings file (`"auto"` goes back to the choice by target language).

### Settings

The settings you change often are in "Settings..." in the left pane. Its "General" page has, under "Lettering", the largest lettering size; the size below which a translation is put on the list for a second look (Review);
the lettering size (80 to 200 %; 100 % keeps the largest size that fits the bubble, and 90 % sets every translation a tenth smaller;
above 100 %, nothing goes past the bubble or the largest size, and only translations that were held back to keep sizes even on the page get larger;
in the settings file it is `text_scale`, and a book's own value is in "Book settings...", in the Menu while editing); whether to letter in capitals; whether to set slanted lettering at the same slant; and whether to set larger what the original sets larger.
Under "Fitting lettering into bubbles" it has what is tried where a translation would be lettered small or with a hyphen, from the top down (the arrows beside each row change the order), and the smallest lettering size.
The translation itself is never shortened or asked again to fit. The rows (`fit_tries`, `["turn", "condense", "hyphenate"]` by default, in the order tried):
"Turn the line 90 degrees" (`turn`, on by default): in a bubble at least 1.2 times as tall as it is wide, whose text direction is Auto, with no formatting and no part set larger, the line is set across and turned to read from the top down, the tops of the letters to the right (as "Rotate all text 90°" in the region editor turns it).
It is taken only where the lettering across is under the review size (`readable_font_size`), at the smallest size, or has a hyphen, and turned it comes out at least 1.25 times as large and 2 pixels larger, with no more hyphens - or, where across a word has to be split anywhere it fits at the smallest size (in a narrow bubble, a long word in three pieces), turned it keeps every word whole at no smaller a size. Japanese and Chinese are never turned (they are set in columns).
"Narrower letters (down to 92 %)" (`condense`): where the lettering would be under 14 pixels, the letters may be set up to 8 % narrower.
"Hyphens (at most one in a word)" (`hyphenate`): there too, a long word may take a hyphen at one of its hyphenation points, once at most, leaving three letters or more on each line; the hyphens are tried before the narrower letters where this row comes first.
On, a word too wide for its bubble even at the smallest size is split as a last resort, at one of its hyphenation points where one fits (so too a word too long for two lines: a German compound breaks at its syllables).
Off, no word takes a hyphen at all: such a word is set whole at the smallest size and runs past its room, and the review list says "letters touch the bubble's edge" for it.
"Run over the bubble's outline" (`overrun`, off by default): where the lettering would still be small and this sets it larger by the same margin as for the turned line, the bubble's room is grown by 6 pixels (at the page's scale) over its outline, and the letters get an outline in the paper's colour (it shows where they cross the bubble's line).
A row unticked is not tried; with none ticked, the lettering is set at the size that fits with whole words (a word too wide even at the smallest size stays whole and runs past its room). The report of a region ("Copy a report of this region") says "turned" or "over the outline" when the lettering took one of these rooms.
Under "Dialogs" it has the size of the dialogs' text, the dialogs' colours (light, dark, or as Windows is set), reusing the translation of a short line seen before,
"Indicators at the right of the viewer" (`see_through_indicators`, the same as "Indicators" in the left pane), "Delay under the pointer" (`hover_delay_ms`: 0 to 3000 milliseconds, 450 by default; a number out of these bounds is not saved),
"Insert adds a text area" (`add_area_key`, on by default; off, Insert stays the viewer's) and "Start in Reader mode" (`role = "reader"`, off by default; from the next start, for a book you have not switched "Reader mode" for).
Last come the optional page models (the layout model and the inpainting).
"Set larger what the original sets larger" (`size_emphasis`, on by default): where the original letters part of a bubble larger than the rest (its characters are measured as they are read: a part at least 1.25 times the size of the rest, in whole lines),
that part is looked for in the translation once the page's translations are final, and no word of the translation changes. First the Japanese part is translated alone and looked for in the translation;
where it is not found, the bubble's line is asked once more with the part marked, and the answer only points at the words in the translation (kept only where their share of the translation fits the Japanese part's share and the part's own translation bears them out).
These are one or two short requests beside the page's, only for such a bubble (on the test volume about one bubble in ten pages, and about half a second for each such bubble). Measured with stand-in parts on a test set, the words it found were the right ones about 11 times in 12, and it found some for about half of the parts.
The part found is lettered larger (never more times larger than in the original, and at most twice the size; the rest never smaller than the readable size `readable_font_size`, nor than four fifths of the size the whole translation gets at one size). Where the bubble cannot hold both sizes so, the part is set less larger first, and under 1.15 times the rest the bubble is lettered at one size; where nothing is found, the bubble is lettered as before.
The translation cache keeps the part as its place in the translation (no Japanese), so a page from the cache asks nothing. With the setting off, every translation is lettered at one size. The right pane and copying keep the plain text.
For the inpainting (erasing lettering on the drawing with LaMa and filling in the drawing), choose "Not used", "Only with a GPU" or "Always, also on the CPU". The default is "Only with a GPU":
it is used only on a computer where the model is installed and there is a GPU TASlation can use (an NVIDIA GPU with CUDA, one that PyTorch can use with CUDA).
On other computers, erasing works as with "Not used", and the model is not even loaded (the setting's row then says so).
With "Not used" too, lettering on a screentone, a hatching or another pattern that repeats itself is painted over with that pattern (no model takes part in that).
Lettering in a bubble the layout model found and the usual detection could not outline, drawn see-through over the drawing (the drawing's lines cross the lettering), counts as lettering on the drawing too. Where the inpainting is not used, the straight lines of the drawing through it are kept.
`install.cmd` installs PyTorch's GPU build (the CUDA build) on a computer with an NVIDIA GPU, so there it is used with "Only with a GPU" as it is.
On a computer without a GPU (AMD and Intel GPUs are not counted as GPUs either), with an old driver, or where the GPU build did not work, the CPU build is installed, and the inpainting is not used there (docs/INSTALL.md, "Installation").
On a computer where an installation before this version put in the CPU build, running `install.cmd` again replaces it with the GPU build. The installation after `update.cmd` does not replace it, and says so.
With "Always, also on the CPU", it is used even without a GPU, but takes about 4 seconds a screen (about 0.6 seconds on a GPU).
For the layout model (it finds lettering on the drawing that the usual detection misses), choose "Not used", "Only with the inpainting" or "Always used". The default is "Only with the inpainting".
It is used on a computer that uses the inpainting, so on a computer without a GPU, or without the two models, detection works as before.
Before version 0.2.0 the default was "Not used". If you never chose, the new default applies. A settings file that says `detect_model = "off"` (a copy of the old `taslation.toml.example` has that line too) keeps it off.
Neither model makes clear where the images used to train it come from (`docs/THIRD_PARTY.md`).
The two models are installed together, with one question (`install.cmd` tells you about their origin before it asks). On a computer where TASlation uses LaMa on the GPU (one where the GPU build of PyTorch is being or has been installed),
Enter installs them ([Y/n]); elsewhere Enter does not ([y/N]). A run without a console installs them on neither (`-Yes` does not answer this question either).
Running `python setup_models.py` by hand asks the same way, and what Enter means is decided by whether PyTorch can use a CUDA GPU (the same judgement as "Only with a GPU"). With `--agreed`, it installs them without asking.
"Save" writes to `taslation.toml` and takes effect at once (the page on show is re-set from the cache). The file's comments and other lines stay as they are.
The dialogs' text size and colours change as soon as you save.
The dialogs' colours are "As Windows is set" (the default: the app mode in Windows' colour settings, looked at when TASlation starts), "Light" (Windows' own look) or "Dark"
(dark grounds with light text in the dialogs and their title bars).
The side panes take their colours from the viewer's ground and their size from the scaling of the viewer's monitor, whatever these two settings say. While Windows' high contrast is on, the dialogs use Windows' colours whatever this setting says (the row says so).
In the settings file it is `theme` (`"system"`, `"light"` or `"dark"`).

"Open settings file" opens `taslation.toml`, with every setting in it, in a text editor. If there is no file, it first makes one from `taslation.toml.example`.
In the file it makes, every setting is a description with `#` at the start of the line, and removing the `#` turns that setting on (no default value is written in, so if a later version changes a default, you get the new default).
It is made where the settings are read from (the file that was read, or else `taslation.toml` in the state folder; the state folder survives updates).
Updating with `update.cmd` does not overwrite `taslation.toml` in the TASlation folder (docs/INSTALL.md, "Updating").
Settings changed in the file take effect from the next start.

TASlation has no keys of its own to set: every key goes to the viewer, except Insert, which adds a text area while the viewer is in front
("Insert adds a text area" turns it off), and Delete, which drops the selected regions while editing ("Editing: correcting the page"). In the region editor, "Previous" and "Next" are Alt+↑ and Alt+↓, and copying and pasting formatting
Ctrl+Shift+C and Ctrl+Shift+V. Keys an earlier version saved for these in `shortcuts.json` in the state folder still apply, but there is no page to change them any more.

The "System" page of "Settings" shows, for each stage of processing a page (finding the text, reading the text, translation, erasing and lettering), where it runs ("GPU (the GPU's name)" or "CPU") and how many seconds a page took.
For detection, the classical detection runs on the CPU, and when the layout model is used, that model runs on the GPU. The OCR runs on the CPU, or two of its three readers on the GPU where it has room for them (`ocr_runs_on`, below), and the row says which and why. Translation runs where Ollama loaded the model,
and when only part of it is in video memory, it shows something like "GPU and CPU (60 % on the GPU)" (if no model is loaded, it says so).
For erasing, the fill with the paper's colour runs on the CPU, and when the inpainting (LaMa) is used, the part on the drawing runs on the GPU (on the CPU with "Always, also on the CPU" and no GPU). Only NVIDIA GPUs with CUDA are counted as GPUs,
and it neither loads a model nor starts Ollama to find out. The seconds are the average of the last 20 pages lettered, saved in `timings.json` in the state folder when TASlation quits (numbers only; nothing of the pages' content).
"Look again" refreshes it. `taslation doctor` prints the same as "Where each stage runs:". Below, it says how many short lines this session reused without asking the model ("Reusing short lines"; counts only).
Under that, "Translation model's layers on the GPU" (`ollama_num_gpu`) decides how much of the translation model Ollama puts on the GPU, for both translators (PLaMo and Qwen).
Empty (the default) leaves it to Ollama, and the requests are exactly as before. `0` runs it on the processor only and leaves the GPU free (translating several times slower); a number puts that many of the model's layers on the GPU and the rest on the processor.
It is sent as the `num_gpu` option of Ollama's requests. Once saved, the next request uses it (a model already loaded may take a moment to be loaded again for it).
With a number of layers set, a model split between the GPU and the processor is neither loaded again nor reported (it was asked for). Anything but empty or a whole number from 0 to 999 is not saved.
Under that, "OCR runs on" (`ocr_runs_on`) chooses where the OCR readers run: "The GPU when it has room" (the default), "The processor (CPU)" or "The GPU" (see below).
Where they run now, and why, is in the OCR row above. Once saved, "The processor (CPU)" and "The GPU" apply from the next page, "The GPU when it has room" from the next start.
The box under it, "When the GPU's memory is short at the start, start with part of the work on the processor without asking" (`gpu_short`), decides what a start does when its check finds the GPU's memory short ("What runs on the GPU", below).
Off (the default), it says by how much and asks; on, it starts with what does not fit on the processor. It applies from the next start.
When the start was short, or a part failed on the GPU, a note under the rows says so and what runs on the processor.
Last, "Translator's window cache" (`ollama_window_cache`) decides whether the Ollama TASlation starts keeps the cache of the translation model's whole window:
"On" (the default) or "Off" (see below). It applies from the next start of Ollama; the translation's row above
says whether the Ollama running now has it ("Started by TASlation with the window cache", or without it).
Under it, the box "Look for a new version once a day when TASlation starts" (`update_check`: `"off"`, the default, or `"daily"`; the installer asks once) makes TASlation, at a start a day or more after the last look,
30 seconds or more after TASlation is ready and while no page is read or translated, run a program of its own, `check_update.py`, which asks GitHub for the first 16 KB of `CHANGELOG.md`.
A newer version is named in the "Check for updates..." item of "Menu > Help" and in one line on the status line (no dialog). When it could not ask, it says nothing. It applies from the next start.
"Menu > Help > Check for updates..." asks when you choose it, whether the box is on or off; chosen again within a minute of an answer, it shows that answer again and asks nothing (after "could not ask" it asks again at once). It shows this version and the new one with their dates and what changed; "Update now" closes TASlation,
and `update.cmd` downloads the new version, updates and starts TASlation again (docs/INSTALL.md, "Updating"). The same box is in that window too.
The time of the last look and the newest version it found are kept in `update-check.json` in the state folder (nothing else is written there). In a git clone there is no look at the start.

The settings file `taslation.toml` is looked for in this order: the one given with `--config`, `./taslation.toml` in the folder it was run from, and `taslation.toml` in the state folder (`~/.taslation`,
or the place in the environment variable `TASLATION_STATE_DIR`); the first one found is read (with none, the defaults apply).
Put it in the state folder. `taslation doctor` shows which file was read.

A `taslation.toml` placed in the working directory or in this folder is read (optional):

```toml
ollama_model = "auto"        # "auto": PLaMo 3 Translate 2B, or Qwen3.5 4B for Brazilian Portuguese and Turkish; or a model of your own
ollama_num_ctx = 16384       # the chat translator's context window; PLaMo has its own (8192)
target_language = "English"
uppercase = false            # scanlation-style capitals (Latin script only)
size_emphasis = true         # the part the original letters larger is set larger in the translation too, where it is found there
readable_font_size = 11      # a translation set smaller than this is flagged "small" for review (0 = never)
text_scale = 1.0             # the lettering size (0.5-2.0): 0.9 a tenth smaller, 1.2 larger where the page held it back (a book can have its own)
enforce_terms = true         # a translation that misses a rendering from the series sheet is flagged "rendering"
spellcheck = false           # flag a word the dictionary does not know; its word lists (the pyspellchecker package) are an optional extra that TASlation does not install
take_columns_beyond = false  # dark bubbles: also read a column that goes on past the interior on the bubble's own black (a book setting too)
page_turn_wait_ms = 3000     # after a turn, a blank frame is looked at closely so long; a viewer behind other windows still blank then is raised once for a look
erase_mode = "fill"          # "fill": the bubble's own paper, flat or along its shading, within its outline;
                             # "inpaint": the same way, inpainted; "classic": the erase before 2026-10-30, byte for byte
art_erase = "auto"           # with "fill", lettering on the drawing is inpainted by LaMa once installed: "auto" only where PyTorch has a CUDA GPU (else as "off"), "lama" also on the CPU, "off"
detect_model = "auto"        # the layout model first, the classical detectors add what it missed: "auto" (where art_erase runs), "on", "off" (the default of earlier versions)
ollama_keep_alive = "5m"     # how long Ollama keeps the model after a request: "2h", "90s", seconds; "-1" never
                             # unloads, "0" unloads after every request
ollama_num_gpu = ""          # the model's layers on the GPU: "" Ollama decides, "0" the processor only, or a number
load_model_at_start = true   # TASlation loads the translation model at start, beside the OCR models; false: the first line to translate does
ollama_window_cache = "auto" # the Ollama TASlation starts: the cache of the model's whole window ("auto", "on"); "off": without it
ocr_threads = 0              # CPU threads for the OCR model (0 = torch's default, one per core); while
                             # other programs keep the CPU busy, half the cores can be faster
ocr_runs_on = "auto"         # "auto": two of the OCR readers where the check at the start puts them (the GPU when everything fits); "cpu"; "gpu"
gpu_short = "ask"            # the GPU's memory short at the start: "ask" (a box), or "processor" (what does not fit runs on the processor)
font_path = ""               # auto: the series sheet's font where installed, then models/fonts per script, then system fonts
reuse_lines = true           # a short line translated before in the book or its series gets that translation again
see_through_indicators = true  # the right pane: the bubble under the pointer, how far the page is, the status line
hover_delay_ms = 450         # the wait before a bubble under the pointer gives way to the original (0-3000; 0: at once)
role = "translator"          # at the start: "translator" (editing) or "reader" (Reader mode); a book keeps its own choice ("Start in Reader mode")
add_area_key = true          # Insert adds a text area while the viewer is in front (taken only then); false: Insert stays the viewer's
update_check = "off"         # "daily": at the start, look for a new version at most once a day (check_update.py asks GitHub); "off": only Menu > Help > Check for updates...
```

The size of the dialogs' text can be changed with `ui_scale` (1.0 follows Windows' scaling; 0.5 to 3.0).
It acts on the dialogs only: the side panes follow the scaling of the viewer's monitor.

Every key is a field of `taslation/config.py:Settings`, and
`taslation.toml.example` lists all of them with their defaults. Settings that were removed (`review_pass`, `series_notes`,
`notes_pages_per_request`, `revision_flag_distance`, `revision_changes_only`, `ollama_prompt_style` and others) may remain in the settings file: it is still read as before, and they do nothing.
So may the settings of TASlation's former window (`see_through`, `next_page_key`, `prev_page_key`, `always_on_top`, `over_book`, `bubble_zoom`, `hover_shows`, `hover_reveal`,
`side_indicator`, `panel_font_size`): a settings file that still has them loads, they are left out, and the log says so in one line.
A key this version does not know (a misspelling, or a setting of a newer version) does not stop the start. That key is skipped, and TASlation names it once (without showing its value).
On the command line, it is shown as a warning every time. The old-named `~/.selftrans` folder (and the even older
`~/.cleantrans`) is moved to `~/.taslation` at the first start, and `SELFTRANS_*` environment variables
are still read when there is no `TASLATION_*`.

### The OCR models and their licence

The lettering on the page is read by three OCR models (about 700 MB in all). manga-ocr-charspot-small finds and reads the characters one by one;
it is strong on long lines, but it also tries to read something from drawings with no text. So TASlation first checks this model's confidence
(the product of the mean likelihood of character centres and the mean certainty of telling the characters apart; `ocr_min_confidence`, 0.65 by default),
that the text is at most three times the page's usual character size, and that it has 2 characters or more; what fails is treated as not text.
That is why a line of a single character is skipped. In that case, add the region by hand ("Add area" in the left pane, or Insert). A region added by hand
is never put through this check.

A region that passes the check is also read by manga-ocr-nar-small. If the two readings are the same, that reading is taken. If not, manga-ocr-base-CPT-flex reads it too,
and of the three, the reading closest to the other two is taken (on a tie, charspot, then nar). When all three differ widely,
the line is flagged "TASlation may have misread the Japanese" for review. A region added by hand is read by all three models.

The weights of all three models are licensed **CC BY-NC-SA 4.0**, **for non-commercial use only**. TASlation's code is MIT, but
reading pages needs these models, so using TASlation requires agreeing to these terms. `install.cmd` shows the terms and
asks for your agreement once; if you do not agree, it ends without installing anything (`-Yes` does not count as agreeing either). The weights are not in the repository,
and the application never downloads them. Only `setup_models.py` downloads them.

`setup_models.py` shows the progress of large files in percent and MB. When the connection breaks partway, it continues from where it broke, up to 3 times in the same run
(when the server honours HTTP Range; if not, it starts that file again). For the OCR models, the page models
and the fonts, a failure leaves the partial file (`.part`), and the next run fetches the rest. A file completed this way, too,
is put in place only after the checksum of the whole file has been checked. PLaMo's files, on a failure or a cancellation, have their partial file deleted too
(because an installation from TASlation leaves nothing behind); only `install.cmd`, which tries a failed download 3 times and then stops, keeps it, so that its next attempt or run goes on from there. A file the server refused or no longer has (HTTP 401, 403, 404, 410) is not fetched again,
and the script ends with exit code 5 (running it again would not help, so it tells you to update TASlation or to see the project's issues page). When winget installs Python and Ollama, your Y to the question is passed on to winget
as agreement to its terms of use (`--accept-source-agreements --accept-package-agreements`; this is said before the question).

If an earlier installation has only manga-ocr-charspot-small, TASlation works with that model alone. The status line says so in one line,
and it is not an error. Running `install.cmd` installs the other two.

On the CPU, the OCR models share the `ocr_threads` setting. When the CPU is busy with
other work, setting `ocr_threads` to half the number of cores can make it faster.
The third OCR model reads only a few lines a page and stays on the CPU; where the other two read is in the next section.

### What runs on the GPU

With an NVIDIA GPU, TASlation checks once, as it starts, whether the card's memory holds everything its settings put there.
It counts the translation model whole (with its window cache when it has one, below), two of the three OCR readers (manga-ocr-charspot-small and manga-ocr-nar-small, `ocr_runs_on`), LaMa and the layout model when they are used (LaMa needs more on a screen taller than 1440 pixels, where the lettering is larger in pixels) and PyTorch's own memory, beside what other programs hold at that moment, with about 700 MB left over.
Those 700 MB are what the graphics driver keeps free (with less, it moves the memory of a program that is not computing just then into the computer's RAM, and that program waits for it at its next turn) and room for other programs to grow.
When Ollama has the translation model loaded already as TASlation asks for it, its memory counts as TASlation's, once, not as other programs', and it is not loaded again. Loaded at another context length (by another program, or an earlier version), the server would load it again, so TASlation loads it again at the start rather than at the first page.
The check comes after the legal notice, once Ollama answers and before any model is loaded. It asks nothing over the network (the figures are this computer's card's and Ollama's).

When it all fits, TASlation can be used at once and the models load in the background. The right pane says "Loading the models..." until they are all there, and the viewer can be chosen meanwhile. A page turned before that waits until what it needs is there.
With "Load the translation model at start" off, the translation model loads at the first page that needs it, but its room is counted at the start all the same.
Everything stays where it was put for the session: nothing is looked at again, and nothing moves.

When it does not fit, a box comes before anything loads: "The GPU's memory is short by N MB. Close other applications that use it and check again, or start with part of the work on the processor (slower)." Under that, it says what would run on the processor.
"Check again" (Enter) checks once more, after you closed something. "Start on the processor" starts with only what does not fit on the processor: the OCR readers first, then LaMa, then the layout model, and the translation model last. "Quit" (Esc, or closing the box) closes TASlation.
When Ollama holds other models in the card's memory, the box names them with their sizes, TASlation's own (for example the Qwen model a Portuguese (Brazil) or Turkish session left loaded) apart from other programs'. With one of TASlation's among them, "Release and check again" comes first (Enter then): it releases TASlation's models, waits until the card shows their memory free (3 s at most) and checks again. Another program's model is never released: close it in that program, or stop it with `ollama stop` and its name, then press "Check again".
The order puts first what loses the least time: the OCR reads beside the translation (a page about 1.2 s on the CPU, about 0.6 s on the GPU), LaMa erases only lettering on the drawing (about 1.7 s a place on the CPU, about 0.2 s on the GPU), the layout model works on every page before its first bubble (about 0.5 s a page unit on the CPU, about 0.06 s on the GPU), and the translation model translates about four times slower on the CPU.
With "Do not ask again on this computer" ticked, the next starts do so without asking (`gpu_short = "processor"`; the box "When the GPU's memory is short at the start, start with part of the work on the processor without asking" on the System page of "Settings..." is that setting).
The System page then says, under its rows, by how much the start was short and what runs on the processor this session.
On a 6 GB card with the default settings (PLaMo, both page models, a screen up to 1440 pixels high), the box comes when other programs hold more than about 1.7 GB at the start (about 1.4 GB with a taller screen). The larger translation model (Qwen3.5 4B) does not fit on a 6 GB card together with the OCR readers and the page models.

A computer without an NVIDIA GPU never sees the box. Neither do the `taslation` commands and the developer's tools, which cannot ask: they do as "Start on the processor" does.
`ocr_runs_on`'s `"cpu"` and `"gpu"`, and a number of layers in `ollama_num_gpu`, put those parts there whatever the room. With a part put on the GPU that way, the start never asks: it starts as the settings say and shows on the System page by how much it is short.

The memory other programs take after the start is theirs: TASlation does not look again. On Windows a card used past its memory gives no error; it gets slower, because the driver moves memory to and fro and the reading and the translation wait for it (on the 6 GB card a request began 0.2 to 0.5 s later, and with another program computing on the card the OCR read more slowly than on the CPU). The System page still says GPU meanwhile. Close the other program, or start TASlation again, which checks again.
When a part fails on the GPU (its memory runs out, a CUDA error), it goes on on the CPU until the session ends, the page comes out as usual, and the System page says so. The readings are the same on both.
While the translation model answers (the next page of a spread is read meanwhile, for one), the two OCR readers read on the CPU as well: on the GPU they would wait for the model's computing, 0.7 s a line against 0.13 s on the CPU.

Ollama's model is put in GPU memory only while it is needed. TASlation loads it at start, while the OCR models load (`load_model_at_start = true`, the default;
"Load the translation model at start" on the System page of "Settings..."), so the first page to translate does not wait for it. Nothing is shown for this load,
and when Ollama is not running or the model is not installed it does nothing (the first page that needs the model says what is wrong, as before).
With the setting off, and for the `taslation` commands, the model is loaded when a line that needs translating comes up
(this takes a few seconds and shows in the status). It is not loaded for a page whose translations are in the cache. A loaded model stays for
`ollama_keep_alive` ("5m" by default) after the last request (or after the load at start), then is released automatically; with `ollama_keep_alive = "0"` nothing is loaded at start. While you read on through untranslated pages, each request
extends this, so it is not loaded again for every page. When TASlation quits, and at the end of a run of a `taslation` command, it is released at once.
While you read a page and nothing is being translated, TASlation has Ollama compute the beginning of the next page's first request (the series sheet and the earlier lines that request starts from) when Ollama does not hold it already, as after the earlier lines were cut back to the newest: the next untranslated page you turn to does not wait for it (a second or so).
It sends what that request would send and keeps nothing of the answer, so the requests are what they are without it; as when Ollama computes a request from another starting point, the model can word a line slightly otherwise (on a test set about one line in ten, with about the same score). It shows nothing, is done only while the model is loaded wholly on the graphics card, and stops as soon as you turn.
With `ollama_keep_alive = "-1"`, as before, it is loaded at start, before the OCR models, and never released.
When only part of the loaded model fits on the graphics card, you are told so (it is not loaded again).
To free the GPU memory at once for a game or another program, use "Menu > Release the model now". It releases the translation model TASlation loaded or used this session
with a normal request of Ollama's API (`keep_alive` 0 for that model), and the page models (the layout model and LaMa) give their memory back too. It does so with `ollama_keep_alive = "-1"` as well.
A model another program loaded into the same Ollama is left alone, and Ollama itself is neither stopped nor started. OCR models on the GPU go back to the processor (the next page puts them back where the check at the start put them),
and what stays is the CUDA context PyTorch made once a page model or the OCR ran on the GPU (a few hundred MB), until TASlation quits.
The status line says what was released (the OCR's GPU memory too, when it held some). While a page is being translated and while a translation waits to start it releases nothing and says so in the status line.
If the model is still loading at start, it waits for that load and then releases it. The next line that needs translating loads the model again as usual.
Ollama runs only while TASlation uses it. When it translates and Ollama is not running, TASlation starts Ollama's server (`ollama serve`)
in a window that is never shown (never Ollama's app), and writes down that it did in `ollama-started.json` in the state folder
(the process's number, its program, when it started and the TASlation processes that use it; no text of a book). When you quit TASlation, or when a `taslation` command that translated ends,
it stops that Ollama. It does not stop it while another TASlation still uses it, nor while another program has a model loaded in it (in the second case TASlation no longer treats it as its own).
When it does not stop, the record is kept, and it is stopped the next time TASlation ends. When TASlation crashed and left Ollama running, the next TASlation that uses it takes it over.
An Ollama you started yourself (from the Start menu, or with `ollama serve`) was not started by TASlation, and is never stopped by it.
When a message such as "The translation program did not start" tells you to restart your PC, that is to end for certain an Ollama that stopped answering. After the restart, TASlation starts it again when it translates.
TASlation gives the Ollama it starts three environment variables. When TASlation's own environment lacks one, it passes on the value Windows keeps for this user (or this computer),
and only when there is none, its own; a value that is set is never changed.
On an NVIDIA GPU with 6 GB of memory or less, `OLLAMA_KV_CACHE_TYPE` is `q8_0` (Ollama then uses less GPU memory).
`LLAMA_ARG_SWA_FULL=1` makes llama.cpp keep the cache of the translation model's whole window, so that each request goes on from the one before instead of computing its whole prompt again,
and `LLAMA_ARG_CACHE_RAM=256` keeps 256 MB of earlier requests in RAM (without the variable Ollama uses up to 8 GB for them).
In TASlation's measurements on a 6 GB GPU, translating took about a quarter less time with them (296 s instead of 401 s for 214 pages translated in one pass,
0.98 s instead of 1.28 s a line without a GPU), and the model took 130 MB more GPU memory (220 MB with Ollama's default KV cache).
The setting "Translator's window cache" (`ollama_window_cache`) decides: "On" (the default; `"auto"` or `"on"` in the file) passes both,
"Off" (`"off"`) `LLAMA_ARG_CACHE_RAM=0` alone, as before. The check at the start counts the translation model with its window cache (130 MB) (the start of this section);
the window cache is no longer left out to keep the OCR readers on the GPU. What it chose is in the log, one line each time it starts Ollama,
and in the translation's row of the System page and of `taslation doctor`.
For an Ollama that was there before, `install.cmd` sets `LLAMA_ARG_CACHE_RAM=0` and, on a GPU of 6 GB or less, `OLLAMA_KV_CACHE_TYPE=q8_0` as environment variables of this Windows user
("Installation" in docs/INSTALL.md, which also says how to give your own Ollama the window cache). Because Windows keeps them, the Ollama TASlation starts on that computer gets `LLAMA_ARG_CACHE_RAM=0` too: the window cache without the 256 MB in RAM
(317 s instead of 296 s in the measurement above).

### Trying it without a book

`.\.venv\Scripts\python.exe tools\fake_viewer.py`, run in PowerShell in the folder that holds `install.cmd` (`python tools/fake_viewer.py` in a source checkout), opens a stand-in viewer that shows synthetic test pages (left arrow for the next page, pressed in its window).
Choose the window titled "Fake Viewer" in TASlation and turn its pages there: you can check that capture, translation
and the lettering over it all work.

### The error log and "Copy details"

TASlation records errors in `log.txt` in the state folder (when it grows large, it moves on to a next file, and the oldest are deleted, so it is about 1 MB in all).
It writes the environment at start (TASlation's version and date, Python, Tk, Windows, torch and the graphics card, Ollama's version), the names and values of settings changed from their defaults,
warnings, and errors with where they happened (the program's file name and line).
It does not write the page's text, OCR results, translations, book titles or window titles. For file locations, it writes only the state folder and the models folder, by name (`<state dir>` and the like),
and replaces the file names beyond them, and any other place, with `<path>`. Quotations in error messages, and characters that are not ASCII (Japanese and so on), are replaced with `…`.

"Copy details", in "Menu > Help > About TASlation" and on the screens that report an error, puts the same content (environment, changed settings, the last error) on the clipboard,
with the offline guard's state added (on or off, the address of Ollama on this computer it can reach, and how many connection attempts it blocked).
Paste it when you report a problem. It sends nothing anywhere. On the screen shown when it could not start, too, "Yes" copies it.

### Reporting a problem

"Menu > Copy a report" puts a report of the page on show on the clipboard, ready to paste where you ask for help (an issue, a message).
It holds numbers and states only: no text of the page, no title of a book or of the viewer's window, none of your file names and no pictures, and its first line says so.
Nothing is written to disk and nothing is sent anywhere; you paste it yourself. After copying, the right pane says how many lines went to the clipboard.

It is plain text between two lines of three backquotes, in sections with English names whatever TASlation's language (`[region 3]`, `[page]`, `[screen]`, `[panes]`, `[program]`, `[log]`), each a list of `key = value` lines, the most important first:

- the regions: each one's number (as its plate shows it and as the region editor counts it), state, kind, box in the frame and on the page and its distance to the page's edges, how many characters were read and how sure the readers were, the translation's length and flags, the lettering's size and what it could not do, how it was erased and how many dark pixels of the original the erase left inside it (`dark_kept`), its pieces on the lettering's window and whether its lettering shows now and, when it does not, why (`differs:top`, for example: the pixels round it at the top changed since the page was read);
- the page: its key as the log names it, its size, single page or spread, from the cache or read now, the regions by state, how many of those lettered show, the times of the page jobs (started, first request, first line lettered, finished or cancelled and why) and the translator's requests;
- the screen: the monitors, the viewer's window (a browser or an app, never its name), its place, DPI and state, whether it is in front and what covers it, the capture, the frames per second and what the frames were lately, the capture area, the page box at rest, the band where bars never come and the bars;
- the side panes and the lettering's window: where each shows, or why it is hidden, whether the lettering takes the mouse, the Insert and Delete keys, the last changes of the window in front;
- the program: its version and commit, Python, Windows, torch and the GPU with its memory free, the languages, the mode, the models and where each runs, the translation program, the offline guard, the settings changed and the last error;
- the log: the kinds of warnings and errors of this session and how many, without their values.

While editing, with regions chosen, the Menu also has "Copy a report of the chosen regions" (those first and in full) and, with one region chosen, "Copy a report with this region's text".
In the region editor, "Copy a report of this region" does it for its region; check "With this region's text" first to add that region's Japanese and translation. No other region's text goes in, and never a title.

## Checking for yourself that it works offline

What the guard covers is TASlation's own process: the one the Start menu starts (`taslation gui`) and every `taslation` command. Before anything heavy is loaded, it makes every connection and every name lookup fail
unless it goes to this computer (loopback) on Ollama's port (11434 by default), and it tells the libraries that load models to stay offline.
It does not cover other programs. Ollama, which does the translating, is a program of its own: TASlation starts its server when it is not running (`ollama serve`, which TASlation stops again when it no longer uses it), and asks it, on 127.0.0.1, to load and release the translation model
and to translate the lines TASlation sends (`/api/generate`, `/api/chat`, `/api/ps`, `/api/tags`, `/api/version`); through the `ollama` command it lists the models
and removes one no longer needed when you agree (`ollama list`, `ollama rm`); and the downloader asks it to fetch or import a translation model
(`ollama pull`, `ollama create`). What else Ollama does is not under TASlation's control.
The downloader (`setup_models.py`, which TASlation and the command line run as a separate process when you agree to download a model) and the installer (`install.cmd`, which `update.cmd` also runs) run without the guard: they download.
The third is `check_update.py`, the program that looks for a new version: TASlation runs it as a process of its own when you choose "Menu > Help > Check for updates..." and, when you turned on the look at the start, once a day;
`update.cmd` runs it when it is asked to look for and download a new version. It runs without the guard too, and the TASlation package never imports it.
It asks GitHub's three hosts only: raw.githubusercontent.com for the first 16 KB of `CHANGELOG.md` (a Range header asks for that part only, so the request stays this small however long the file grows), and github.com for that version's ZIP, with an HTTPS GET
(the ZIP is tried up to three times when a download breaks off or what came is not a whole ZIP, every entry of it read back: a broken one is downloaded whole again); github.com sends the ZIP on to codeload.github.com. Sent on to any other address, it stops without asking there.
Besides the plain headers HTTP needs and that Range header, it sends only a fixed User-Agent (`TASlation-update-check`): no query string, no cookie, not the installed version, nothing about this computer or your books.
GitHub sees the IP address and the time, as any site you open does. It uses no proxy.
TASlation's own process connects nowhere for it, so what `taslation audit` lists of TASlation's own connections is the same with it.

With an installation made with `install.cmd`, TASlation's program is `.venv\Scripts\taslation.exe` in the folder that holds `install.cmd`; it is not on PATH.
Open PowerShell in that folder (with the folder open in File Explorer, type `powershell` in the address bar and press Enter), then:

1. `.\.venv\Scripts\taslation.exe doctor` prints, among its lines,
   `Network guard: ON (loopback:11434 only; 0 attempt(s) blocked)`.
   In TASlation, "Copy details" in "Menu > Help > About TASlation" copies the same state, as a line `Offline guard: on; ...`. The right pane shows something
   only when the guard has blocked an attempt to connect (it then stays until you quit TASlation).
2. `.\.venv\Scripts\taslation.exe audit tests\fixtures\sample_page.png --translator echo`
   runs detection and OCR on a sample page that comes with TASlation, with a stand-in translator that sends nothing, and lists every network connection the process made.
   Under `--- network audit ---` it says `allowed calls: none (no network call at all)` and `blocked attempts: none`.
   Its last part, `--- saved files (at rest) ---`, counts the saved files with text of a book in the data folder and ends with `plain files with text of a book: none` when every one is protected; it changes nothing.
3. The same command without `--translator echo` translates the page with Ollama (starting it when it is not running, and stopping it at the end):
   the allowed calls listed are lookups of and connections to `127.0.0.1` on port `11434` only (for the request that loads the model, and the page's requests).
4. Turn off Wi-Fi or unplug the cable, and use it as usual. Ollama goes on answering, and the OCR models and the page models
   are loaded from `models\`.

From a source checkout with the development tools (`pip install -e .[dev]`), the tests check the guard and the protection of the saved files:
`python -m pytest tests/test_netguard.py -q` (name lookups, direct connections, UDP and a loopback port other than Ollama's are refused, and a subprocess using the raw socket module is stopped by the audit hook)
and `python -m pytest tests/test_protect.py -q` (with Windows' data protection, in a temporary folder).

`docs/OFFLINE_VERIFICATION.md` records the procedure and the results of the checks made during development.

## How it works

See `docs/ARCHITECTURE.md` for the details. In outline: a page on the screen is identified by a 320-bit perceptual page fingerprint (one page at a time for a spread; the fingerprint is taken over the inked area on that page's paper, and in a viewer with a dark background, the page's large bright part and what lines up with it are taken as paper; any text in the area is treated as belonging to the page above, below or beside it),
and if it is in the cache, the saved translations are laid over the live page. If not, it detects the text (with the layout model and OpenCV's classical detection where the inpainting runs, with OpenCV alone elsewhere), runs the OCR,
translates with the Ollama model (with the series sheet and the pages just before as context; PLaMo one line at a time, Qwen once per page), erases and letters, and saves the translations in the cache.
The program's icon is drawn by `tools/make_icon.py`
with Pillow alone and kept in `taslation/ui/assets/`. Run it again if you change the drawing.

## Limitations

* Where the inpainting runs (by default, a computer with an NVIDIA GPU that PyTorch can use with CUDA and both page models installed; "Layout model:" and "Inpainting:" in "Settings"), the layout model finds the lettering first and the classical image processing adds what it missed; elsewhere detection is classical image processing alone.
  The classical detection covers closed bubbles and boxes (bright and dark alike; dark bubbles, and light lettering on dark parts, are lettered in white)
  and dialogue and sound effects written straight on the page. For text written straight on the page, only the letters and the bright background around them are erased; the drawing next to them, fine lines and halftone dots included, is kept,
  and the translation is set in the space that is freed. When the drawing is close, the translation gets smaller, and small bits of drawing mistaken for parts of letters are erased with them.
  Text that runs into busy drawing of the same darkness is missed by the classical detection. With `translate_sfx = false`,
  hand-drawn sound effects are left as drawn. The layout model, its licence and what its card says of its training data are in `docs/THIRD_PARTY.md`.
  A bubble the layout model found and the classical detection could not outline has its translation set on the paper closed round its lettering, inside the bubble's outline, where there is such paper; elsewhere in the box the model found. Inside the outline, the translation of a narrow bubble is smaller.
* Bubbles that touch or overlap and form one white area are cut apart where they narrow, or where the outline turns sharply inward from both sides, and each is translated on its own.
  This also holds when the two texts sit offset from each other, as long as they are set further apart than the lines within each.
  A single bubble with two sets of columns stays one region (`split_joined_bubbles`, which can also be changed in the book's settings).
  Where the boxes of two regions overlap, each translation is set in the part nearest its own Japanese, so no two translations run over each other; pages from the cache get this as they are shown.
  Pages cached by an earlier version hold only one translation for a pair of touching bubbles, so translate them again with the circular arrow (not using the cache).
* OCR accuracy hardly depends on the size of the letters (clean vertical text reads as well at 12 px as at 28 px,
  and enlarging the crop changes nothing). What lowers the accuracy is text on screentone, decorative typefaces, and regions that are not text at all; these are problems of detection.
* Erasing stays inside the bubble's outline and paints with the bubble's paper colour (cream and shading too), so
  it does not paint over thin outlines broken by anti-aliasing (on the test volume, the pixels changed outside bubbles fell from 67,624 to 19,882,
  and the pixels of broken outlines from 13,398 to 166). `erase_mode = "classic"` brings back the earlier way of erasing.
  Letters drawn into the outline itself, parts without a clear outline (ink splatter and the like), and one or two characters in a small bubble may be left unerased.
* Regions the OCR model can only guess at (faces, highlights, illegible sound effects) are dropped by the confidence filter (`ocr_min_confidence`). One or two characters in a small region (`min_short_bubble`,
  under 60 px on a page 1170 px high or more, proportionally less on a smaller one) are taken for dots in the drawing and the like, but a short line with a confidence of 0.95 or more that starts with hiragana or kanji,
  in a bubble with an outline, is translated. Katakana in a small region (mostly parts of drawn sound effects) and lone symbols (exclamation marks,
  ellipses) are left as drawn.
* Capture only the page part (for a viewer read in a browser,
  leaving out the browser's tabs and address bar is enough; the reader's own toolbar is ignored automatically). A spread is split into two pages. In a viewer with a dark background, even on a page whose lower half is a black panel, the bubbles and panels lined up with the bright part are taken as one page, and the reader's slider, buttons and bars are not captured. Where the page's edge is the same black as the viewer, that part falls outside the page, but its text is read as part of the neighbouring page. Text in the area that belongs to no page is read as part of the nearest page, so keep the reader's own bars out of the area. While the reader shows a header or page slider over the page, it is read together with its bar, so the page fingerprint changes.
* Bubbles with screentone or a dark colour inside, and bubbles with a broken outline, may be missed.
* The quality of the translation depends on the Ollama model. Larger models do better, and are slower for it.
  In languages the model is weak in, the translations are worse.
* Names are rendered consistently only when they are written in the series sheet. A name not written there is read by the model line by line, so its rendering may vary.
  Find such names with the review flags or "Find and replace...", and add them to the series sheet.
* Page fingerprints stand up to differences in window size and viewer background,
  but not to switching between single-page and two-page display (a spread is split into two pages, so pages translated as spreads are recognised in single-page display too,
  but not the other way round).
* Capture is Windows only. On other operating systems, the `translate` command processes image files.
