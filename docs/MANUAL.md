# TASlation detailed manual

日本語: [MANUAL.ja.md](MANUAL.ja.md)

This is a translation. The Japanese text, [MANUAL.ja.md](MANUAL.ja.md), is the original, and it prevails where the two differ.

Everyday use is explained in the app, under "Help > How to use...". This manual gathers the detailed explanations: the settings, the command line and so on.

## How to use

1. Open the book in the viewer and show the page where you want to start translating.
2. Start TASlation from "TASlation" in the Start menu.

3. Choose the viewer's window in the "Viewer" list. TASlation carries no list of stores or viewers,
   so a viewer you use for the first time on this computer is not chosen for you (only a window whose title has a word such as "book", "電子書籍" or "本棚" is).
   Once you have chosen it, that viewer's window is chosen automatically from then on, even if you open it after TASlation. When several windows look like viewers, none is chosen automatically:
   the status line says so, and you choose one from the list. A browser window is judged by its tab title without "- Google Chrome" and the like,
   and a title in which a word such as "book", or a viewer's name it has learned, is only part of a longer word is not taken for a viewer. In a browser-based reader,
   the part that is the page, without the tabs, the address bar and the reader's own frame, is found automatically, and only that part is read. If that does not work, use "Set area..." in the "Page" menu once
   and drag a rectangle around the page (it is remembered per window). The area you set is treated as an outer frame,
   and the page part is looked for and read inside it as well (the part found is shown with a dashed line). The rectangle is resized with its eight handles, moved by dragging inside it,
   and drawn again by dragging outside it. Enter confirms, Esc cancels, and "Clear area" goes back to finding the page automatically.
4. "Auto" is on from the start: each time you turn a page in the viewer, the page is translated or brought from the cache.
   When you edit in translator mode, for example, untick it to stop following.
   "Translate (F5)" processes the current page by hand (if the page is in the cache, that is shown; to translate again without using the cache,
   use translator mode's "Translate again" (it does not use the cache)). If you press it while the OCR model is still loading, for example, it runs as soon as it can.

The window shows the viewer's current display without watching the viewer all the time. When you turn a page from TASlation, it looks right after and once more one second later,
so even with a viewer that first draws a blurred picture (a viewer read in a browser, for example), it reads from the sharp picture.
A page whose translations are all in the cache is shown from the cache as soon as the new picture arrives, without an untranslated picture in between.
With a viewer that has drawn a blurred picture first, though, a blurred picture shows as it is, and the page is shown from the cache as soon as the sharp picture arrives
(on a blurred picture only some of the bubbles are found, and the translations would sit off their places). In translator mode,
once the picture has settled (no new picture for 0.4 seconds), the page is read once more and the bubbles not in the cache are added.
While you operate the viewer directly, it looks every 0.7 seconds, and while neither window is in front, it does not look (after a move, a tab switch
or a scroll it looks once). Windows tells it which window is in front, so it does not read the contents of other windows.
With `follow = "poll"` in `taslation.toml`, it always looks every 0.7 seconds.
A page that is not in the cache is also read from the first new picture, without waiting for the picture to settle.
As soon as it has been read, and a look has found the picture still the same, the model is asked for its translations, and the picture is
watched while the model answers. What it translates is kept in the cache only once the picture has stayed the same for 0.8 seconds (twice the
`settle_ms` setting, the same for every viewer). If the picture changes before that (a page sliding in, a blurred picture replaced by the sharp one),
the request is stopped, what was read from the picture is dropped and the page is read again from the new picture.
A sharp picture that replaces a blurred one later than that drops what was kept from the blurred picture too: while its translation still runs,
and with a viewer that has drawn a blurred picture first, up to 2 seconds after it is done.
With `early_start = false` in `taslation.toml`, a page is read only once its picture has stayed the same for `settle_ms`, as in earlier versions.
A page turned while another is being translated shows at once as the viewer draws it, with nothing of the other page's translation over it;
that translation is stopped only once the new picture has stayed the same for a moment (0.15 seconds; a black flash or a loading indicator stops
nothing, and back on that page, its translation shows again), and the new page is read then. A page already translated and on show,
whose work is only to get its next showing ready, gives way at once.
The bubbles the stopped page had translated by then stay in the cache, the page marked as not finished (only when its picture had stayed the same for 0.8 seconds, as above):
back on it, they are lettered at once and only the rest is read and translated. A page stopped with "Stop" or Esc keeps nothing, as before.

An untranslated page fills in while you look at it. The bubbles found are marked with frames (dashed; solid once read; gone once they turn out not to be text),
and they are translated in the order the page's bubbles are read, each with the lines before it as context. Each bubble is lettered as soon as its translation is ready.
A line goes to the translator as soon as it is read, before the rest of the page is read, so the first bubbles come sooner; once the page is read,
a bubble translated that early may be replaced (for example when the reading order turned out different): it shows without lettering for a moment and is lettered again. At the end,
names spelled differently from the series sheet are made consistent mechanically, so a few bubbles may change. A translation that does not fit its bubble is set in smaller letters
(the model is not asked to shorten it).
In the Reader role the bubbles filling in are the progress. Only when no bubble is lettered 1 second after you look at the page does the left end of the status bar
(on the full screen, the bottom of the margin on the side the page turns to) say "Loading the model...", "Reading the page..." or "Translating...",
and it goes when the first bubble is lettered. No seconds are shown and nothing turns. A page that could not be translated shows an orange "!" and
"This page could not be translated. F5 tries again." in the same place while that page is on show, and a page with nothing to read shows "Nothing to read on this page." for 4 seconds.
Nothing else is said there. In the Translator role, the badge at the top right shows what it is doing and how many seconds have passed, as before,
and the status bar shows the same.

### Pages you turn past

While you read, TASlation goes on reading and translating the pages you have turned past. How far it is shows in the margin on the side the page turns to
(the left in a book read right to left, the right in a book read left to right), in both roles, in the window and on the full screen.
This work runs at a lower priority than the programs you use, so that turning a page, and the page you are on, come first.

* Where the margin is 141 pixels or wider, it is a column of the pages turned past, top to bottom. Each page has a small thumbnail (too small to read),
  its number and two bars (R for reading the text, T for the translation). A bar shows its state by its letter, its colour and its pattern: empty is not started,
  a moving stripe is under way, filled is done, a cross did not work, hatched is not needed, dotted could not be taken. The page on show has a yellow outline
  and a triangle pointing at the page, and the column scrolls by itself to keep it in view (the mouse wheel scrolls it too).
* Where the margin is narrower, it is a narrow bar beside the page (6 pixels in the window, 8 on the full screen): a mark a page from the top, and with many pages
  the pages one after another in the same state make one mark, so that hundreds of pages fit. Filled is done, half filled is under way, hollow is waiting,
  striped across did not work, dotted could not be taken. The page on show has a yellow outline and a triangle.
  Where the margin is narrower than 24 pixels, the page is drawn 16 pixels in from that side only, so that the bar never covers it.
  That width changes only with the window's size, the full screen on or off, and the setting, never as you turn the pages.
* A page turned too fast to be taken is a dashed frame with its number and "?". Turn back to it in the viewer and it is read like any other.
* A click on a thumbnail shows in the status bar how to read that page (turn to it in the viewer: TASlation shows the translation over it).
  Nothing else happens: TASlation never shows a page from its memory as a page to read, and sends nothing to the viewer.
* The pointer resting on a thumbnail says what that page is, on a bar the state of that stage, and anywhere else the whole: how many of the pages seen are done,
  the pages and lines still to go, about how long that takes (once that can be trusted: 8 lines or more over 15 seconds or more), how many pages could not be taken,
  and how many were updated since you saw them.

When the words of a bubble on a page you have seen with its translation change later (the work behind finished, names were made consistent, find and replace,
a series correction, translating again), its thumbnail gets a diamond at its corner (on the narrow bar, beside its mark). So does a bubble you saw in Japanese
that is translated now. Size, fill, outline, review flags, font and emphasis do not count, nor does a change made on the page on show, nor a page you have
never seen with its translation. When you turn back to that page, the bubbles whose words changed get corner brackets in the same colour (a shape unlike the
dashed frame of a bubble found and the solid frame of one read). They go, and so does the diamond, once the page has been on show for a time that follows the
characters changed (1 second and 60 milliseconds a character, from 2 to 8 seconds), or once the pointer rests on that bubble. Turn away before that, and the
diamond stays. The words you saw are kept in memory only and never written anywhere; they go with the book.

Choose its form in "Tools > Settings...", "Pages turned past:": "Thumbnails where there is room" (the default), "A narrow bar" or "Not shown" (`side_indicator` in `taslation.toml`).

### With a single screen

You do not need a second monitor. Tick "Always on top" in the "View" menu (or start with `--on-top`)
and place TASlation over the viewer. The viewer goes on drawing underneath, and capture goes on as before.
Chrome stops drawing when an opaque window covers it completely, so the TASlation window is 99% opaque.
If the viewer stops drawing even so, TASlation keeps the last picture and tells you, in the banner above the page, to un-maximise TASlation or move it so that a little of the viewer shows
(it never shows a copy of the screen, that is, a picture of TASlation itself). "Move TASlation aside" in the banner
un-maximises TASlation and narrows the TASlation window so that a little of the viewer shows at the edge (only TASlation's window is moved).

The basic way is to turn the pages in the TASlation window. You can operate the viewer from TASlation. TASlation never sends the viewer a key you did not press.

* The arrow keys, Page Up/Down, Home, End and Space pressed on the page are sent to the viewer, and each new page, as soon as it is shown,
  is translated or brought from the cache.
* A click on the page is passed to the same place in the viewer (a viewer that turns pages on a click, its toolbar, the next-page arrow, closing a panel, and so on).
  Clicks are passed on in reader mode, in the window and on the full screen, and in translator mode while a page that is not translated is shown in the window (on the full screen in the Translator role they never are). While translator mode
  shows a translated page, clicks belong to TASlation, which uses them to select and edit text regions (pages can be turned with the keys).

To a desktop viewer, keys are sent straight to its window without taking the focus. For a viewer that ignores them, TASlation presses the key for real
and then gives the focus back, but only when the viewer's picture has not changed at all for 3 seconds (`page_turn_wait_ms`). Keys you press again
within those 3 seconds are not lost: each of them is pressed for real too, in order, one page each. If two pages were turned even so,
the status line says so and shows the key that goes back one page. Which way of passing the key turned the page is recorded per viewer in `profiles.json`,
and from then on that way is used from the first key (the 3-second wait happens only the first time with that viewer). A key sent straight to a browser while it is not in front does not reach it
(0 out of 9 times, tried with Chrome and Edge). So a browser is brought to the front for a moment every time and the key is pressed for real, and the focus
comes back once the browser has read the key; when it cannot be brought to the front, nothing is sent,
and you are told "click the book and turn the page there". To read large, use TASlation's full screen (F11).
The viewer's own full-screen display is optional; if you use it, switch it yourself, inside the viewer (see "Over a full-screen viewer", next).

### Over a full-screen viewer

This is optional. When you have put the viewer into full screen yourself (TASlation never does), and the viewer is full screen (or fills the monitor)
on the same monitor as TASlation, TASlation behaves like Windows' on-screen keyboard.
It always stays on top, but clicking it does not bring it to the foreground (where key presses go). The viewer stays in the foreground,
so the page keys reach the viewer directly as usual, and TASlation follows to the new page. Browsers go on drawing too.

* TASlation's buttons, checkboxes and so on work with a click as usual.
* F5 (translate) goes to TASlation even while the viewer is in the foreground (it does not reload the browser). On TASlation's full screen,
  F11 and Esc also belong to TASlation and leave it (in the Translator role Esc first lets go of a selected region).
  Otherwise F11 and Esc, and the page keys, belong to the viewer (you can use them to switch the viewer's own full screen). TASlation takes these keys only in this mode, and only while the viewer or TASlation is in the foreground.
* When you click a box you type in (Series, Vol., To:), press on the page in translator mode, or open a dialog (book settings, the series sheet,
  editing and so on), TASlation becomes an ordinary window for that time and takes key presses. Click the book
  or close the dialog, and it goes back.
* When the book is on another monitor, nothing changes.
* Untick "View > Over the full-screen viewer" to turn it off; it stays off at the next start too (`over_book = false`
  in `taslation.toml` also turns it off by default).

### Full screen

"Full screen" (the toolbar button, or F11) shows the page alone on the whole screen, in the role you chose. It puts a black full screen over the viewer,
enlarges the capture area to fill the screen, and shows only the translated page. Fit the area exactly to the page first.
The toolbar, the menus and the status bar are away while it lasts; the status is shown at the bottom of the screen instead.
The pages you turn past (see "Pages you turn past") show in the margin on the side the page turns to, and the Reader role's status at the bottom of that margin.
It opens on the monitor the window is on, and for a browser window where neither an area nor the page part is known, F11 first asks whether to "Set area..." or "Read as it is".

* **In the Reader role** it is for reading as you would read the original book. Page keys and clicks go to the viewer, and Auto follows (if it was off, it is on only while you read, and this is said at the start of each such session). The status shows for a few seconds only.
* **In the Translator role** the page keeps the Translator's pointer and keys, as in the window: a click selects a region, a drag moves, resizes, turns or draws one, and a double click or Enter opens the editor;
  F5, Undo, Delete, Tab and the other keys of translator mode work, and the regions' frames, numbers and flags show as in the window. Clicks stay TASlation's whatever the page shows:
  none goes to the viewer (a click on a page that is not translated yet says to press F5), and the page keys still turn the viewer's pages. Auto stays as you set it.
  The region editor and the other dialogs open above the full screen, and closing them brings you back to it. A status line stays longer there, by its length (up to 12 seconds).
  Changing the role and the Series and Vol. fields need the toolbar: leave the full screen for them.

F11 takes you back to the window, and so does Esc (in the Translator role Esc first lets go of a selected region). To go back with the mouse, move the pointer to the top edge of the screen: a faint "✕ Leave full screen (F11)" appears at the top right,
and you click it (it disappears when you move the pointer down; clicks anywhere else go on as before). With `taslation gui --full-screen`,
the full screen starts as soon as the viewer is chosen (`--reading`, its earlier name, does the same).
When you translate a book that has no name yet (in a browser viewer whose tab title is only the viewer's name, for example) on the full screen, those translations are not saved anywhere.
When you leave the full screen, the book's name is asked for once; once you name it, the pages from then on are saved under that name (the page on show can be saved with F5).

The full screen translates untranslated pages one page at a time, as the window does. The full-screen window covers the viewer,
so the page can be taken only from what the viewer itself draws. Chromium-based viewers, such as the viewers read in a browser, do draw;
with a viewer that does not, the page says so: press F11 and read in the normal window.

### The bubble under the pointer: the original, the translation, and copying the Japanese

In the window and on the full screen, in either role, resting the pointer on a bubble shows that bubble's "other side"
(how the Translator role differs is under "In the Translator role" below).
Two choices decide what the page shows and how the other side is shown. Both are in the View menu and in Tools > Settings..., and a choice applies at once to the page on show
(nothing is translated again). They are kept in the settings file (`hover_shows`, `hover_reveal`).
Each has a shortcut action ("Switch between the translation and the original on the page", "Switch between a panel and the bubble itself under the pointer"),
with no key at first (Tools > Settings... > Shortcuts gives them one).

* **On the page** (`hover_shows`): "Translation on the page, original under the pointer" (the default, `"original"`), or "Original on the page, translation under the pointer"
  (`"translation"`). With the latter the page is exactly as the viewer shows it (nothing erased, nothing written), and the translation shows only on the bubble under the pointer.
* **Under the pointer** (`hover_reveal`): "A panel beside the bubble" (the default, `"panel"`), or "The bubble itself" (`"in_place"`).

| On the page | Under the pointer | Resting the pointer on a bubble |
|---|---|---|
| Translation | Panel | A small window beside it shows an enlargement of the original bubble and the translation at a readable size. |
| Translation | The bubble itself | That bubble alone goes back to what the viewer shows (the original lettering) where it is, and back to the translation when the pointer leaves. |
| Original | Panel | A small window beside it shows the translation alone, at a readable size, in the faces of its kind (a thought in italics, a shout in bold). For a bubble still being translated it says "This bubble is being translated..." with a running bar. |
| Original | The bubble itself | That bubble alone is erased and its translation set where it is, exactly as the translated page has it. A bubble still waiting for its translation shows its outline. |

**Which to choose**: the panel puts the original and the translation in sight at once, which suits holding one against the other as you read. The bubble itself shows the
original font and lettering (which the panel's plain text cannot), and shows in place what was read as text, what was erased and how the translation is set,
which suits finding a mistake of the OCR or of the detection (characters missed, a piece of the drawing erased).

The wait before either shows is the same. With the translation on the page, a bubble that is hard to read (one flagged "small", a translation much longer than the original,
or one shown on the screen smaller than the readable size `readable_font_size`) shows after about 0.5 seconds and other bubbles after about 1.2 seconds; with the original on the page,
every bubble after about 0.5 seconds. So a pointer that merely passes over the page shows nothing.
"Delay under the pointer" in Tools > Settings... (`hover_delay_ms`, 450 by default) changes both waits: that many milliseconds, and about 2.7 times as long for the other bubbles; 0 shows at once. One bubble at a time;
it goes back when the pointer leaves the bubble, on a click (the click goes to the viewer as before; in the Translator role it selects a region), on the wheel, a key or Esc, and when the page changes.
It shows when you rest the pointer, not on a click (since clicks on the page belong to the viewer, and in the Translator role to selecting the regions).
The panel's translation is twice `readable_font_size` (22 pixels by default), and never smaller than on the page.
With "Panel text size" in Tools > Settings... (`panel_font_size`, in points; 0, the default, keeps that automatic size) it is the size you set, which grows with the window's text size and the monitor's scaling as the rest of the window's text does, up to about 8 % of the screen's height;
a panel that would not fit on the screen has its text made smaller until it does. The panel never covers the bubble and takes no focus,
so even over a full-screen viewer, keys reach the viewer. The enlargement of the original, and the original lettering put back in place, are cut out of the page in memory and never written to disk.

**View > Show original and the bubble zoom setting**: with the translation on the page, View > Show original shows the whole page as the viewer does
(meanwhile the bubble itself shows nothing different; the panel still opens). With the original on the page, Show original is greyed in the Reader role
and its key does nothing (the full screen turns Show original off as it starts). "Enlarge the bubble under the pointer" in Tools > Settings...
(`bubble_zoom`) off shows nothing under the pointer while the translation is on the page. With the original on the page the pointer is the way to the translation,
so the setting does not count there.

**In the Translator role**: the page is always the translated page with the regions' frames, in the window and on the full screen, whatever "On the page" says
(the original on the page is a choice of the Reader role; View > Show original works as before).
Resting the pointer on a translated bubble shows its original in the way "Under the pointer" chooses, with the same waits and the same `bubble_zoom`.
The pointer is still the Translator's (a press selects; a drag moves, resizes, turns or draws a new region; a double click opens the editor),
so nothing shows while a button is down, while you drag or draw a rectangle, on a handle of the selected region (a corner, a side, the round handle),
or while the region editor or a dialog that holds the window is open (inside the selected region it does show).
What shows goes on a press (and the press selects or drags as ever), on the wheel, a key or Esc.
Esc takes it away first; the next Esc clears the selection as before.
The panel never covers the bubble, nor the selected region's frame and handles while there is room for it on a side.
The original lettering that "The bubble itself" puts back lies under the regions' frames, numbers, flags and the selection, changes none of them and is no edit (there is nothing to undo).
It goes back to the translation the moment the pointer leaves or a press comes.

**The bubble's Japanese as text, and copying**: in the window and on the full screen, in either role, you can do this with the bubble under the pointer
(in every combination, and over a full-screen viewer too; in the Translator role, not while a button is down or the region editor or a dialog is open):

* F2: opens the bubble's panel pinned, with its Japanese as text you can select, and the buttons "Copy the Japanese", "Copy the translation" and "Close".
  It stays while the pointer moves to it, and closes with F2 again, Close, Esc, a click on the page, the wheel, and when the page changes.
  With "The bubble itself" chosen, this is the panel there is, opened with F2.
  With the original on the page, the pinned panel opens with the Japanese alone and a "Show the translation" button, so that you read the Japanese first:
  F2 again (or the button) shows the translation, and F2 after that closes the panel. A panel pinned on another bubble holds its translation back again.
* Shift+F2: copies the bubble's Japanese to the clipboard (the part selected in the pinned panel, if any).
* Ctrl+F2: copies the bubble's translation (without the lettering's marks), also while the panel holds it back.
* F3 / Shift+F3: opens the same pinned panel on the next / previous bubble of the page in reading order (from the pinned one, else from the bubble under the pointer, else from the first / last).
  At the first or the last bubble the panel stays and the status line says so. With "The bubble itself" chosen, it is this panel too.

Tools > Settings... > Shortcuts changes the keys. For a page read in this session the Japanese is in memory. A page shown from the cache has none
(the cache keeps no Japanese), so the first time it is asked for, the bubble's part of the capture in memory is read again (as translator mode's "Read the Japanese" does),
and meanwhile "Reading the Japanese..." shows. The Japanese read is kept in memory with the page only, never written to disk or to a log.
TASlation writes the clipboard only when you copy. A line of the book you copied stays on the clipboard until you copy something else, and other programs can read it there.
Over a full-screen viewer these keys are TASlation's only while the pointer is on TASlation's page or a panel is pinned,
and the viewer's the rest of the time. No page key and no click is taken.

Without the pointer: F3 and Shift+F3 go from bubble to bubble, and while the pointer stays where it was, F2, Shift+F2 and Ctrl+F2 act on the pinned bubble (move the pointer onto a bubble and they act on that one again).
On a touch screen, where a tap goes to the viewer and nothing rests on the page, press and hold a bubble (about 0.6 seconds, without moving) to pin its panel; that touch is not passed to the viewer, and a short tap goes to the viewer as before.
Windows turns a touch held still into a right click while its "press and hold" setting is on, so a right click on a bubble pins its panel too.
Pinning by a press held still or a right click is the Reader role's only: in the Translator role a press held is the start of a drag, and a right click only closes a panel that shows.

### Starting a book: the setup and the book's name

Each page is translated when you open it (what "Auto" and F5 do), with only the few pages just before it as context, and the pages you turn past go on being read and translated in the background ("Pages you turn past" above).

When something translating needs is missing (Ollama not running, the model or the OCR models not installed),
the banner above the page says what is missing and how to fix it, and checks again every 10 seconds until it is fixed.

**The buttons in the banner above the page.** Each line of the banner has a button when it is something TASlation can fix for you.

| The banner says | Button | Pressing it |
|---|---|---|
| The translation program (Ollama) is not running | Start translator again | Starts Ollama there and then, and checks the setup again |
| The translation model the target language needs is not installed | Download model | Asks whether to download it, showing its size (it asks even if you answered "Not now" before) |
| Several windows look like viewers / the viewer was closed | Choose viewer | Opens the "Viewer" list |
| The viewer's window is minimised | Show viewer | Restores the viewer to its size and places it right behind TASlation (no key is pressed, and the focus does not move) |
| The viewer stays black | Show viewer | Brings the viewer's window in front of the other windows. Click the book and reload it |
| TASlation covers the viewer completely | Move TASlation aside | Moves only TASlation's window, so that a little of the viewer shows |

If, at start, translation turns out to run on the processor (CPU) (judged by whether Ollama's log names a graphics card),
the banner shows once roughly how many seconds a page takes to translate. "Close" removes it for the rest of that session.

When the window's title gives the book no name, a small dialog asks for the book's name on its first page.
The cache and the series sheet are saved under this name. Some viewers read in a browser have a tab title that is only the viewer's name, whatever book is open,
and with such a title it always asks (a viewer's or a browser's name is never used as the book's name).
Which part of a title is the viewer's name is learned on this computer: when you choose a second book in the same viewer, or type the book's name without the viewer's part in the "Series" and "Vol." fields. From then on that part is left out of the book's name. For the first book the whole title may show in the "Series" field; correct the name there. A browser-based viewer whose tab shows only its own name asks for the book's name first, and your answer teaches it that the title names no book.
What is learned (the titles and program file names of the windows you chose as the viewer, and which parts of titles are a viewer's or a book's) is kept only in `~/.taslation/viewers.json` on this computer. It never goes into a cache export or a log, and it is never sent anywhere. Deleting the file only means choosing the viewer once more.
A book you have named once is recognised from its translated pages, whatever capture area you read it with, and its name is filled in. If several books look alike, the candidates are offered in the box's list,
and if it cannot tell, the name last given with the same viewer is filled in ("Last time with this viewer: ...").
Even after you resize the viewer's window, the book is recognised from its pages the next time you open it (if the two pages of a spread are both close to different pages of the same book, it is taken to be that book). Old caches are matched the way pages were cut out at the time, so they still work as they are.
Closing the dialog without a name reads nothing, and it asks again on the next page, since nothing can be kept without a name.

The pages you translate are also checked for the same character's name written more than one way in the translations ("竜司" split into "Ryuji" and "Ryūji", for example).
When a name is written in two ways, the banner says so quietly, with a "Review names..." button (no window opens, and each name is offered once a session; it also opens from "Names rendered in more than one way..." in the "Tools" menu).
Each name is listed with its spellings and how many lines use each; choose the spelling to keep, or type one in "Other:", and press "Apply": the lines with the other spellings are changed to it.
If "Keep it in the series sheet" is ticked (the default), it also goes into the character's rendering in the series sheet, and later translations use that spelling.
Nothing is changed until you press "Apply". Only the name itself is changed, and only in the lines whose Japanese has that name; the rest of the line, the review flags, the notes to the reader and the positions stay as they are.
"Take back" restores both the lines and the series sheet (in translator mode, Ctrl+Z can also take back the lines alone; pressing "Take back" after that restores the series sheet too).
The names are found by fixed rules; no model is used. Only names that carry an honorific such as "さん", "くん" or "様" in the Japanese (2 or more katakana, or 2 to 4 kanji) are considered,
and a name is shown only when the translations write it in two or more ways, each in separate lines, that look like spellings of the same name (missing a case is preferred to making a wrong suggestion).
It does not appear for translations in languages without capital letters (Chinese, Korean, Thai and so on).
The Japanese lines are only kept in memory while TASlation is open, and are written nowhere. So it covers only the lines of the pages translated in this session (at most some 3,000 lines, the oldest going first; a page shown from the cache has no Japanese to look at).

If the model returns nothing for 20 seconds, the badge at the top right says so.
While the TASlation window is open, the screen does not switch off and the computer does not sleep (because the viewer stops redrawing when the screen switches off).
It cannot prevent closing the lid, putting the computer to sleep by hand, or locking it. Closing the window puts this back as it was.

The translations an earlier version saved by reading a whole book first stay in the cache, and show as any page translated before.

### How the viewer is read

The viewer's screen is taken with Windows.Graphics.Capture. A window can be read even behind other windows; the picture taken is only the latest one,
in memory, and is not saved to disk. Where this is not available, it switches to PrintWindow automatically (`taslation doctor`
shows which one is in use). Drawing stops when the display switches off, so the display is kept on while the TASlation window is open.

When you choose the viewer, if its window is smaller than the monitor's work area, the window is enlarged once to fill the work area,
changing only its position and size. No key is pressed and the focus does not move (a maximised window is left as it is, and so is a window you made smaller afterwards).
When you choose another viewer or close TASlation, the window is put back if it still has the size TASlation gave it. For the case where TASlation ends without closing (a crash and the like),
the position and size before enlarging are kept in `ui.json` in the state folder, and at the next start, if the same window still has the enlarged size, it is put back.
The larger the viewer's window, the better it is read. When a page in the cache is shown, the status line says "Looking at the page..." rather than "Translating...".

Some viewers stop drawing while they are hidden. When you choose the viewer, and when the full screen starts, if the viewer is completely hidden by other windows,
TASlation asks it to redraw without pressing any key (the same request Windows makes when another window is moved away), checks whether it draws while still hidden,
and records that per viewer in `profiles.json`. Only a viewer that did not draw is brought to the front for a moment at each page when reading page by page
(with no key press and no change of focus), and put back in its place in the order at once. A viewer that is even partly visible goes on drawing, so it is not brought to the front.
Browsers follow a published rule: they stop drawing only when they are completely covered by an opaque window. So browsers are not checked. A viewer read in a browser does not draw the next page while it is behind, even when it gets the key, so each time a key you pressed in the TASlation window is passed on, the viewer is brought to the front for a moment, the key is pressed for real, and once it has drawn, it is put back in its place in the order.
The focus moves for that moment. If drawing stops, the banner says so: move the window aside.

### When the viewer stays black

A viewer read in a browser can get stuck on its loading screen, or stay black. When the capture area stays black, TASlation does the following. It never presses a key.

1. **Wait**: loading may just be slow, so it waits for `black_wait_s` (30 seconds by default). After about 8 seconds it says the viewer is "still loading".
   Meanwhile it only checks in memory, about once a second, whether a new frame has arrived (when capturing with PrintWindow, it captures once every 2 seconds).
2. **Tell you**: if it is still black, it tells you, once, to reload in the book's window. Click the book, then press that window's reload key
   (F5 in a browser). In the TASlation window, F5 is the translate key, so pressing it there does not reload.

TASlation goes on waiting, and when a page appears, it continues from the page shown at that moment. It never translates or caches a black screen. A page that really is all black cannot be told from a stalled loading screen, so it is treated the same way.

### Page keys

When you press a page key in the TASlation window, that key is passed on to the viewer once (one press, one key). TASlation never sends a key on its own to turn a page.
Manga viewers read from right to left, so the ← key is the next page; in image viewers and books written horizontally, the → key is the next page.
"Page > Page keys..." sets the next-page and previous-page keys for each viewer you choose.
When you press your usual next and previous keys in the TASlation window (the defaults set with "Apply to all viewers", or failing those the keys in `taslation.toml`; at first ← is next and → is previous),
they are passed on as the keys set for that viewer. For a viewer that goes to the next page with Page Down, for example, pressing ← once passes Page Down once
(the status line says so too). The keys set for the viewer themselves, and any other keys, are passed on as pressed. Only the kind of key changes;
the number of presses does not, and a key is passed on only when you press it. This way TASlation can pass keys even to a viewer that turns pages with Backspace or a letter key.
When TASlation sits over the viewer's full screen, keys reach the viewer directly, so press the viewer's keys.

* Choosing the preset "Right-to-left reading" (← next, → previous) or "Left-to-right reading" (→ next, ← previous) fills in all the keys
  at once. For a combination of your own, type the keys in the key boxes and apply them (named presets written in `profiles.json` can be used with `taslation keys`).
* To try the keys, close the dialog, then press your usual next and previous keys in the TASlation window. The dialog never presses the viewer's keys.
* "Apply to this viewer" writes to that viewer only; "Apply to all viewers" writes to every saved viewer and to the defaults for viewers
  not set up yet.

The keys are saved per viewer in `profiles.json` in the state folder. A viewer whose window title includes a file name, like an image viewer,
shares one setting by what comes after the last " - " of the title (the viewer's name). A window other than a browser whose title is only a file name ("000.jpg" and the like) or only a number shares one setting by its window
class name, so the keys and the capture area set while it showed "000.jpg" are used as they are for "001.jpg". The keys used are decided in this order: the viewer's setting,
the defaults from "Apply to all viewers", then `taslation.toml`. On the command line, `taslation keys list` /
`show --viewer TITLE` / `apply left-to-right --viewer TITLE` / `set --all --next Right --prev Left` do the same.

### The book's name: series and volume

A book's name is given in two fields, "Series" and "Volume" (in the toolbar, where the second is labelled "Vol.", in the dialog at the start of a book, and in the colophon's offer).
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
The role kept per book carries over after the rename. A series sheet that an earlier version kept under a whole name with a kanji volume
("第一巻" and the like) as its series is found and used too, and moves along when the book is renamed.

On the command line, `--series` and `--volume` name the book the same way. A name given with `--book` is split as one string by the same rules
and put in the one spelling (if translations were saved under an older spelling, they are read and written under that name).

### The colophon and renaming the book

Near the end of a volume, TASlation reads the colophon (title, volume, author, publisher, ISBN), saves it in the cache's header,
and offers the colophon's title as the book's name, once per book. The name is shown in the toolbar's "Series" and "Vol." fields, so you can correct it. Choose "Use" or "Keep".

When there are files under the book's current name (the name you typed first, or an old cache saved under the viewer's name), "Use" renames the book.
The translations in every language and the information attached to pages, and the series sheet too if the new name belongs to another series, are moved to the new name,
and the status line shows what was moved and how much.

If that series already has a series sheet (when you renamed an earlier volume to its full title, for example), this book's series sheet is merged into it.
What is added is taken in as it is. Where the two disagree (a term's rendering, a character's first-person pronoun, a policy in the style guide and so on),
the series' value and this book's value are shown side by side, one item at a time, before anything is moved,
and you choose "Keep the series'" or "Take this book's" (you can also choose for all at once). "Rename" renames the book following those answers;
with "Cancel" the name stays as it is, and the colophon's title is offered again next time. This table appears only in the translator role. In the reader role it does not ask, and merges keeping the series' value in every row.
If there is nothing to answer, it merges at once and shows how many entries were added, how many were taken from this book, and how many were kept as the series had them.

The series' defaults (see "Book settings...") follow too when the new name belongs to another series. If the new series has none yet, the old series' defaults are moved to it,
or copied when other volumes are still kept under the old series, so that those keep theirs. If the new series already has defaults of its own, they stay as they are, and so do the old series'.
A book that was following its series keeps the values that were in force for it: if the new series' defaults (or none, for a name without a volume) would give it others,
the values it took from the old series become its own, and it no longer follows a series.

Nothing else is overwritten. If translations or page information under the new name already exist, nothing is moved,
and the files in the way are shown.

### The window's language

At the first start, it asks which country you are in and the window's language (see "The notice at start"), and remembers them in `~/.taslation/notice.json` and
`~/.taslation/ui.json`. The language can be changed at any time in the "Language" menu,
and the country with "Legal notice..." in that menu (it is also in the "Help" menu). They can also be set with `--ui-language ja` or with
`ui_language` in the settings file.

There are 17 built-in languages: English, 日本語, Español, Português (Brasil), Français, Deutsch,
Italiano, Nederlands, Polski, Русский, Türkçe, Bahasa Indonesia, Tiếng Việt, 简体中文,
繁體中文, 한국어, ไทย. This is the language of the menus and messages, not of the translations. Translations can be into any of the 20 languages of the "To:" box.
"About TASlation" in the "Help" menu shows the version, the licence,
the folder where the cache, series sheets and settings are kept, and where the README and docs/THIRD_PARTY.md are.

### Translator mode

The window has two roles. As **Reader**, keys and clicks on the page go to the viewer. Switch to **Translator** with "Translator" in the toolbar,
and below the toolbar appear translator mode's tools (Reading order, Skip page, Translate again, Book settings, Series sheet, Review, My corrections, Lines to review, Find and replace, Text direction, Undo, Redo; all of them are only here) and
a line explaining the mouse actions and keys ("Click: select · drag: move · drag a handle: resize · drag the round handle: rotate (Shift: 15° steps) · double-click: edit · drag on empty space: add · Delete: drop · T: text direction · Ctrl+Z: undo · Ctrl+Y: redo · Tab: next region · Alt+arrow keys: move by 1 px"; the keys shown are those set in "Shortcuts" in "Settings", and actions whose key was removed are left out),
and the page can be edited.

* **Keyboard**: Tab on the page selects the next region in reading order, Shift+Tab the previous one (after the last comes the first again;
  the status bar shows which number it is). Alt+arrow keys move the selected region by 1 pixel, Alt+Shift+arrow keys by 10 pixels,
  and a moment after you let go of the keys, it is saved as one move (Ctrl+Z takes it back in one step). As Reader, Alt+arrow keys go on reaching the viewer as arrow keys, as before.
  Esc in the Series, Vol. or To: box gives the keys back to the page and does nothing else (it does not stop a process that is running).
* **Copying and pasting formatting**: as with a word processor's format painter, Ctrl+Shift+C on the selected region remembers its formatting (font, size, bold and italic,
  alignment, line and letter spacing, slant, text direction, text colour and outline), and selecting another region and pressing Ctrl+Shift+V gives it that formatting
  (Ctrl+Z takes it back in one step). The kind (speech, thought, shout and so on) is premise information the model is told when it translates, so it is not copied with the formatting.
  "Paste format on every region of this kind..." in the "Page" menu applies the copied formatting to every region of this book of the same kind as the selected region
  (it shows how many and asks first; the kinds are held by the book's premises, so it also applies to regions on pages not shown yet;
  when the kind is "(not set)", the regions of translated pages are the ones covered). Whatever page is shown, one Ctrl+Z takes back the whole of it.
  Ctrl+C remembers the selected region itself (frame and formatting), and Ctrl+V on another page with the same layout
  adds a region at the same place, then reads and translates it (it does not add one where there already is a region, or when the page's size differs).
  All the keys are gathered under "Keys" in "How to use", which "Help" > "Keys..." (Shift+F1) opens (the mouse actions are there too),
  and "How to use..." opens with F1. All the keys written here are the initial ones, and can be changed in "Shortcuts" in "Settings".
  Menu items and buttons also show the keys they currently have.

* **Regions**: every text region is shown with a frame (green: translated, orange: untranslated, blue: a region you marked yourself, red with "?": translated but flagged for review). The speaker,
  and "..." where a sentence continues, are shown too. Frames, the selection frame, handles, the rotation handle and the rectangle being dragged are drawn in two-colour lines, a dark line under the coloured one,
  so they show on white pages and black pages alike. Labels such as the speaker are placed, where there is room, where they do not cover a neighbouring region (above, below, then left or right).
  Draw a rectangle around text that was not detected, and it is read, translated
  and added to the page (later readings use it too). On the drawing, only the lettering inside it is erased and the drawing under it filled in (by the inpainting model where it runs, otherwise from the drawing around the strokes);
  in a bubble or on a flat box, the rectangle is wiped on its paper, and the outline and the drawing beyond it stay. Like shapes in office software, a region is selected with a click, moved by dragging,
  and resized with its handles, and it is read again only when the new frame covers a larger area. Drag the round handle that sticks out from the middle of the selected frame's top edge,
  and the frame rotates around its centre, as a shape in Word does, and is lettered again where you let go (with Shift held, in 15° steps;
  without it, it snaps straight within 3° either side of 0°; the range is up to 89° either way; Esc cancels the drag, and Ctrl+Z takes it back).
  Rotation is the same setting as "Slant" in the editor; a slanted frame is shown at that angle, and its handles sit on the slanted frame.
  A handle of a slanted frame widens or narrows the original (unslanted) frame on the side the handle faces on the page. Delete removes a region,
  and a removed region is remembered as "not text" on that page, so a false detection never comes back.
* **The original under the pointer**: resting the pointer on a translated bubble shows its original, as in the Reader role ("In the Translator role" in "The bubble under the pointer").
  Pressing, dragging, the handles and editing are as before, and nothing shows meanwhile.
* **Selecting several regions**: as with shapes in office software, Shift+click adds a region to the selection, and clicking it again removes it.
  Shift+drag draws a dotted rectangle and adds every region that lies entirely inside it to the selection (Shift on a selected region's handles or
  round handle resizes, and rotates in 15° steps, as before; dragging on empty space without Shift
  adds a region as before). With several selected, each frame is drawn without handles. Drag any of them or press Alt+arrow keys,
  and they move together (the whole group stops when one of them reaches the edge of the page); Delete removes them all, T switches the text direction of them all,
  and Ctrl+Shift+V pastes the formatting on them all. "Set kind..." and "Set text size..." in the "Page" menu set the kind and the text size ("Auto" goes back to the size that fits)
  of the selected regions (one or several). Each of these is one change that Ctrl+Z takes back,
  and taking it back leaves all the regions concerned selected again. Clicking one of the selected regions without moving it selects that region alone, Tab selects the next single region,
  and Esc clears the selection.
* **Areas ignored on every page**: for things that appear at the same place on every page and that you do not want translated, such as watermarks, page numbers or a band printed on every page, select the region and
  choose "Ignore this area on all pages of this book" in the "Page" menu: that place (the region's frame, slightly widened) is then ignored on every page of the book.
  When you remove a region at the same place as one you removed on another page, the same is asked after the removal is saved (a place you answered "Only this page" for
  is not asked about again until you close the window; removing a region you added yourself does not ask). A detection that falls almost entirely (70% or more of its area) inside such an area
  is treated as not found, and left as drawn. Regions you added yourself stay, even inside the area.
  An area set on a page of a spread applies to the pages on that side (right or left) and to pages shown one at a time; an area set on a page shown one at a time applies to every
  page; neither applies to pages of a very different shape (a spread made into a single image and the like). Adding one can be taken back with one Ctrl+Z,
  whatever page is shown. The translations inside the area stay in the cache, so taking it back brings them back as they were. All that is saved is the area's four numbers,
  the side of the spread and the page's aspect ratio.
* **Editing a region**: opens with a double-click (or Enter while a region is selected). The formatting fields are folded into the "Formatting" button when the region has no formatting of its own. You can change the **speaker** (chosen from the series sheet's names), the **kind** (Speech,
  Thought, Shout, Narration, Sound effect, Handwritten, Erase only), whether the **sentence continues in the next bubble**, the **hint for the model** (a pun, who is addressed),
  and the translation. Enter starts a new line (the lettering keeps that line break too), and Ctrl+Enter saves.
  PLaMo 3 Translate (the model of every target language but Brazilian Portuguese and Turkish, see "Choosing the model") follows a hint only sometimes (about half the time in a test), and the editor says so under it:
  it works best for how a name or a term is read and for who or how many are meant; names and terms that must always come out the same belong in the series sheet. Qwen3.5 4B and a model of your own are given the hint with the bubble.
  A hint can change the wording of its own line even where it does not need to, but it never reaches another line: the request that translates a bubble together with the next one as one sentence carries no hint, and "Ask again" asks the bubble alone, with its hint.
  With the kind set to "Erase only", the region's original lettering is only erased, and nothing is lettered there (as soon as you choose it, the page behind shows it erased).
  It is not sent for translation, and it is counted neither as flagged for review nor as untranslated. The earlier translation stays in the cache, so setting the kind back letters it again.
  The change can be taken back with Ctrl+Z.
  Where the original letters part of the bubble larger than the rest and that part was found in the translation ("Settings", `size_emphasis`), those words show larger in the translation's box.
  They follow your typing; an edit that touches them letters the bubble at one size again. "Set larger" and "One size" on the formatting bar set and clear them.
  "Ask again" looks for the part in the new answer too.
  At the top of the editor, the region as it originally looks is shown, cut out of the captured screen (an image in memory only, saved nowhere).
  A page shown from the cache has no Japanese (the cache keeps only translations), so "Read the Japanese" reads it again there and then;
  "Read as:" then appears, and "Ask again" can be used too (if you press "Ask again" without having read it, it reads first).
  Where the Japanese was misread, correct it in the "Read as:" field: "Ask again" translates your reading, and so does everything that reads that bubble again in this session
  ("Translate again", reading it again from the cache, moving it). Where nothing was read, the field appears after a reading, to type the Japanese in.
  Your reading stays in memory only and is never saved; "Save" keeps only the translation, and Ctrl+Z takes back the translation, not the reading.
  "Previous (Alt+↑)" and "Next (Alt+↓)" move to editing the region before or after in reading order (the keys can be changed in "Shortcuts"). If you changed something, it is saved before moving, as "Save" does
  (Ctrl+Z takes it back as one change); if you changed nothing, nothing is written.
  If you try to close it with Esc or the window's close button with changes made, it asks whether to discard them ("Keep editing" is the default).
  The "Cancel" button closes without asking.
* **Formatting bar**: the formatting bar above the translation works like a word processor's text box.
  It has "Bold" and "Italic" ("Auto" goes back to what the series sheet sets for the kind), **Font** (the fonts installed on this computer;
  a computer without that font uses the automatically chosen font; at the top of the list come the fonts you starred with the ☆ beside them, then the fonts used recently
  (the last 10); pressing ★ again removes the star; you can also move to it with Tab and press it with Space; only the font's family name is remembered,
  saved in this computer's ui.json), **Size** ("Auto" is the largest size that fits; a fixed size is not shrunk,
  and text that does not fit is cut off at the bubble's edge, which is shown), "Condense to fit" (automatic under 14 points),
  "Set larger" (the words selected in the translation are lettered larger than the rest, as many times larger as the original's larger part where it was measured, else 1.5 times; the box shows them larger) and "One size" (the whole translation at one size),
  align left, centre and right, and align top, middle and bottom, **Line spacing**, **Letter spacing**, **Slant** (the angle, anticlockwise; "Auto" keeps the original lettering's slant), **Text direction** (as in a Word text box: Auto, Horizontal, Rotate all text 90° (reads from the top down, the direction of an English book's spine), Rotate all text 270° (reads from the bottom up), and Stacked (vertical writing: the letters are stacked downward, and the columns run from right to left; the long-vowel mark "ー", dashes, "…" and brackets take their vertical forms, small kana and punctuation sit in their vertical positions, and Latin letters are stacked upright one at a time; horizontal-in-vertical (tate-chū-yoko) and ruby are not supported); combined with a slant, the text in the chosen direction is slanted together with its frame), **Text colour** and **Outline colour** (Auto, Black, White, Custom...; with Custom, you choose any colour in Windows' colour dialog, and clicking the colour swatch beside it lets you choose again; nothing is asked of the network), **Outline** (Auto, With outline, No outline), and "Reset formatting". "Auto" for the colours and the outline follows the colour and outline the series sheet set for that kind; if it set none, the text is black or white to suit the background, the outline is drawn only on art and screentone, and the outline colour is the opposite of the text's. Colours and outlines do not change the text's size or line breaks. "Copy format" (Ctrl+Shift+C) remembers the bar's formatting, and "Paste format" (Ctrl+Shift+V) puts it into the bar of another region's editor (confirmed with "Save"). In translator mode, pressing T on the selected region, or the "Text direction (T)" button, switches in the order Auto → rotated 90° → rotated 270° → stacked → Auto (Ctrl+Z takes it back). After a change,
  the page behind is lettered again a moment later. The formatting is saved with the book's page information.
* **Into the series sheet**: when your edit replaces a name or term that the series sheet renders differently, it asks whether to make yours the series sheet's rendering,
  and replaces it on the pages already translated as well (replacing the translations is one change that Ctrl+Z takes back; the series sheet's rendering does not go back).
* "Reading order": when the order decided automatically is wrong, click the regions in reading order to set it (split sentences, and who answers whom, are decided by this order).
  In translator mode, each region's place in the reading order is shown in a small round badge beside its frame (placed where it does not cover a neighbouring region or label;
  "Reading-order numbers" in the "View" menu turns it on and off, and the choice carries over to the next start; while you are clicking the order with "Reading order",
  the labels show the numbers, so the badges are not shown). To correct the place of a single region, select that region and, with "Place in reading order..." in the "Page" menu,
  enter which place it should have (with several selected, they are put at that place in their present order; the order of the other regions
  does not change; Ctrl+Z takes it back).
  "Skip page" marks a page with nothing to translate, such as an advertisement or the viewer's own panel,
  and "Translate again" (not using the cache) translates the page again with the current premises.
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
  ("Open settings file" in Tools > Settings...). Nothing is fetched from the network.
* "Undo" (Ctrl+Z) takes back the changes to the page on show, newest first (edits of translations and notes; moving, resizing, adding and removing regions (a change made to several regions at once
  counts as one); saved formatting; setting kinds and text sizes;
  "Skip page"; setting the reading order; "Translate again"),
  and "Redo" (Ctrl+Y) applies them again. Changes on other pages can be taken back when that page is shown again.
  Taking back "Translate again" brings back the page's earlier translations. A translate-again that ended without translating anything (a stop, for example) is not something to take back.
* "Find and replace..." (a translator-mode button) searches and replaces across all the translations of the current book in the current language
  (and, if you choose so under "Look in:", in the other volumes of its series too).
  Use it, for example, to correct a wrong character name throughout a volume at once. You can keep reading the book with the window open, and as you type, the matches
  are listed with their page numbers and the text around them (the match is between `«` and `»`; the page number is not the book's printed page number,
  but the order in which the page entered the cache). "Match case" and "Whole word" narrow the search. "Whole word" does not look for word boundaries next to
  scripts that put no spaces between words, such as Japanese, Chinese, Korean and Thai.
  Nothing is written until you press a replace button. "Replace selected" replaces only the matches selected in the list (Ctrl and Shift select several),
  and "Replace all" replaces every match (the list shows only the first 500, but the count and "Replace all" cover them all).
  The page on show is lettered again at once, and other pages show the new translations the next time they are shown.

  Only the translations change. Review flags, notes to the reader, draft marks, marks of unfinished pages and the bubbles' positions stay as they are.
  A part of a translation set larger moves with its words; where the replacement touches it, that bubble is lettered at one size.
  The lines were not looked at and corrected one by one, so, unlike an edit of a region, it does not clear review flags. A bubble whose translation would become empty is not replaced, and this is said.
  A replacement is one change as a whole: while it is the book's latest change, Ctrl+Z takes it back on all pages at once, whatever page is shown,
  and Ctrl+Y applies it again (in the Find and replace window as well). If you edit another page after it, that edit must be taken back first.
  A bubble whose content changed because it was translated again is no longer part of what is taken back.

  The series sheet does not change on its own. Only when the words replaced with "Replace all" were a rendering in the series sheet does it ask, once, as for a region edit,
  whether to use the new rendering. When only some lines were replaced, it does not ask. Undoing does not take back a change to the series sheet.
  Nothing can be replaced while a page is being processed. Press it again once that is over.

  "Look in:" says where "Replace all" replaces: "This book" (what the window starts with every time it opens) or "All volumes of the series".
  With the second, the list still shows this book, and "Replace all" first counts the matches in the other volumes of the book's series kept in the same language
  (found as `taslation glossary apply` finds them: by the series name), shows the count volume by volume, and asks.
  "Replace in all volumes" replaces in this book as "Replace all" does (Ctrl+Z takes it back) and in each other volume, where the change is saved at once
  and Ctrl+Z does not reach it. Before a volume is changed, a copy of its file as it was is kept beside it (`<file>.before-replace.<date>.json`, protected as the cache is);
  to take the change back, replace the other way round in all volumes, or put that copy back in place of the file. The lines replaced there are marked as your corrections too.
  "Replace selected" always stays in this book.
* "Book settings..." saves the detection and OCR values that suit this book (thresholds, text-block detection, sound effects) and this book's lettering size
  ("Lettering size" and "Largest size"; "As in Settings" and an empty box mean the values in "Tools > Settings..."), together with the book's premises,
  without changing your own settings. "Apply to this book" re-sets the page on show from the cache (nothing is translated again).
  "Reading direction" says which page of a two-page spread and which bubble come first: "Right to left (Japanese books)", the default,
  or "Left to right"; "Clear all" leaves it as it is.
  "Clear all" shows how many settings will go and asks before clearing them (the default button is "Keep them"),
  and leaves the window open. Meanwhile "Undo" brings the cleared settings back. Below that, the areas ignored on every page of this book are listed
  with the pages they apply to (All pages, Right-hand pages, Left-hand pages) and their position (in % of the page's width and height), and "Remove area" (or the Delete key in the list)
  removes the selected area at once (text is looked for there again). "Undo" takes back the last thing done in this window (Clear all, or removing an area).

  The volumes of a series can share these values. "Save as the series' default" applies the values shown to this book and keeps them (the choices, the sizes, the other settings and the reading direction) as its series' defaults;
  "Use these areas for the series", beside the areas (and in the "Page" menu, greyed while the book has no series), keeps the areas listed as the series' areas. A volume opened for the first time (nothing of its own kept yet) starts from its series' defaults and follows them wherever it has no value of its own:
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
  "Undo" at the bottom takes back the last change made in this window (an addition, update, removal or saved style guide), one step.
  When you change the rendering or spelling of a term or character (also when you bring one back with "Undo"), it shows how many translated lines use the old rendering,
  and asks whether to give them the new one. "Apply to the {n} line(s)" replaces it, word by word, in that book's translations in that language in the cache (changing "Miyu"
  leaves "Miyuki" alone; the page on show is lettered again at once). The replacement is one change as a whole, and Ctrl+Z takes it back, as with Find and replace.
  If a page is being processed, it asks once that is over.
  When other volumes of the series kept in the same language use the old rendering too, the question lists them with their lines, and its box
  "All volumes of the series" (unticked at first) gives them the new one as well; when only other volumes use it, it asks about them alone.
  The other volumes are saved at once and Ctrl+Z does not reach them; a copy of each file as it was is kept beside it (`<file>.before-replace.<date>.json`).
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

A Chrome (or Edge) window is recognised by its title, but a browser window's title is that of its active tab.
If the book's tab shares a window with other tabs, TASlation can see the book only while that tab is in front.

The fix is needed only once. Drag the reader's tab out of the window (or right-click the tab and choose "Move tab to new window")
to give it a window of its own. Leave that window open behind your other work. It may be hidden, but do not minimise it.
A desktop viewer is an app of its own, so it does not need this. A window other than a browser, such as an image viewer, is treated as the book as long as the same window stays open, even if its title (a file name or page number)
changes with every page you turn, and a change of title does not make it wait. Only when the window is hidden or minimised
does the status line say so and wait for it to come back.

If the window shows another tab even so, Auto notices the change of title, says so on the status line and waits for the book to come back.
It never reads the wrong page.

When the reading reaches the end of the volume, some viewers show an end-of-book panel (ratings, the next volume). The arrow keys may not get you out of this panel,
so then close it with "x" and go back to the first page. Text that looks like part of the viewer itself or of a colophon page (horizontal lines of Latin letters and numbers:
prices, addresses, ratings, dates of publication, the record of where each chapter first ran) is taken as print, not dialogue, and left as it is, and so are the title and the author's name on a title page.
A chapter's label and the words of a contents page (第3話, 第十二章, 最終話, 番外編, 目次, あとがき and the like) are translated wherever they stand: set across, on a band, beside a page number,
and a contents list row by row. Japanese read surely beside digits or Latin letters (3年B組, a heading with a subtitle in Latin letters) is translated too; a subtitle on a line of its own in Latin letters
is left as it is. A paragraph set across (an explanation page, a foreword) is read and lettered as one, not in pieces.

### The translation cache and backups

The cache is in `~/.taslation/cache/<book>.json`,
one file per target language (the book's name comes from the viewer window's title and can be changed in the "Series" and "Vol." fields; books that give the same file name, such as "My:Book 1" and "My
Book 1", get `<book>-<hash>.json`). "Saved translations..." in the "Tools" menu
lists and deletes caches (the list shows each book as its series and volume, with its pages, bubbles, the file's size, language and last change,
and under it how many files, pages and bytes there are in all). A click on a heading sorts the list by that column, a second click the other way round;
at first it goes by series, volume and language. Ctrl+click and Shift+click choose several rows, Ctrl+A all of them. "Delete" moves only the files of the chosen rows' books, each in its row's language, to the Windows Recycle Bin
(the translations in other languages stay), after one question that names the book, or how many and which. The confirmation's default button is "Keep them", and the files can be restored from the Recycle Bin. When a file cannot be moved to the Recycle Bin
(on a drive without one, for example), it is not deleted, and this is said. On the command line, `taslation cache delete` deletes all languages, as before.
"Rename..." gives the one book chosen a new name in its Series and Volume fields; the rename then goes as the window's own does (the review first where the series sheets
say otherwise), its translations in every language, page information and series sheet moving along, and the list follows once it is done. A file holds the translations, the normalised shapes and positions of the bubbles, the page fingerprints and the notes to the reader (and, for a bubble with a part set larger, that part's place in its translation),
what the colophon says of the book (title, volume, author, publisher, ISBN) and the translations of short lines kept for reuse, each under a keyed hash of the line's Japanese, never the Japanese itself ("Reusing short lines"); it holds no page image.
Everything TASlation keeps is listed in "Help > How to use..." under "Your data".
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
When there are files that cannot be opened on this computer, the window says at its start how many and how to move the translations (only when the number changes).
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
before" in "Tools > Settings..."). The same cry, reply or name called out comes back page after page: reusing its
translation saves a request and keeps the line the same each time. It applies to lines of at most 10 characters, once
differences that change no reading are evened out (full-width and half-width forms, spaces, "……" and "...", "〜" and
"ー", "!?" and "！？！", a final "。"). A line whose sentence goes on in the next bubble or comes from the one before, and a
line with a hint for the model, are always translated. The speaker and the kind you gave a line in translator mode are
part of it: the same words said by someone else, or marked as a thought, are another line. Only translations made by
the same model into the same language are reused, and never those of another series. The series is the one the
series sheet goes by: the Series field, so a volume still kept under a name typed before the two fields ("Some Title
3巻") shares its lines with "Some Title 4".

* A translation you corrected in translator mode wins: later identical lines get your text. "Ask again" in the editor
  asks the model; its answer, once saved, counts as your correction here (not in "My corrections"). When a translation
  was reused from an earlier identical line, the editor says so. Ctrl+Z on a correction also takes back the line it kept.
* "Translate again" asks the model for every line but those you corrected (unless you
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

The target language is chosen in the "To:" box (or with `--language`, or the setting `target_language`).
The cache and the series sheet are saved per language, and the lettering switches to a font for that script. The model that translates is decided by the target language
(see "Choosing the model"). The quality depends on how good the model is in that language. Only translation into English has been measured (see "Choosing the model");
the models used now have not been measured in the other target languages.
Hindi and Bengali are shaped with HarfBuzz (the `uharfbuzz` package that install.cmd installs): conjuncts, vowel signs
and the reph are set as the font forms them. Where that package is missing, their letters are drawn one by one, and
the banner above the page says so (run install.cmd again). Everything else is set correctly too, including Arabic and
Hebrew, which are written from right to left; only Hebrew's vowel points, which translations seldom have, may sit on
the letter next to theirs.

### Command line

```
taslation                      open the TASlation window (the same as `taslation gui`)
taslation gui --window "<title>" --on-top   open with the viewer chosen, and keep the window over the viewer (Auto on; --no-auto starts with it off)
taslation gui --full-screen    start on the full screen (the page alone, in the role chosen) once the viewer is chosen
taslation windows              list the windows that can be captured
taslation doctor               check the models, fonts, Ollama, the network guard, and whether each stage runs on the GPU or the CPU
taslation notice [--country CODE] [--reset]   show the legal notice of the start for a country (ISO code); --reset shows it again at the next start
taslation cache export <book> --out FILE [--force] [--confirm]   export the book's translations, page information, series sheet and series' defaults to a file encrypted with your own passphrase (a backup for yourself, or for another computer of yours); --force overwrites an existing FILE
taslation cache export --series NAME | --all --out FILE   every cached volume of a series in the target language, or every book, in one file
taslation cache import FILE [--list] [--book NAME] [--take-file] [--replace] [--confirm]   read that file back (merged with what is there, your corrections, page information, series' defaults and sheet values kept unless --take-file; --replace replaces the cache); --list only lists the books it holds
taslation read --window "<title>" --book "My Book 1"   capture once, translate and preview
    (it takes the book's name from the viewer window's title; a title with no book's name in it, such as
     "<viewer> - Google Chrome" with only the viewer's name, is refused, so give --book NAME)
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
taslation gui --role translator   start as translator
taslation audit page.png       run the processing and show every network connection made (and at the end, whether any saved file is left unprotected)
taslation annotations list [--json]          list the books that have a notes file on this PC (pages, frames, memos, skipped pages, reading orders; no text is shown)
```

Global options: `--model NAME` (the default is the setting `ollama_model = "auto"`: the target language decides the model; see "Choosing the model"), `--ollama-url http://127.0.0.1:11434`,
`--margins L,T,R,B`, `--font path.ttf`, `--uppercase`, `--language German`,
`--models-dir DIR`, `--config taslation.toml`.

`--window` is matched against, in this order: the window's whole title; in a browser, the tab's whole title; the beginning of the tab's title; part of a tab title that looks like a viewer;
part of the window's title. When several windows match, it does not guess: it shows the candidates and exits (exit code 2).
Give a somewhat longer title.

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
Answer with a number from the window's list or with the English name (a language not in the list can also be chosen by name, if PLaMo or Qwen can write it). Enter means
the language last chosen in the window, otherwise the language that matches this PC's display language, otherwise English. If `taslation.toml` has `target_language`,
that is used without asking. If you choose a language other than the one shown, the window also starts with that language (it is written to `ui.json`).
install.cmd's questions are shown in Japanese if Windows' display language is Japanese (the translations are in `installer-texts.json`, and other languages can be added;
a language without a translation gets English).
When you choose a language in "To:" that needs the other model, the window offers to download that model (showing its size) and to remove the one no longer needed.
TASlation installs only one translation model at a time. For a model TASlation did not install (a `qwen3.5:4b` you had installed yourself, for example),
it asks separately whether to remove it, and keeps it by default. The first time PLaMo is installed, it first asks for your agreement to its licence (the PLaMo Community License as revised on November 9, 2026;
the main points are in `docs/THIRD_PARTY.md`). A PLaMo installed after agreeing to the earlier text goes on working as it is; agreement to the revised text is asked the next time PLaMo is installed.
When the publisher's server refused the download or no longer has the file, trying again will not help, so it tells you to update TASlation or to see the project's issues page.
While it lies over the book and on the full screen, it does not ask; it asks when you are back in the window.
On the command line, `--language` asks the same, and `python setup_models.py --translator-for "Turkish"` installs it too.
When `ollama_model` names a model of your own, nothing is offered.
When PLaMo is not installed but Qwen is, it translates with Qwen meanwhile, and the banner above the page says so.
When the model the target language needs is not installed and there is nothing to stand in for it, the banner says that model is not installed. In both cases,
"Download model" in the banner installs it there and then, without running install.cmd again.
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

The settings you change often can be changed in the window under "Tools > Settings...": the smallest and largest lettering size; the size below which a translation is put on the list for a second look (Review);
the lettering size (80 to 200 %; 100 % keeps the largest size that fits the bubble, and 90 % sets every translation a tenth smaller;
above 100 %, nothing goes past the bubble or the largest size, and only translations that were held back to keep sizes even on the page get larger;
in the settings file it is `text_scale`, and a book's own value is in translator mode's "Book settings..."); whether to letter in capitals; whether to set slanted lettering at the same slant; the size of the window's text; the window's colours (light, dark, or as Windows is set); whether to stay always on top;
and whether to use the optional page models (the layout model and the inpainting). The settings of other features (the enlarged view of the bubble under the pointer, reusing the translation of a short line seen before, setting larger what the original sets larger) are listed here too.
"Set larger what the original sets larger" (`size_emphasis`, on by default): where the original letters part of a bubble larger than the rest (its characters are measured as they are read: a part at least 1.25 times the size of the rest, in whole lines),
that part is looked for in the translation once the page's translations are final, and no word of the translation changes. First the Japanese part is translated alone and looked for in the translation;
where it is not found, the bubble's line is asked once more with the part marked, and the answer only points at the words in the translation (kept only where their share of the translation fits the Japanese part's share and the part's own translation bears them out).
These are one or two short requests beside the page's, only for such a bubble (on the test volume about one bubble in ten pages, and about half a second for each such bubble). Measured with stand-in parts on a test set, the words it found were the right ones about 11 times in 12, and it found some for about half of the parts.
The part found is lettered larger (never more times larger than in the original, and at most twice the size; the rest never smaller than the readable size `readable_font_size`, nor than four fifths of the size the whole translation gets at one size). Where the bubble cannot hold both sizes so, the part is set less larger first, and under 1.15 times the rest the bubble is lettered at one size; where nothing is found, the bubble is lettered as before.
The translation cache keeps the part as its place in the translation (no Japanese), so a page from the cache asks nothing. With the setting off, every translation is lettered at one size. The hover panel and copying keep the plain text.
Under the rows for the bubble under the pointer are "Panel text size" (`panel_font_size`: 0, automatic, or 6 to 72 points) and "Delay under the pointer" (`hover_delay_ms`: 0 to 3000 milliseconds, 450 by default); a number out of these bounds is not saved.
For the inpainting (erasing lettering on the drawing with LaMa and filling in the drawing), choose "Not used", "Only with a GPU" or "Always, also on the CPU". The default is "Only with a GPU":
it is used only on a computer where the model is installed and there is a GPU TASlation can use (an NVIDIA GPU with CUDA, one that PyTorch can use with CUDA).
On other computers, erasing works as with "Not used", and the model is not even loaded (the setting's row then says so).
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
The size of the window's text changes when you save, but it reaches every part of the window only after a restart.
The window's colours are "As Windows is set" (the default: the app mode in Windows' colour settings, looked at when TASlation starts and whenever its window comes to the front), "Light" (Windows' own look, as before) or "Dark"
(dark grounds with light text in the window, its dialogs and their title bars; the menu bar keeps Windows' colours). They change as soon as you save.
The page and the frames drawn on it keep their own colours in either. While Windows' high contrast is on, TASlation uses Windows' colours whatever this setting says (the row says so).
In the settings file it is `theme` (`"system"`, `"light"` or `"dark"`).

"Open settings file" opens `taslation.toml`, with every setting in it, in a text editor. If there is no file, it first makes one from `taslation.toml.example`.
In the file it makes, every setting is a description with `#` at the start of the line, and removing the `#` turns that setting on (no default value is written in, so if a later version changes a default, you get the new default).
It is made where the settings are read from (the file that was read, or else `taslation.toml` in the state folder; the state folder survives updates).
Updating with `update.cmd` does not overwrite `taslation.toml` in the TASlation folder (docs/INSTALL.md, "Updating").
Settings changed in the file take effect from the next start.

The "Shortcuts" page of "Settings" changes the window's keys. Choose an action in the list (translating the page on show, full screen, Undo, Redo,
menu commands, translator mode's tools and the keys on the page (next and previous region, moving a region by 1 pixel, copying and pasting formatting and regions),
"Previous" and "Next" in the region editor, and so on), press "Change key...", then press the new key (Esc cancels).
"No key" removes the key, "Default" puts that action's key back to the initial one, and "Reset all" puts all the keys back to the initial ones.
A key of another action, the page keys passed on to the viewer (the arrows, PageUp, PageDown, Home, End, Space; with modifiers too), Esc, Tab, F10 and Alt+F4 cannot be used
(Tab and Shift+Tab, Alt+arrow keys, and Ctrl+C / Ctrl+V on the page can be used for an action only when they are that action's keys from the start).
Keys used across the whole window, and keys also used in the region editor ("Previous", "Next", copying and pasting formatting), must be combined with Ctrl or Alt, or be F keys
(a key on its own would stop you typing that character in text boxes). Actions on the page and actions only in the region editor work in different places, so they may share a key (Alt+↑ / Alt+↓ do).
Keys used on the page (editing, removing and text direction of frames, and translator mode's tools) may be single keys. The keys of translator mode's tools work only in the translator role.
"Save" saves the keys in `shortcuts.json` in the state folder (only the keys that differ from the initial ones), and they take effect at once. The menus and toolbar buttons, translator mode's buttons and explanation, "Previous" and "Next" in the region editor,
and "Keys" in "Help > How to use..." ("Help > Keys...") show the changed keys too.
Esc, the page keys and translator mode's mouse actions are only shown in grey and cannot be changed here (the page keys are set in "Page > Page keys..."). Over a full-screen viewer, F5, F11 and Esc stay the original keys.

The "System" page of "Settings" shows, for each stage of processing a page (finding the text, reading the text, translation, erasing and lettering), where it runs ("GPU (the GPU's name)" or "CPU") and how many seconds a page took.
For detection, the classical detection runs on the CPU, and when the layout model is used, that model runs on the GPU. The OCR runs on the CPU, or two of its three readers on the GPU where it has room for them (`ocr_runs_on`, below), and the row says which and why. Translation runs where Ollama loaded the model,
and when only part of it is in video memory, it shows something like "GPU and CPU (60 % on the GPU)" (if no model is loaded, it says so).
For erasing, the fill with the paper's colour runs on the CPU, and when the inpainting (LaMa) is used, the part on the drawing runs on the GPU (on the CPU with "Always, also on the CPU" and no GPU). Only NVIDIA GPUs with CUDA are counted as GPUs,
and it neither loads a model nor starts Ollama to find out. The seconds are the average of the last 20 pages lettered, saved in `timings.json` in the state folder when the window closes (numbers only; nothing of the pages' content).
"Look again" refreshes it. `taslation doctor` prints the same as "Where each stage runs:". Below, it says how many short lines this session reused without asking the model ("Reusing short lines"; counts only).
Under that, "Translation model's layers on the GPU" (`ollama_num_gpu`) decides how much of the translation model Ollama puts on the GPU, for both translators (PLaMo and Qwen).
Empty (the default) leaves it to Ollama, and the requests are exactly as before. `0` runs it on the processor only and leaves the GPU free (translating several times slower); a number puts that many of the model's layers on the GPU and the rest on the processor.
It is sent as the `num_gpu` option of Ollama's requests. Once saved, the next request uses it (a model already loaded may take a moment to be loaded again for it).
With a number of layers set, a model split between the GPU and the processor is neither loaded again nor reported (it was asked for). Anything but empty or a whole number from 0 to 999 is not saved.
Under that, "OCR runs on" (`ocr_runs_on`) chooses where the OCR readers run: "The GPU when it has room" (the default), "The processor (CPU)" or "The GPU" (see below).
Where they run now, and why, is in the OCR row above. Once saved, it applies from the next page.
Last, "Translator's window cache" (`ollama_window_cache`) decides whether the Ollama TASlation starts keeps the cache of the translation model's whole window:
"On, unless the OCR then leaves the GPU" (the default), "Off" or "Always on" (see below). It applies from the next start of Ollama; the translation's row above
says whether the Ollama running now has it ("Started by TASlation with the window cache", or without it, and why).
Under it, the box "Look for a new version once a day when TASlation starts" (`update_check`: `"off"`, the default, or `"daily"`; the installer asks once) makes TASlation, at a start a day or more after the last look,
30 seconds or more after the window is ready and while no page is read or translated, run a program of its own, `check_update.py`, which asks GitHub for the first 16 KB of `CHANGELOG.md`.
A newer version is named in the Help menu's "Check for updates..." item and in one line at the bottom of the window (no dialog). When it could not ask, it says nothing. It applies from the next start.
Help → "Check for updates..." asks when you choose it, whether the box is on or off; chosen again within a minute of an answer, it shows that answer again and asks nothing (after "could not ask" it asks again at once). It shows this version and the new one with their dates and what changed; "Update now" closes TASlation,
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
next_page_key = "Left"       # key that shows the next page in your viewer
erase_mode = "fill"          # "fill": the bubble's own paper, flat or along its shading, within its outline;
                             # "inpaint": the same way, inpainted; "classic": the erase before 2026-10-30, byte for byte
art_erase = "auto"           # with "fill", lettering on the drawing is inpainted by LaMa once installed: "auto" only where PyTorch has a CUDA GPU (else as "off"), "lama" also on the CPU, "off"
detect_model = "auto"        # the layout model first, the classical detectors add what it missed: "auto" (where art_erase runs), "on", "off" (the default of earlier versions)
ollama_keep_alive = "5m"     # how long Ollama keeps the model after a request: "2h", "90s", seconds; "-1" never
                             # unloads, "0" unloads after every request
ollama_num_gpu = ""          # the model's layers on the GPU: "" Ollama decides, "0" the processor only, or a number
load_model_at_start = true   # the window loads the translation model at start, beside the OCR models; false: the first line to translate does
ollama_window_cache = "auto" # the Ollama TASlation starts: the cache of the model's whole window, unless the OCR readers would then leave the GPU; "off"; "on"
ocr_threads = 0              # CPU threads for the OCR model (0 = torch's default, one per core); while
                             # other programs keep the CPU busy, half the cores can be faster
ocr_runs_on = "auto"         # "auto": two of the OCR readers on the GPU only when it has room beside the translator and the page models; "cpu"; "gpu"
font_path = ""               # auto: the series sheet's font where installed, then models/fonts per script, then system fonts
reuse_lines = true           # a short line translated before in the book or its series gets that translation again
hover_shows = "original"     # the Reader role: the translation on the page ("original" under the
                             # pointer), or the page as the viewer shows it ("translation" under the pointer)
hover_reveal = "panel"       # ... shown in a panel beside the bubble, or "in_place": in the bubble itself
side_indicator = "column"    # the pages turned past beside the page: "column" where it fits, "rail", "off"
bubble_zoom = true           # false: nothing under the pointer while the translation is on the page
panel_font_size = 0          # the panel's text in points (6-72, following ui_scale and the monitor); 0: automatic
hover_delay_ms = 450         # the wait before a bubble under the pointer shows its other side (0-3000; 0: at once)
update_check = "off"         # "daily": at the start, look for a new version at most once a day (check_update.py asks GitHub); "off": only Help > Check for updates...
```

The size of the window's text can be changed with `ui_scale` (1.0 follows Windows' scaling; 0.5 to 3.0).
At start it is multiplied by the scaling of the monitor the window is on, and when you move the window to a monitor with different scaling, the text size changes to suit that monitor.
Parts drawn in pixels (the page and so on) keep their original size.

Every key is a field of `taslation/config.py:Settings`, and
`taslation.toml.example` lists all of them with their defaults. Settings that were removed (`review_pass`, `series_notes`,
`notes_pages_per_request`, `revision_flag_distance`, `revision_changes_only`, `ollama_prompt_style` and others) may remain in the settings file: it is still read as before, and they do nothing.
A key this version does not know (a misspelling, or a setting of a newer version) does not stop the start. That key is skipped, and the window names it once (without showing its value).
On the command line, it is shown as a warning every time. The old-named `~/.selftrans` folder (and the even older
`~/.cleantrans`) is moved to `~/.taslation` at the first start, and `SELFTRANS_*` environment variables
are still read when there is no `TASLATION_*`.

### The OCR models and their licence

The lettering on the page is read by three OCR models (about 700 MB in all). manga-ocr-charspot-small finds and reads the characters one by one;
it is strong on long lines, but it also tries to read something from drawings with no text. So TASlation first checks this model's confidence
(the product of the mean likelihood of character centres and the mean certainty of telling the characters apart; `ocr_min_confidence`, 0.65 by default),
that the text is at most three times the page's usual character size, and that it has 2 characters or more; what fails is treated as not text.
That is why a line of a single character is skipped. In that case, add the region by hand in translator mode. A region added by hand
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
(because an installation from the window leaves nothing behind); only `install.cmd`, which tries a failed download 3 times and then stops, keeps it, so that its next attempt or run goes on from there. A file the server refused or no longer has (HTTP 401, 403, 404, 410) is not fetched again,
and the script ends with exit code 5 (running it again would not help, so it tells you to update TASlation or to see the project's issues page). When winget installs Python and Ollama, your Y to the question is passed on to winget
as agreement to its terms of use (`--accept-source-agreements --accept-package-agreements`; this is said before the question).

If an earlier installation has only manga-ocr-charspot-small, TASlation works with that model alone. The status line says so in one line,
and it is not an error. Running `install.cmd` installs the other two.

On the CPU, the OCR models share the `ocr_threads` setting. When the CPU is busy with
other work, setting `ocr_threads` to half the number of cores can make it faster.
With an NVIDIA GPU, `ocr_runs_on` (`"auto"` by default) puts manga-ocr-charspot-small and manga-ocr-nar-small on the GPU, but only when it has room for them at TASlation's peak:
the translation model whole in video memory, LaMa and the layout model when they are used (LaMa needs more on a screen taller than 1440 pixels, where the lettering is larger in pixels), PyTorch's own memory, and what other programs hold now, with 1 GB left over.
A card of less than 5 GB is never used for them, and the larger translation model (Qwen3.5 4B) leaves no room on a 6 GB card. The third model reads only a few lines a page and stays on the CPU.
TASlation decides when the OCR models load, again after the GPU memory was let go ("Tools > Release the model now", and before Ollama loads its model when the room is no longer there), and when a setting it depends on changes.
While Ollama loads its model, the two stay on the GPU as long as the room is still there at that moment; with `"gpu"` they go back to the CPU for the load, as before.
It never decides while the translation model loads or answers, but at the first line read after that (at start, after the translation model's load when that is still under way).
While the translation model answers (the next page of a spread is read meanwhile, for one), the two read on the CPU as well: on the GPU they would wait for the model's computing, 0.7 s a line against 0.13 s on the CPU.
If the GPU fails, that line is read on the CPU. When its memory ran out, the OCR stays on the CPU until the GPU memory is next let go (before the translation model's next load, or "Tools > Release the model now"), and TASlation then decides again; after another CUDA error it stays on the CPU until the window closes. The layout model and LaMa do the same when the GPU's memory runs out: they go on on the CPU until it is next let go, and the page comes out as usual. The readings are the same on both.
`"cpu"` keeps the OCR on the CPU; `"gpu"` puts the two on the GPU wherever there is one, without looking at the room. The "System" page says where they are and why.

Ollama's model is put in GPU memory only while it is needed. The window loads it at start, while the OCR models load (`load_model_at_start = true`, the default;
"Load the translation model at start" on the System page of "Tools > Settings..."), so the first page to translate does not wait for it. Nothing is shown for this load,
and when Ollama is not running or the model is not installed it does nothing (the first page that needs the model says what is wrong, as before).
With the setting off, and for the `taslation` commands, the model is loaded when a line that needs translating comes up
(this takes a few seconds and shows in the status). It is not loaded for a page whose translations are in the cache. A loaded model stays for
`ollama_keep_alive` ("5m" by default) after the last request (or after the load at start), then is released automatically; with `ollama_keep_alive = "0"` nothing is loaded at start. While you read on through untranslated pages, each request
extends this, so it is not loaded again for every page. When the window closes, and at the end of a run of a `taslation` command, it is released at once.
While you read a page and nothing is being translated, the window has Ollama compute the beginning of the next page's first request (the series sheet and the earlier lines that request starts from) when Ollama does not hold it already, as after the earlier lines were cut back to the newest: the next untranslated page you turn to does not wait for it (a second or so).
It sends what that request would send and keeps nothing of the answer, so the requests are what they are without it; as when Ollama computes a request from another starting point, the model can word a line slightly otherwise (on a test set about one line in ten, with about the same score). It shows nothing, is done only while the model is loaded wholly on the graphics card, and stops as soon as you turn.
With `ollama_keep_alive = "-1"`, as before, it is loaded at start, before the OCR models, and never released.
When only part of the loaded model fits on the graphics card, it is loaded once more, and if it still does not fit, you are told so.
To free the GPU memory at once for a game or another program, use "Tools > Release the model now". It releases the translation model TASlation loaded or used this session
with a normal request of Ollama's API (`keep_alive` 0 for that model), and the page models (the layout model and LaMa) give their memory back too. It does so with `ollama_keep_alive = "-1"` as well.
A model another program loaded into the same Ollama is left alone, and Ollama itself is neither stopped nor started. OCR models on the GPU go back to the processor (the next page decides again where they read),
and what stays is the CUDA context PyTorch made once a page model or the OCR ran on the GPU (a few hundred MB), until the window closes.
The status line says what was released (the OCR's GPU memory too, when it held some). While a page is being translated and while a translation waits to start it releases nothing and says so in the status line.
If the model is still loading at start, it waits for that load and then releases it. The next line that needs translating loads the model again as usual.
Ollama runs only while TASlation uses it. When it translates and Ollama is not running, TASlation starts Ollama's server (`ollama serve`)
in a window that is never shown (never Ollama's app), and writes down that it did in `ollama-started.json` in the state folder
(the process's number, its program, when it started and the TASlation processes that use it; no text of a book). When you close the window, or when a `taslation` command that translated ends,
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
The setting "Translator's window cache" (`ollama_window_cache`) decides: with "On, unless the OCR then leaves the GPU" (the default) TASlation looks, each time it starts Ollama,
where the OCR readers would run (`ocr_runs_on`, below) with the model at its size without the window cache and with it. When only those 130 MB would move them to the processor,
it starts Ollama without the window cache and with `LLAMA_ARG_CACHE_RAM=0`; otherwise with both (on a computer without a usable GPU, or with the readers' place set to "The GPU" or "The processor", too).
"Off" always starts it with `LLAMA_ARG_CACHE_RAM=0` alone, as before; "Always on" always with both. What it chose is in the log, one line each time it starts Ollama,
and in the translation's row of the System page and of `taslation doctor`.
For an Ollama that was there before, `install.cmd` sets `LLAMA_ARG_CACHE_RAM=0` and, on a GPU of 6 GB or less, `OLLAMA_KV_CACHE_TYPE=q8_0` as environment variables of this Windows user
("Installation" in docs/INSTALL.md, which also says how to give your own Ollama the window cache). Because Windows keeps them, the Ollama TASlation starts on that computer gets `LLAMA_ARG_CACHE_RAM=0` too: the window cache without the 256 MB in RAM
(317 s instead of 296 s in the measurement above).

### Trying it without a book

`.\.venv\Scripts\python.exe tools\fake_viewer.py`, run in PowerShell in the folder that holds `install.cmd` (`python tools/fake_viewer.py` in a source checkout), opens a stand-in viewer that shows synthetic test pages (left arrow for the next page).
Choose the window titled "Fake Viewer" in TASlation, and you can check that capture, translation
and the passing of page keys all work.

### The error log and "Copy details"

The window records errors in `log.txt` in the state folder (when it grows large, it moves on to a next file, and the oldest are deleted, so it is about 1 MB in all).
It writes the environment at start (TASlation's version and date, Python, Tk, Windows, torch and the graphics card, Ollama's version), the names and values of settings changed from their defaults,
warnings, and errors with where they happened (the program's file name and line).
It does not write the page's text, OCR results, translations, book titles or window titles. For file locations, it writes only the state folder and the models folder, by name (`<state dir>` and the like),
and replaces the file names beyond them, and any other place, with `<path>`. Quotations in error messages, and characters that are not ASCII (Japanese and so on), are replaced with `…`.

"Copy details", in "Help > About TASlation" and on the screens that report an error, puts the same content (environment, changed settings, the last error) on the clipboard,
with the offline guard's state added (on or off, the address of Ollama on this computer it can reach, and how many connection attempts it blocked).
Paste it when you report a problem. It sends nothing anywhere. On the screen shown when it could not start, too, "Yes" copies it.

## Checking for yourself that it works offline

What the guard covers is TASlation's own process: the window and every `taslation` command. Before anything heavy is loaded, it makes every connection and every name lookup fail
unless it goes to this computer (loopback) on Ollama's port (11434 by default), and it tells the libraries that load models to stay offline.
It does not cover other programs. Ollama, which does the translating, is a program of its own: TASlation starts its server when it is not running (`ollama serve`, which TASlation stops again when it no longer uses it), and asks it, on 127.0.0.1, to load and release the translation model
and to translate the lines TASlation sends (`/api/generate`, `/api/chat`, `/api/ps`, `/api/tags`, `/api/version`); through the `ollama` command it lists the models
and removes one no longer needed when you agree (`ollama list`, `ollama rm`); and the downloader asks it to fetch or import a translation model
(`ollama pull`, `ollama create`). What else Ollama does is not under TASlation's control.
The downloader (`setup_models.py`, which the window and the command line run as a separate process when you agree to download a model) and the installer (`install.cmd`, which `update.cmd` also runs) run without the guard: they download.
The third is `check_update.py`, the program that looks for a new version: the window runs it as a process of its own when you choose Help → "Check for updates..." and, when you turned on the look at the start, once a day;
`update.cmd` runs it when it is asked to look for and download a new version. It runs without the guard too, and the TASlation package never imports it.
It asks GitHub's three hosts only: raw.githubusercontent.com for the first 16 KB of `CHANGELOG.md` (a Range header asks for that part only, so the request stays this small however long the file grows), and github.com for that version's ZIP, with an HTTPS GET
(the ZIP is tried up to three times when a download breaks off or what came is not a whole ZIP, every entry of it read back: a broken one is downloaded whole again); github.com sends the ZIP on to codeload.github.com. Sent on to any other address, it stops without asking there.
Besides the plain headers HTTP needs and that Range header, it sends only a fixed User-Agent (`TASlation-update-check`): no query string, no cookie, not the installed version, nothing about this computer or your books.
GitHub sees the IP address and the time, as any site you open does. It uses no proxy.
The window's own process connects nowhere for it, so what `taslation audit` lists of TASlation's own connections is the same with it.

With an installation made with `install.cmd`, TASlation's program is `.venv\Scripts\taslation.exe` in the folder that holds `install.cmd`; it is not on PATH.
Open PowerShell in that folder (with the folder open in File Explorer, type `powershell` in the address bar and press Enter), then:

1. `.\.venv\Scripts\taslation.exe doctor` prints, among its lines,
   `Network guard: ON (loopback:11434 only; 0 attempt(s) blocked)`.
   In the window, "Copy details" in "Help > About TASlation" copies the same state, as a line `Offline guard: on; ...`. The status bar shows something
   only when the guard has blocked an attempt to connect (it then stays until you close the window).
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
The window's icon is drawn by `tools/make_icon.py`
with Pillow alone and kept in `taslation/ui/assets/`. Run it again if you change the drawing.

## Limitations

* Where the inpainting runs (by default, a computer with an NVIDIA GPU that PyTorch can use with CUDA and both page models installed; "Layout model:" and "Inpainting:" in "Settings"), the layout model finds the lettering first and the classical image processing adds what it missed; elsewhere detection is classical image processing alone.
  The classical detection covers closed bubbles and boxes (bright and dark alike; dark bubbles, and light lettering on dark parts, are lettered in white)
  and dialogue and sound effects written straight on the page. For text written straight on the page, only the letters and the bright background around them are erased; the drawing next to them, fine lines and halftone dots included, is kept,
  and the translation is set in the space that is freed. When the drawing is close, the translation gets smaller, and small bits of drawing mistaken for parts of letters are erased with them.
  Text that runs into busy drawing of the same darkness is missed by the classical detection. With `translate_sfx = false`,
  hand-drawn sound effects are left as drawn. The layout model, its licence and what its card says of its training data are in `docs/THIRD_PARTY.md`.
* Bubbles that touch or overlap and form one white area are cut apart where they narrow, or where the outline turns sharply inward from both sides, and each is translated on its own.
  This also holds when the two texts sit offset from each other, as long as they are set further apart than the lines within each.
  A single bubble with two sets of columns stays one region (`split_joined_bubbles`, which can also be changed in the book's settings).
  Where the boxes of two regions overlap, each translation is set in the part nearest its own Japanese, so no two translations run over each other; pages from the cache get this as they are shown.
  Pages cached by an earlier version hold only one translation for a pair of touching bubbles, so translate them again with "Translate again" (not using the cache).
* OCR accuracy hardly depends on the size of the letters (clean vertical text reads as well at 12 px as at 28 px,
  and enlarging the crop changes nothing). What lowers the accuracy is text on screentone, decorative typefaces, and regions that are not text at all; these are problems of detection.
* Erasing stays inside the bubble's outline and paints with the bubble's paper colour (cream and shading too), so
  it does not paint over thin outlines broken by anti-aliasing (on the test volume, the pixels changed outside bubbles fell from 67,624 to 19,882,
  and the pixels of broken outlines from 13,398 to 166). `erase_mode = "classic"` brings back the earlier way of erasing.
  Letters drawn into the outline itself, parts without a clear outline (ink splatter and the like), and one or two characters in a small bubble may be left unerased.
* Regions the OCR model can only guess at (faces, highlights, illegible sound effects) are dropped by the confidence filter (`ocr_min_confidence`). One or two characters in a small region (`min_short_bubble`,
  under 60 px) are taken for dots in the drawing and the like, but a short line with a confidence of 0.95 or more that starts with hiragana or kanji,
  in a bubble with an outline, is translated. Katakana in a small region (mostly parts of drawn sound effects) and lone symbols (exclamation marks,
  ellipses) are left as drawn.
* Capture only the page part (for a viewer read in Chrome,
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
