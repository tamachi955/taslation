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
A page whose translations are all in the cache is shown from the cache as soon as the new picture arrives, without an untranslated picture in between. In translator mode,
once the picture has settled (no new picture for 0.4 seconds), the page is read once more and the bubbles not in the cache are added.
While you operate the viewer directly, it looks every 0.7 seconds, and while neither window is in front, it does not look (after a move, a tab switch
or a scroll it looks once). Windows tells it which window is in front, so it does not read the contents of other windows.
With `follow = "poll"` in `taslation.toml`, it always looks every 0.7 seconds.

An untranslated page fills in while you look at it. The bubbles found are marked with frames (dashed; solid once read; gone once they turn out not to be text),
and they are translated in the order the page's bubbles are read, each with the lines before it as context. Each bubble is lettered as soon as its translation is ready. At the end,
names spelled differently from the series sheet are made consistent mechanically, so a few bubbles may change. A translation that does not fit its bubble is set in smaller letters
(the model is not asked to shorten it).
While it works, the badge at the top right shows what it is doing and how many seconds have passed, and the status bar shows the same.

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
  Clicks are passed on in reader mode, in reading mode, and in translator mode while a page that is not translated is shown. While translator mode
  shows a translated page, clicks belong to TASlation, which uses them to select and edit text regions (pages can be turned with the keys).

To a desktop viewer, keys are sent straight to its window without taking the focus. For a viewer that ignores them, TASlation presses the key for real
and then gives the focus back, but only when the viewer's picture has not changed at all for 3 seconds (`page_turn_wait_ms`). If two pages were turned even so,
the status line says so and shows the key that goes back one page. Which way of passing the key turned the page is recorded per viewer in `profiles.json`,
and from then on that way is used from the first key (the 3-second wait happens only the first time with that viewer). A key sent straight to a browser while it is not in front does not reach it
(0 out of 9 times, tried with Chrome and Edge). So a browser is brought to the front for a moment every time and the key is pressed for real; when it cannot be brought to the front, nothing is sent,
and you are told "click the book and turn the page there". To read large, use TASlation's reading mode (F11).
The viewer's own full-screen display is optional; if you use it, switch it yourself, inside the viewer (see "Over a full-screen viewer", next).

### Over a full-screen viewer

This is optional. When you have put the viewer into full screen yourself (TASlation never does), and the viewer is full screen (or fills the monitor)
on the same monitor as TASlation, TASlation behaves like Windows' on-screen keyboard.
It always stays on top, but clicking it does not bring it to the foreground (where key presses go). The viewer stays in the foreground,
so the page keys reach the viewer directly as usual, and TASlation follows to the new page. Browsers go on drawing too.

* TASlation's buttons, checkboxes, the page strip and so on work with a click as usual.
* F5 (translate) goes to TASlation even while the viewer is in the foreground (it does not reload the browser). In reading mode,
  F11 and Esc also belong to TASlation and end reading mode.
  Otherwise F11 and Esc, and the page keys, belong to the viewer (you can use them to switch the viewer's own full screen). TASlation takes these keys only in this mode, and only while the viewer or TASlation is in the foreground.
* When you click a box you type in (Book, To:), press on the page in translator mode, or open a dialog (book settings, the series sheet,
  editing and so on), TASlation becomes an ordinary window for that time and takes key presses. Click the book
  or close the dialog, and it goes back.
* When the book is on another monitor, nothing changes.
* Untick "View > Over the full-screen viewer" to turn it off; it stays off at the next start too (`over_book = false`
  in `taslation.toml` also turns it off by default).

### Reading mode

"Reading mode" (the toolbar button, or F11) is a mode for reading as you would read the original book. It puts a black full screen over the viewer,
enlarges the capture area to fill the screen, and shows only the translated page. Fit the area exactly to the page first.
Page keys and clicks go to the viewer, and Auto follows (if it was off, it is on only while you read, and this is said at the start of each such session). The status is shown at the bottom of the screen for a few seconds only.
It opens on the monitor the window is on, and for a browser window where neither an area nor the page part is known, F11 first asks whether to "Set area..." or "Read as it is".
Esc or F11 takes you back to the window. To go back with the mouse, move the pointer to the top edge of the screen: a faint "✕ Leave reading mode (Esc)" appears at the top right,
and you click it (it disappears when you move the pointer down; clicks anywhere else go to the viewer as before). With `taslation gui --reading`,
reading mode starts as soon as the viewer is chosen.
When you translate a book that has no name yet (in a browser viewer whose tab title is only the viewer's name, for example) in reading mode, those translations are not saved anywhere.
When you leave reading mode, the book's name is asked for once; once you name it, the pages from then on are saved under that name (the page on show can be saved with F5).

**Bubble zoom**: in reading mode, and in reader mode in the normal window, when you rest the pointer on a translated bubble for a moment, a small window appears beside it
and shows the translation at a readable size, next to an enlargement of the original bubble (the Japanese). For a bubble that is hard to read (one flagged "small", a translation much longer than the original,
or one shown on the screen smaller than the readable size `readable_font_size`) it appears after about 0.5 seconds, for other bubbles after about 1.2 seconds, so a pointer that merely
passes over the page does not bring it up. The translation is shown at twice `readable_font_size` (22 pixels by default), and never smaller than on the page. The window never covers the bubble,
and it disappears when the pointer leaves the bubble, on a click (the click goes to the viewer as before), on the wheel, a key or Esc, and when the page changes.
The enlargement of the original is cut out of the page in memory and is not written to disk. The window takes no focus, so even over a full-screen viewer, keys reach the viewer.
It opens when you rest the pointer, not on a click (since clicks on the page belong to the viewer). `bubble_zoom = false` in `taslation.toml` turns it off.

Once you have read the whole book with the whole-book reading, every page is shown at once, which makes reading comfortable. Reading mode translates untranslated pages one page at a time,
and a whole-book reading waits until you leave reading mode (reading mode does not start while a batch is running). The full-screen window covers the viewer,
so the page can be taken only from what the viewer itself draws. Chromium-based viewers, such as the viewers read in a browser, do draw;
with a viewer that does not, the page says so: press Esc and read in the normal window.

### Two ways to read

**Page by page** (the default; what "Auto" and F5 do): each page is translated when you open it, with only the few pages just before it as context.
This is the way of reading that sits most easily with stores' terms of use.

**Translating the whole book first** (optional): the whole book is read only when you choose it in a dialog, and the dialog shows this note:
"A store's terms of use are a contract between you and the store. In a whole-book run TASlation turns no page: it reads only the pages you turn yourself. That does not settle what your store's terms allow, so check them and use this mode knowing that." (The usual consequence of breaking the terms is a suspended account, not a crime.)

In this mode, the first time Auto meets a page that is not in the book's cache, TASlation first checks that it is ready to translate (that Ollama is running, and that the model and the OCR models are installed). If something is missing,
the banner above the page says what is missing and how to fix it, and until it is fixed, nothing is read and pages are translated one at a time (it checks again every 10 seconds).

**The buttons in the banner above the page.** Each line of the banner has a button when it is something TASlation can fix for you.

| The banner says | Button | Pressing it |
|---|---|---|
| The translation program (Ollama) is not running | Start translator again | Starts Ollama there and then, and checks the setup again |
| The translation model the target language needs is not installed | Download model | Asks whether to download it, showing its size (it asks even if you answered "Not now" before) |
| Several windows look like viewers / the viewer was closed | Choose viewer | Opens the "Viewer" list |
| The viewer's window is minimised | Show viewer | Restores the viewer to its size and places it right behind TASlation (no key is pressed, and the focus does not move) |
| The viewer stays black | Show viewer | Brings the viewer's window in front of the other windows. Click the book and reload it |
| TASlation covers the viewer completely | Move TASlation aside | Moves only TASlation's window, so that a little of the viewer shows |

While a whole-book reading is waiting for the viewer, the banner above the page has the same buttons.
If, at start, translation turns out to run on the processor (CPU) (judged by whether Ollama's log names a graphics card),
the banner shows once roughly how many seconds a page takes to translate. "Close" removes it for the rest of that session.

Next, a small dialog asks for the book's name (in page-by-page mode too, if the book has no name yet, the same is asked on the first page).
The cache and the series sheet are saved under this name. Some viewers read in a browser have a tab title that is only the viewer's name, whatever book is open,
and with such a title it always asks (a viewer's or a browser's name is never used as the book's name).
Which part of a title is the viewer's name is learned on this computer: when you choose a second book in the same viewer, or type the book's name without the viewer's part in the "Book" box. From then on that part is left out of the book's name. For the first book the whole title may show in the "Book" box; correct the name there. A browser-based viewer whose tab shows only its own name asks for the book's name first, and your answer teaches it that the title names no book.
What is learned (the titles and program file names of the windows you chose as the viewer, and which parts of titles are a viewer's or a book's) is kept only in `~/.taslation/viewers.json` on this computer. It never goes into a cache export or a log, and it is never sent anywhere. Deleting the file only means choosing the viewer once more.
A book you have named once is recognised from its translated pages, whatever capture area you read it with, and its name is filled in. If several books look alike, the candidates are offered in the box's list,
and if it cannot tell, the name last given with the same viewer is filled in ("Last time with this viewer: ...").
Even after you resize the viewer's window, the book is recognised from its pages the next time you open it (if the two pages of a spread are both close to different pages of the same book, it is taken to be that book). Old caches are matched the way pages were cut out at the time, so they still work as they are.

The same dialog also asks, with the note above, whether to read the whole book first. Enter chooses "Page by page instead" (so that the heavier way does not start without you choosing it). The answer is remembered per book (ui.json in the state folder). For a book you answered "page by page", it does not ask again, and the status line shows how to read it whole. For a book you answered "Start", it asks again next time, and then Enter is "Start" (the run is always your decision). Closing the dialog means "Not now": until you close TASlation, that book is translated page by page and not asked about again (nothing is remembered). Only if you close it while the book has no name yet does it ask again on the next page, since nothing can be kept without a name. If you do read the whole book, turn the pages at your own pace, in the viewer or with the page keys in the TASlation window. TASlation only reads the pages that are turned; it never turns a page itself.
When you have read to the end, press "Finished reading" in the banner, and everything is translated together with the whole story in view (about 1 hour for 190 pages on a mid-range GPU; the time the reading takes is simply the time you spend reading). You cannot read the translations until the translation is finished. The banner above the page shows the number of pages read and waiting,
the time a page takes to read, the translation's progress (how many lines of how many) with its bar, and the time left, with a "Stop" button. The translation's progress also shows as a green bar on TASlation's taskbar button (yellow while the reading is held up and waiting). During the reading, "Auto" is off (the reading reads the pages you turn;
the first time, the status line says so); when it is over, Auto is on again, and from then on every page is shown at once.
When the translation has finished, or has stopped on a problem, and TASlation is not in front, TASlation's taskbar button flashes to tell you
(the focus does not move, and the window is not brought forward; the button stays lit until you open TASlation; when you stopped it with "Stop", it does not tell you).
The setting `flash_when_done = false` stops the flashing, and `sound_when_done = true` also plays Windows' default sound (by default: flashing, no sound).

When the translation has finished, it also checks whether the same character's name is written more than one way in the translations ("竜司" split into "Ryuji" and "Ryūji", for example).
If it finds any, the banner shows how many, with a "Review names..." button (it also opens from "Names rendered in more than one way..." in the "Tools" menu).
Each name is listed with its spellings and how many lines use each; choose the spelling to keep, or type one in "Other:", and press "Apply": the lines with the other spellings are changed to it.
If "Keep it in the series sheet" is ticked (the default), it also goes into the character's rendering in the series sheet, and later translations use that spelling.
Nothing is changed until you press "Apply". Only the name itself is changed, and only in the lines whose Japanese has that name; the rest of the line, the review flags, the notes to the reader and the positions stay as they are.
"Take back" restores both the lines and the series sheet (in translator mode, Ctrl+Z can also take back the lines alone; pressing "Take back" after that restores the series sheet too).
The names are found by fixed rules; no model is used. Only names that carry an honorific such as "さん", "くん" or "様" in the Japanese (2 or more katakana, or 2 to 4 kanji) are considered,
and a name is shown only when the translations write it in two or more ways, each in separate lines, that look like spellings of the same name (missing a case is preferred to making a wrong suggestion).
It does not appear for translations in languages without capital letters (Chinese, Korean, Thai and so on).
The Japanese lines are only kept in memory while TASlation is open, and are written nowhere. So it covers only the lines translated in the last whole-book translation of this session, by that run.

Both modes use the same cache.

### Reading the whole book (optional; check the terms first)

The default is page by page. To read the whole book, press "Read whole book..." in the toolbar. The most pages read in one run is `batch_max_pages` in the settings file.
`--no-context` is available only on the command line. The batch dialog, too, shows the note about stores' terms of use, above "Start".

Translating one page alone means translating without knowing who is speaking, what came before and what comes next. "Batch: Read whole book..."
reads the pages you turn and translates them all together once you have finished reading, in two stages. During the reading, no request at all is made to the model.

1. **Reading**: starting from the page shown when you press "Start", each time you turn a page the new page is taken in and its bubbles are read (OCR). TASlation sends no keys to the viewer.
   You may turn the pages in the viewer, with the page keys in the TASlation window (as many presses as you make are passed on to the viewer), or by clicking the page.
   Reading takes about 2 seconds a screen, but turning quickly is fine. Turned pages wait their turn in memory (up to about 24 screens). If more pile up, the banner asks you to wait a little, and as soon as there is room, the page on show at that moment is taken in.
   If a page was turned before it could be taken in (it was shown too briefly, or you moved on while it was still a blurred provisional picture), the banner above the page says so at once,
   and a dotted frame with "?" appears at its place in the page strip. Go back to that page in the viewer, and it is read like the other pages, at its place in the book's order
   (with the test viewer, no page was missed even at 2 pages a second).
   Going back to an earlier page does not read it twice, and the order does not change. Page images are not written to disk: they are kept in memory only, while TASlation is open.
   They are used only to erase the Japanese ahead and to show the page being translated. The text read and its positions are also kept
   only in memory at this stage (about 5 MB for 200 pages). At this stage, no page can be read yet.
   The window shows the page now on show and the regions read. No text is put on it yet.
   TASlation never decides where the book ends. When you have read to the end, press "Finished reading" in the banner (Enter on the command line). Once the waiting pages are read, it moves on to the next stage.
   You may stop for a while. If no page is turned for an hour, it only stops keeping the screen from switching off, and it reads on from where you were. It never starts translating on its own.
2. **Translation**: after "Finished reading", it translates 3 to 5 pages at a time (`chunk_bubbles`, 30 lines by default), with the series sheet and the whole story (the translations of the earlier lines;
   with Qwen, also the Japanese that follows) as clues, and puts each part into the cache as it is done. From here on, the viewer is not touched.
   Names spelled differently from the series sheet are made consistent mechanically; then the renderings and the lettering sizes are checked and review flags are set (no extra requests to the model).
   Lines that a run of an older version left as draft translations are not sent to the model: at the same stage, they are checked against the series sheet and saved as translations.
   The banner shows "Translating: m of n lines" with its bar, and moves on each time the model translates a line (PLaMo line by line, Qwen as its reply arrives).
   The page area shows the page being translated. Each time the model translates a line, its translation is lettered in its bubble; the lines not translated yet stay as in the original, outlined.
   Once the translations go into the cache, the page shows as the cache has it (until then they are provisional, and nothing of them is saved anywhere).
   When the translation moves on to the next page, so does the page area, and the page strip below outlines that page. The strip only shows how far each page has come: clicking a thumbnail does not show that page.
   To read it, open the page in the viewer, and the translation is shown over it. When a page's picture is no longer in memory, only the banner and the strip move on.
   When the translation ends (also when you stop it, or when it fails), the page area goes back to the viewer's page at once.
   The time left is computed from the speed since the first line was done, so the time to load the model is not included. It is not shown until the speed can be trusted: 8 lines or more, and 15 seconds or more.
   If the speed of the last translation with the same model is kept (ui.json in the state folder, only the speed per line), it starts from that and replaces it bit by bit with this run's speed.
   Under a minute, it says "less than a minute left"; with 10 minutes or more left, it also shows when it will be done ("done at about 13:40").
   The model does not write notes on the volume or review its translations (removed on 2026-11-06). All the model knows of the book is the series sheet you write.
   `--no-context` (command line) does not use this flow: it translates the pages you turn one page at a time.

**Stopping partway.** If up to 3 pages have been read, "Stop" in the reading stage simply ends it. If more have been read,
you are asked before it stops, and you choose among "Keep reading" (Esc and Enter choose this one), "Stop without translating" and "Translate the pages read".
"Translate the pages read", like "Finished reading", first finishes reading the waiting pages, then translates the pages read so far. It does not count as having read the book to the end,
so if you run "Read whole book..." later, it reads on from the page on show. Esc alone never stops the run: pressing Esc partway brings up this question,
however many pages have been read.
"Stop without translating" translates nothing, and the banner shows the number of pages read and a "Translate the pages read" button ("Translate the rest" if you had finished reading the book).
What was read stays in memory only while the window is open, so this button, or running "Read whole book..." again, lets you go on translating or reading from where you were.
If you try to close the window while pages that were read remain untranslated, or partway through a reading, you are asked before it closes ("Keep TASlation open" is the default).
If you close the window, or on the command line, what was read is lost, and pages not cached yet have to be turned and read again (go back to the page where the reading began before you run it).
If you "Stop" in the translation stage (you are asked first here too; the default is "Keep translating"), the translations already saved stay as they are, and only what the request under way would have brought is lost. If the window stays open,
running it again translates the rest without reading. If you closed the window, or on the command line, the reading is needed again,
but pages already translated are not translated again. Pages translated or corrected after the stop, by Auto or otherwise, are not overwritten by the rest of the translation. What was read is never written to disk.

The model's reply is read as far as it can be read, even when it is broken. Only the lines with no usable translation are asked again, a few lines at a time with the lines around them as context, and, if still missing, one line at a time;
a line that still gets no translation is left untranslated, and the translations of the other lines are saved in the cache. The lines left over are translated on their own when you read that page, or at the next run. A line of punctuation only is taken as its own translation.

"Stop" stops it at any time (the result of the request under way is not cached; the question, and how to go on after stopping, are as above). A one-page translation can also be cancelled with Esc, and translated again with F5.
If the model returns nothing for 20 seconds, the badge at the top right says so. When requests fail, the summary shows how many and why,
and if Ollama is not running or the model is missing, it does not keep retrying. During the reading, you are the one who turns the pages. TASlation never turns a page itself,
and never stops on its own at the last page. When you have read to the end, press "Finished reading". Once the reading is over, the viewer is no longer needed, and the screen may switch off.
While the TASlation window is open, the screen does not switch off and the computer does not sleep (because the viewer stops redrawing when the screen switches off).
It cannot prevent closing the lid, putting the computer to sleep by hand, or locking it. Closing the window puts this back as it was.

After that, each page you turn is recognised by its page fingerprint and the saved translations are laid over the live page, so you can read it at once. A page that was not in the batch
is translated on the spot and added to the cache. To go on with an unfinished batch after closing the window, just run it again from the first page.
Cached pages are checked again against the current detection (a bubble that no longer matches a text region is dropped), and only text that is not in the cache is translated, so
running it again after the detection has improved tidies an old cache without translating it again. A cached bubble
is drawn only when there is a text region at the same place on the live page. The app and a batch may have the same cache open at the same time.
Every save merges with what is in the file, so neither overwrites the other's translations, and the translations a batch adds show in the app at once.

### How the viewer is read

The viewer's screen is taken with Windows.Graphics.Capture. A window can be read even behind other windows; the picture taken is only the latest one,
in memory, and is not saved to disk. Where this is not available, it switches to PrintWindow automatically (`taslation doctor`
shows which one is in use). Drawing stops when the display switches off, so the display is kept on while the TASlation window is open.

When you choose the viewer, if its window is smaller than the monitor's work area, the window is enlarged once to fill the work area,
changing only its position and size. No key is pressed and the focus does not move (a maximised window is left as it is, and so is a window you made smaller afterwards).
When you choose another viewer or close TASlation, the window is put back if it still has the size TASlation gave it. For the case where TASlation ends without closing (a crash and the like),
the position and size before enlarging are kept in `ui.json` in the state folder, and at the next start, if the same window still has the enlarged size, it is put back.
During a whole-book reading, the viewer is not moved or resized, so that the banner and the buttons stay visible. A minimised viewer is shown again
by "Start". The larger the viewer's window, the better it is read (the "Read whole book..." dialog says so too).

In a whole-book reading, everything shown is counted in "lines". Pages translated before are shown as "N lines already translated", and the "Read" count in the banner
is the same number of pages as the status bar and the page strip show. When a page in the cache is shown, it says "Looking at the page..." rather than "Translating...".

Some viewers stop drawing while they are hidden. When you choose the viewer, and when reading mode starts, if the viewer is completely hidden by other windows,
TASlation asks it to redraw without pressing any key (the same request Windows makes when another window is moved away), checks whether it draws while still hidden,
and records that per viewer in `profiles.json`. Only a viewer that did not draw is brought to the front for a moment at each page when reading page by page
(with no key press and no change of focus), and put back in its place in the order at once. A viewer that is even partly visible goes on drawing, so it is not brought to the front.
Browsers follow a published rule: they stop drawing only when they are completely covered by an opaque window. So browsers are not checked. A viewer read in a browser does not draw the next page while it is behind, even when it gets the key, so each time a key you pressed in the TASlation window is passed on, the viewer is brought to the front for a moment, the key is pressed for real, and once it has drawn, it is put back in its place in the order.
The focus moves for that moment. In a whole-book reading too, the keys you press are passed on the same way, but the viewer is not brought to the front otherwise. If drawing stops, the banner says so: move the window aside.

### When the viewer stays black

A viewer read in a browser can get stuck on its loading screen, or stay black. When the capture area stays black, TASlation does the following. It never presses a key.

1. **Wait**: loading may just be slow, so it waits for `black_wait_s` (30 seconds by default). After about 8 seconds it says the viewer is "still loading".
   Meanwhile it only checks in memory, about once a second, whether a new frame has arrived (when capturing with PrintWindow, it captures once every 2 seconds).
2. **Tell you**: if it is still black, it tells you, once, to reload in the book's window. Click the book, then press that window's reload key
   (F5 in a browser). In the TASlation window, F5 is the translate key, so pressing it there does not reload.

TASlation goes on waiting, and when a page appears, it continues from the page shown at that moment. It never translates or caches a black screen. A page that really is all black cannot be told from a stalled loading screen, so it is treated the same way.

The same goes for a whole-book reading. The banner shows the same guidance and it waits; when the page comes back, it reads on from there. If it comes back on a page already read, that page is skipped.

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

### The colophon and renaming the book

Near the end of a volume, TASlation reads the colophon (title, volume, author, publisher, ISBN), saves it in the cache's header,
and offers the colophon's title as the book's name, once per book. Choose "Use" or "Keep".

When there are files under the book's current name (the name you typed first, or an old cache saved under the viewer's name), "Use" renames the book.
The translations in every language and the information attached to pages, and the series sheet too if the new name belongs to another series, are moved to the new name,
and the status line shows what was moved and how much.

If that series already has a series sheet (when you renamed an earlier volume to its full title, for example), this book's series sheet is merged into it.
What is added is taken in as it is. Where the two disagree (a term's rendering, a character's first-person pronoun, a policy in the style guide and so on),
the series' value and this book's value are shown side by side, one item at a time, before anything is moved,
and you choose "Keep the series'" or "Take this book's" (you can also choose for all at once). "Rename" renames the book following those answers;
with "Cancel" the name stays as it is, and the colophon's title is offered again next time. This table appears only in the translator role. In the reader role it does not ask, and merges keeping the series' value in every row.
If there is nothing to answer, it merges at once and shows how many entries were added, how many were taken from this book, and how many were kept as the series had them.

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
"About TASlation" in the "Help" menu shows the version, the licence, the fact that the only thing it talks to is Ollama on this computer, the state of the offline guard,
the folder where the cache, series sheets and settings are kept, and where the README and docs/THIRD_PARTY.md are.

### Translator mode

The window has two roles. As **Reader**, keys and clicks on the page go to the viewer. Switch to **Translator** with "Translator" in the toolbar,
and below the toolbar appear translator mode's tools (Reading order, Skip page, Translate again, Book settings, Series sheet, Review, Find and replace, Text direction, Undo, Redo; all of them are only here) and
a line explaining the mouse actions and keys ("Click: select · drag: move · drag a handle: resize · drag the round handle: rotate (Shift: 15° steps) · double-click: edit · drag on empty space: add · Delete: drop · T: text direction · Ctrl+Z: undo · Ctrl+Y: redo · Tab: next region · Alt+arrow keys: move by 1 px"; the keys shown are those set in "Shortcuts" in "Settings", and actions whose key was removed are left out),
and the page can be edited.

* **Keyboard**: Tab on the page selects the next region in reading order, Shift+Tab the previous one (after the last comes the first again;
  the status bar shows which number it is). Alt+arrow keys move the selected region by 1 pixel, Alt+Shift+arrow keys by 10 pixels,
  and a moment after you let go of the keys, it is saved as one move (Ctrl+Z takes it back in one step). As Reader, Alt+arrow keys go on reaching the viewer as arrow keys, as before.
  Esc in the Book or To: box gives the keys back to the page and does nothing else (it does not stop a process that is running).
* **Copying and pasting formatting**: as with a word processor's format painter, Ctrl+Shift+C on the selected region remembers its formatting (font, size, bold and italic,
  alignment, line and letter spacing, slant, text direction, text colour and outline), and selecting another region and pressing Ctrl+Shift+V gives it that formatting
  (Ctrl+Z takes it back in one step). The kind (speech, thought, shout and so on) is premise information the model is told when it translates, so it is not copied with the formatting.
  "Paste format on every region of this kind..." in the "Page" menu applies the copied formatting to every region of this book of the same kind as the selected region
  (it shows how many and asks first; the kinds are held by the book's premises, so it also applies to regions on pages not shown yet;
  when the kind is "(not set)", the regions of translated pages are the ones covered). Whatever page is shown, one Ctrl+Z takes back the whole of it.
  It cannot be used while a batch is running. Ctrl+C remembers the selected region itself (frame and formatting), and Ctrl+V on another page with the same layout
  adds a region at the same place, then reads and translates it (it does not add one where there already is a region, or when the page's size differs).
  All the keys are gathered under "Keys" in "How to use", which "Help" > "Keys..." (Shift+F1) opens (the mouse actions are there too),
  and "How to use..." opens with F1. All the keys written here are the initial ones, and can be changed in "Shortcuts" in "Settings".
  Menu items and buttons also show the keys they currently have.

* **Regions**: every text region is shown with a frame (green: translated, orange: untranslated, blue: a region you marked yourself, red with "?": translated but flagged for review). The speaker,
  and "..." where a sentence continues, are shown too. Frames, the selection frame, handles, the rotation handle and the rectangle being dragged are drawn in two-colour lines, a dark line under the coloured one,
  so they show on white pages and black pages alike. Labels such as the speaker are placed, where there is room, where they do not cover a neighbouring region (above, below, then left or right).
  Draw a rectangle around text that was not detected, and it is read, translated
  and added to the page (later readings and batches use it too). Like shapes in office software, a region is selected with a click, moved by dragging,
  and resized with its handles, and it is read again only when the new frame covers a larger area. Drag the round handle that sticks out from the middle of the selected frame's top edge,
  and the frame rotates around its centre, as a shape in Word does, and is lettered again where you let go (with Shift held, in 15° steps;
  without it, it snaps straight within 3° either side of 0°; the range is up to 89° either way; Esc cancels the drag, and Ctrl+Z takes it back).
  Rotation is the same setting as "Slant" in the editor; a slanted frame is shown at that angle, and its handles sit on the slanted frame.
  A handle of a slanted frame widens or narrows the original (unslanted) frame on the side the handle faces on the page. Delete removes a region,
  and a removed region is remembered as "not text" on that page, so a false detection never comes back.
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
  is treated as not found, on the page on show and in whole-book processing alike, and left as drawn. Regions you added yourself stay, even inside the area.
  An area set on a page of a spread applies to the pages on that side (right or left) and to pages shown one at a time; an area set on a page shown one at a time applies to every
  page; neither applies to pages of a very different shape (a spread made into a single image and the like). Adding one can be taken back with one Ctrl+Z,
  whatever page is shown. The translations inside the area stay in the cache, so taking it back brings them back as they were. All that is saved is the area's four numbers,
  the side of the spread and the page's aspect ratio. Areas cannot be added while a batch is running.
* **Editing a region**: opens with a double-click (or Enter while a region is selected). The formatting fields are folded into the "Formatting" button when the region has no formatting of its own. You can change the **speaker** (chosen from the series sheet's names), the **kind** (Speech,
  Thought, Shout, Narration, Sound effect, Handwritten, Erase only), whether the **sentence continues in the next bubble**, the **hint for the model** (a pun, who is addressed),
  and the translation. Enter starts a new line (the lettering keeps that line break too), and Ctrl+Enter saves.
  With the kind set to "Erase only", the region's original lettering is only erased, and nothing is lettered there (as soon as you choose it, the page behind shows it erased).
  It is not sent for translation (in whole-book processing either), and it is counted neither as flagged for review nor as untranslated. The earlier translation stays in the cache, so setting the kind back letters it again.
  The change can be taken back with Ctrl+Z.
  At the top of the editor, the region as it originally looks is shown, cut out of the captured screen (an image in memory only, saved nowhere).
  A page shown from the cache has no Japanese (the cache keeps only translations), so "Read the Japanese" reads it again there and then;
  "Read as:" then appears, and "Ask again" can be used too (if you press "Ask again" without having read it, it reads first).
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
* "Review..." lists the regions on that page worth a look (flagged for review, untranslated, or with a note to the reader).
  "Ask again" in the editor has the model translate that bubble again, with the lines before it as context (there is no feature that lists alternatives).
  To flag translations that contain a word the dictionary does not know as well, install `pyspellchecker` (`pip install pyspellchecker`;
  MIT licence; it keeps word lists for English, Spanish, French, Portuguese, German, Italian, Russian and Dutch on disk;
  the series sheet's names and renderings are exempt). When the spellcheck setting (`spellcheck`, on by default) is on but this package is not installed,
  it says so once, the first time you open the editor (nothing is fetched from the network).
* "Undo" (Ctrl+Z) takes back the changes to the page on show, newest first (edits of translations and notes; moving, resizing, adding and removing regions (a change made to several regions at once
  counts as one); saved formatting; setting kinds and text sizes;
  "Skip page"; setting the reading order; "Translate again"),
  and "Redo" (Ctrl+Y) applies them again. Changes on other pages can be taken back when that page is shown again.
  Taking back "Translate again" brings back the page's earlier translations. A translate-again that ended without translating anything (a stop, for example) is not something to take back.
* "Find and replace..." (a translator-mode button) searches and replaces across all the translations of the current book in the current language.
  Use it, for example, to correct a wrong character name throughout a volume at once. You can keep reading the book with the window open, and as you type, the matches
  are listed with their page numbers and the text around them (the match is between `«` and `»`; the page number is not the book's printed page number,
  but the order in which the page entered the cache). "Match case" and "Whole word" narrow the search. "Whole word" does not look for word boundaries next to
  scripts that put no spaces between words, such as Japanese, Chinese, Korean and Thai.
  Nothing is written until you press a replace button. "Replace selected" replaces only the matches selected in the list (Ctrl and Shift select several),
  and "Replace all" replaces every match (the list shows only the first 500, but the count and "Replace all" cover them all).
  The page on show is lettered again at once, and other pages show the new translations the next time they are shown.

  Only the translations change. Review flags, notes to the reader, draft marks, marks of unfinished pages and the bubbles' positions stay as they are.
  The lines were not looked at and corrected one by one, so, unlike an edit of a region, it does not clear review flags. A bubble whose translation would become empty is not replaced, and this is said.
  A replacement is one change as a whole: while it is the book's latest change, Ctrl+Z takes it back on all pages at once, whatever page is shown,
  and Ctrl+Y applies it again (in the Find and replace window as well). If you edit another page after it, that edit must be taken back first.
  A bubble whose content changed because it was translated again is no longer part of what is taken back.

  The series sheet does not change on its own. Only when the words replaced with "Replace all" were a rendering in the series sheet does it ask, once, as for a region edit,
  whether to use the new rendering. When only some lines were replaced, it does not ask. Undoing does not take back a change to the series sheet.
  Nothing can be replaced during a batch or while a page is being processed. Press it again once that is over.
* "Book settings..." saves the detection and OCR values that suit this book (thresholds, text-block detection, sound effects) and this book's lettering size
  ("Lettering size" and "Largest size"; "As in Settings" and an empty box mean the values in "Tools > Settings..."), together with the book's premises,
  without changing your own settings. "Apply to this book" re-sets the page on show from the cache (nothing is translated again).
  "Clear all" shows how many settings will go and asks before clearing them (the default button is "Keep them"),
  and leaves the window open. Meanwhile "Undo" brings the cleared settings back. Below that, the areas ignored on every page of this book are listed
  with the pages they apply to (All pages, Right-hand pages, Left-hand pages) and their position (in % of the page's width and height), and "Remove area" (or the Delete key in the list)
  removes the selected area at once (text is looked for there again). "Undo" takes back the last thing done in this window (Clear all, or removing an area).
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
  If a page is being processed, it asks once that is over; during a whole-book run it replaces nothing, and says so (you can correct it with "Find and replace" once the run is over).

The speaker, kind, continuation mark and note go with each bubble, and the series sheet is placed before the bubbles, when they are given to the model. They are saved in
`~/.taslation/annotations/<book>.json` and
`~/.taslation/glossary/<series>.json` (names that would give the same file name get `<name>-<hash>.json`),
and hold only positions, facts and policies. Neither the text nor the translations go in.

The effect of the premises can be measured without a book with
`python tools/premises_eval.py` (it translates test lines with and without a series sheet and scores names, pronouns, honorifics,
split sentences and ways of speaking). With the default model, the series sheet raised the pass rate from 58% to 90%. Translating a real volume again
with a series sheet whose facts had been checked against the book brought character-name errors from 208 to 0, and in a blind evaluation with context,
the new translation was preferred for 51% of the changed bubbles and the old one for 36% (`docs/OFFLINE_VERIFICATION.md`).
Check the facts first. A series sheet written from the model's own guesses was no better than none.

### Page fingerprints

A page fingerprint is a 320-bit perceptual hash of the page's content area (a 16x16 gradient hash and an 8x8 brightness hash of the shrunken page),
not a hash of a file. The same page captured at another size or zoom gives nearly the same bits, and a difference of up to 36 bits counts as "the same page".
The page cannot be rebuilt from its fingerprint. Similar pages (blank pages, an advertisement that recurs) are told apart by their aspect ratio and their place in the order.

### Reading in a browser: give the book's tab its own window

A Chrome (or Edge) window is recognised by its title, but a browser window's title is that of its active tab.
If the book's tab shares a window with other tabs, TASlation can see the book only while that tab is in front, and a batch started from the command line
loses the window when you switch tabs.

The fix is needed only once. Drag the reader's tab out of the window (or right-click the tab and choose "Move tab to new window")
to give it a window of its own. Leave that window open behind your other work. It may be hidden, but do not minimise it.
A desktop viewer is an app of its own, so it does not need this. A window other than a browser, such as an image viewer, is treated as the book as long as the same window stays open, even if its title (a file name or page number)
changes with every page you turn, and a change of title does not make it wait. Only when the window is hidden or minimised
does the status line say so and wait for it to come back.

If the window shows another tab even so, Auto and the batch notice the change of title, say so on the status line and wait for the book to come back.
They never read the wrong page. `taslation batch` also waits for the viewer's window to appear (`--wait`, 10 minutes by default), so
you can start it before you open the book. The translation stage does not touch the viewer.

A batch has three safeguards.

* Only one batch at a time can work with a given viewer window (a second one does not start, and says which process is using it).
* A screen that does not look like a page of the book is not read. A store page opened by a stray click, recommendations, or another book have a different shape, so the banner says so and it waits. Go back to the book, or press "Finished reading".
  A page of text only, such as an afterword, is judged by the paper at the place where the page always is, and when a panel opens over the page, the paper seems to spread beyond that place, so the two can be told apart.
* A batch clicks nothing and sends no keys. You are the one who turns the pages.

After you change premises such as the series sheet, `taslation batch --retranslate` reads every page again and translates it again,
so the change reaches the whole volume (cached pages are replaced).

When the reading reaches the end of the volume, some viewers show an end-of-book panel (ratings, the next volume). The arrow keys may not get you out of this panel,
so then close it with "x" and go back to the first page. Text that looks like part of the viewer itself or of a colophon page (horizontal lines of Latin letters and numbers)
is taken as print, not dialogue, and left as it is.

### The translation cache and backups

The cache is in `~/.taslation/cache/<book>.json`,
one file per target language (the book's name comes from the viewer window's title and can be changed in the "Book" box; books that give the same file name, such as "My:Book 1" and "My
Book 1", get `<book>-<hash>.json`). "Saved translations..." in the "Tools" menu
lists and deletes caches. "Delete" moves only the file of the selected row's book, in that row's language, to the Windows Recycle Bin
(the translations in other languages stay). The confirmation's default button is "Keep them", and the file can be restored from the Recycle Bin. When it cannot be moved to the Recycle Bin
(on a drive without one, for example), nothing is deleted, and this is said. On the command line, `taslation cache delete` deletes all languages, as before. A file holds only the translations, the normalised shapes and positions of the bubbles, the page fingerprints and the notes to the reader,
so open it in a text editor and see for yourself. The model never writes notes about the story to keep (note files that an old version wrote in
`~/.taslation/series` are left as they are, unread; delete them if you do not need them).

A cache, page-information or series-sheet file that TASlation cannot read (a broken one, or one written by a newer version) is not overwritten.
It is kept beside as `<name>.unreadable-<date>.json`, a line is printed on the console, and a new file takes its place.
Deleting the book or the series deletes such copies too.

A book's cache can be made into a file encrypted with a passphrase, as a backup for yourself or to move it to another computer of your own ("Saved translations...",
or `taslation cache export` and `taslation cache import`). The file contains the translations,
so keep it to yourself. Without the passphrase, no one, TASlation included, can open it, and a forgotten passphrase cannot be recovered.

* Export and import each start with a warning. An exported file is for you alone (even if the book is yours, giving it to someone else infringes the author's rights),
  and you import only files you made yourself, on your own computer. "Cancel" there stops before you choose a file.
* While you type the passphrase, what it still lacks is shown, and "Show" unmasks it. A full-width space is treated as an ordinary space.
  Without the extra package `cryptography`, export and import are greyed out.
* Each import keeps the cache it changes beside it as `<cache>.before-import.<date>.json`,
  so you can go back by hand. A wrong passphrase, a broken file, a file too large for a book's cache (over 5,000 pages,
  or over 500 bubbles on a page), or pages made by a newer version of TASlation: in these cases it refuses without writing anything.
* `cache export` does not overwrite an existing file unless you add `--force`.

`cache export` and `cache import` only print what the file is for to standard error before asking for the passphrase,
and ask nothing more, so they can run unattended from a script. With `--confirm` they ask "Continue? [y/N]",
and anything but yes ends with exit status 1, reading and writing nothing. The passphrase is asked for without being shown. The environment variable
`TASLATION_PASSPHRASE` is for scripts only, because PowerShell's PSReadLine writes a line such as
`$env:TASLATION_PASSPHRASE = "…"` to its history file (its filter for secrets reacts to
"password" but not to "passphrase"). The safe way is to type it at the command's prompt.
If you use the variable even so, do not write the value on the command line; have the shell ask for it:

```
$env:TASLATION_PASSPHRASE = Read-Host -MaskInput               # PowerShell 7
read -rs TASLATION_PASSPHRASE && export TASLATION_PASSPHRASE   # bash, zsh
```

### Translating into other languages

The target language is chosen in the "To:" box (or with `--language`, or the setting `target_language`).
The cache and the series sheet are saved per language, and the lettering switches to a font for that script. The model that translates is decided by the target language
(see "Choosing the model"). The quality depends on how good the model is in that language. When tried with Qwen3.5 4B,
Spanish, Chinese and Korean were good, and Arabic was visibly worse.
Indic scripts are drawn one character at a time (because the text layout engine that comes with Pillow does not shape glyphs). Everything else
is set correctly, including Arabic and Hebrew, which are written from right to left.

### Command line

```
taslation                      open the TASlation window (the same as `taslation gui`)
taslation gui --window "<title>" --on-top   open with the viewer chosen, and keep the window over the viewer (Auto on; --no-auto starts with it off)
taslation gui --reading        start in reading mode (the page alone, full screen) once the viewer is chosen
taslation windows              list the windows that can be captured
taslation doctor               check the models, fonts, Ollama, the network guard, and whether each stage runs on the GPU or the CPU
taslation notice [--country CODE] [--reset]   show the legal notice of the start for a country (ISO code); --reset shows it again at the next start
taslation cache export <book> --out FILE [--force] [--confirm]   export the translation cache to a file encrypted with your own passphrase (a backup for yourself, or for another computer of yours); --force overwrites an existing FILE
taslation cache import FILE [--replace] [--confirm]    read that file back into the cache (merged with what is there, or replacing it)
taslation batch --window "<title>" --book "My Book 1" [--max-pages N] [--no-context]   read the pages you turn; Enter when you have finished reading, Ctrl+C to stop
taslation read --window "<title>" --book "My Book 1"   capture once, translate and preview
    (both take the book's name from the viewer window's title; a title with no book's name in it, such as
     "<viewer> - Google Chrome" with only the viewer's name, is refused, so give --book NAME)
taslation translate page.png --show    translate an image file of your own (writes nothing)
taslation translate page.png --translator echo --no-translate   detection and OCR only
taslation review --book <book> [--notes]   cached translations flagged for review (could only be set small, a rendering missing, much longer or shorter than the Japanese, the OCR unsure, a word not in the dictionary); --notes also lists the notes to the reader
taslation cache list | delete <book> | path
taslation glossary list | show <series> | set <series> <term> <rendering> [--note ..] | delete <series> [term]
taslation glossary apply <series> --rename OLD=NEW [..] [--dry-run]   replace OLD with NEW in what is already translated
taslation glossary font <series> "Comic Neue" | --clear   the lettering font the series suggests (checks whether this PC has it)
taslation glossary lettering <series> thought|shout|narration|handwritten|sfx [--family NAME] [--italic|--no-italic] [--bold|--no-bold] [--reset]
taslation batch --window "<title>" --retranslate   translate every page again with the current premises
taslation gui --mode book --role translator   start in the mode that translates the whole book first (the default is page), as translator
taslation audit page.png       run the processing and show every network connection made
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
(the model's own chat template cannot name the target language, and ends up translating back into Japanese). Each line is one request,
which carries the earlier lines and their translations, the series sheet as reference information (for a line with a speaker set, that speaker too), and, as a glossary, the series sheet's renderings that appear in that line.
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
it asks separately whether to remove it, and keeps it by default. The first time PLaMo is installed, it first asks for your agreement to its licence.
While it lies over the book, in reading mode, and during a whole-book run, it does not ask; it asks when you are back in the window.
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
a batch needs a long context, support for a wide range of languages, and the ability to follow a glossary.

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
Translated the way a batch translates, its translations are as close to the 30B's as those of the best build of Qwen3 4B (chrF 45.7 over 401 lines;
Qwen3 4B 46.2 at Q6_K, 44.5 at Q4_K_M), it follows the series sheet about as well (39 of 45 checks; the 30B 41),
and it is the fastest model among them. With Ollama's KV cache quantised (see "Installation"), it generates 60 tokens a second on a 6 GB
GPU while keeping the batch's 16K context, about four times as fast as the 30B on the same machine. Its vision weights are not used,
and thinking mode is turned off for every request. In a blind evaluation with the 30B as judge,
Qwen3 4B came out slightly below the 30B (of 162 lines, the 30B's translation was preferred for 89, Qwen3 4B's for 63).

For the highest quality, use `qwen3:30b-a3b-instruct-2507-q4_K_M`. It is an MoE with 3B active parameters, and
needs about 20 GB of RAM, but uses little GPU memory. On the development machine it generates 17 tokens a second with a short context,
and 11 tokens a second with the batch's 32K context. If you have RAM to spare, fetch it and set `ollama_model` and
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
the lettering size (80 to 130 %; 100 % keeps the largest size that fits the bubble, and 90 % sets every translation a tenth smaller;
above 100 %, nothing goes past the bubble or the largest size, and only translations that were held back to keep sizes even on the page get larger;
in the settings file it is `text_scale`, and a book's own value is in translator mode's "Book settings..."); whether to letter in capitals; whether to set slanted lettering at the same slant; the size of the window's text; whether to stay always on top; how a book starts (page by page, or the whole book first);
and whether to use the optional page models (the layout model and the inpainting). The settings of other features (the enlarged view of the bubble under the pointer, the flashing and sound of the taskbar button when a whole-book reading ends) are listed here too.
For the inpainting (erasing lettering on the drawing with LaMa and filling in the drawing), choose "Not used", "Only with a GPU" or "Always, also on the CPU". The default is "Only with a GPU":
it is used only on a computer where the model is installed and there is a GPU TASlation can use (an NVIDIA GPU with CUDA, one that PyTorch can use with CUDA).
On other computers, erasing works as with "Not used", and the model is not even loaded (the setting's row then says so).
`install.cmd` installs PyTorch's GPU build (the CUDA build) on a computer with an NVIDIA GPU, so there it is used with "Only with a GPU" as it is.
On a computer without a GPU (AMD and Intel GPUs are not counted as GPUs either), with an old driver, or where the GPU build did not work, the CPU build is installed, and the inpainting is not used there (README, "Installation").
On a computer where an installation before this version put in the CPU build, running `install.cmd` again replaces it with the GPU build. The installation after `update.cmd` does not replace it, and says so.
With "Always, also on the CPU", it is used even without a GPU, but takes about 4 seconds a screen (about 0.6 seconds on a GPU).
The layout model is not used by default while it is measured on more books. Neither model makes clear where the images used to train it come from (`docs/THIRD_PARTY.md`).
The two models are installed together, with one question (`install.cmd` tells you about their origin before it asks). On a computer where TASlation uses LaMa on the GPU (one where the GPU build of PyTorch is being or has been installed),
Enter installs them ([Y/n]); elsewhere Enter does not ([y/N]). A run without a console installs them on neither (`-Yes` does not answer this question either).
Running `python setup_models.py` by hand asks the same way, and what Enter means is decided by whether PyTorch can use a CUDA GPU (the same judgement as "Only with a GPU"). With `--agreed`, it installs them without asking.
"Save" writes to `taslation.toml` and takes effect at once (the page on show is re-set from the cache). The file's comments and other lines stay as they are.
The size of the window's text changes when you save, but it reaches every part of the window only after a restart.

"Open settings file" opens `taslation.toml`, with every setting in it, in a text editor. If there is no file, it first makes one from `taslation.toml.example`.
In the file it makes, every setting is a description with `#` at the start of the line, and removing the `#` turns that setting on (no default value is written in, so if a later version changes a default, you get the new default).
It is made where the settings are read from (the file that was read, or else `taslation.toml` in the state folder; the state folder survives updates).
Updating with `update.cmd` does not overwrite `taslation.toml` in the TASlation folder (README, "Updating").
Settings changed in the file take effect from the next start.

The "Shortcuts" page of "Settings" changes the window's keys. Choose an action in the list (translating the page on show, reading mode, Undo, Redo,
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
For detection, the classical detection runs on the CPU, and when the layout model is used, that model runs on the GPU. The OCR runs on the CPU. Translation runs where Ollama loaded the model,
and when only part of it is in video memory, it shows something like "GPU and CPU (60 % on the GPU)" (if no model is loaded, it says so).
For erasing, the fill with the paper's colour runs on the CPU, and when the inpainting (LaMa) is used, the part on the drawing runs on the GPU (on the CPU with "Always, also on the CPU" and no GPU). Only NVIDIA GPUs with CUDA are counted as GPUs,
and it neither loads a model nor starts Ollama to find out. The seconds are the average of the last 20 pages lettered, saved in `timings.json` in the state folder when the window closes (numbers only; nothing of the pages' content).
"Look again" refreshes it. `taslation doctor` prints the same as "Where each stage runs:".

The settings file `taslation.toml` is looked for in this order: the one given with `--config`, `./taslation.toml` in the folder it was run from, and `taslation.toml` in the state folder (`~/.taslation`,
or the place in the environment variable `TASLATION_STATE_DIR`); the first one found is read (with none, the defaults apply).
Put it in the state folder. `taslation doctor` shows which file was read.

A `taslation.toml` placed in the working directory or in this folder is read (optional):

```toml
ollama_model = "auto"        # "auto": PLaMo 3 Translate 2B, or Qwen3.5 4B for Brazilian Portuguese and Turkish; or a model of your own
ollama_num_ctx = 16384       # the chat translator's context window (a batch request needs ~10K); PLaMo has its own (8192)
target_language = "English"
uppercase = false            # scanlation-style capitals (Latin script only)
readable_font_size = 11      # a translation set smaller than this is flagged "small" for review (0 = never)
text_scale = 1.0             # the lettering size: 0.9 a tenth smaller, 1.2 larger where the page held it back (a book can have its own)
enforce_terms = true         # a translation that misses a rendering from the series sheet is flagged "rendering"
spellcheck = true            # flag a word the dictionary does not know (needs `pip install pyspellchecker`, offline word lists)
take_columns_beyond = false  # dark bubbles: also read a column that goes on past the interior on the bubble's own black (a book setting too)
next_page_key = "Left"       # key that shows the next page in your viewer
context_mode = true          # batch: read the whole book first, then translate it with the whole story as context
chunk_bubbles = 30           # lines per translation request in context mode (3-5 pages)
erase_mode = "fill"          # "fill": the bubble's own paper, flat or along its shading, within its outline;
                             # "inpaint": the same way, inpainted; "classic": the erase before 2026-10-30, byte for byte
art_erase = "auto"           # with "fill", lettering on the drawing is inpainted by LaMa once installed: "auto" only where PyTorch has a CUDA GPU (else as "off"), "lama" also on the CPU, "off"
detect_model = "off"         # (opt-in for now: "auto") the layout model first, the classical detectors add what it missed: "auto" (where art_erase runs), "on", "off"
ollama_keep_alive = "5m"     # how long Ollama keeps the model after a request: "2h", "90s", seconds; "-1" never
                             # unloads, "0" unloads after every request
ocr_threads = 0              # CPU threads for the OCR model (0 = torch's default, one per core); while
                             # other programs keep the CPU busy, half the cores can be faster
font_path = ""               # auto: the series sheet's font where installed, then models/fonts per script, then system fonts
flash_when_done = true       # a whole-book run that ends while TASlation is not in front flashes its taskbar button
sound_when_done = false      # ... and plays the system's default sound
```

The size of the window's text can be changed with `ui_scale` (1.0 follows Windows' scaling; 0.5 to 3.0).
At start it is multiplied by the scaling of the monitor the window is on, and when you move the window to a monitor with different scaling, the text size changes to suit that monitor.
Parts drawn in pixels (the page, the frames of the page list and so on) keep their original size.

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
(because an installation from the window leaves nothing behind). When winget installs Python and Ollama, your Y to the question is passed on to winget
as agreement to its terms of use (`--accept-source-agreements --accept-package-agreements`; this is said before the question).

If an earlier installation has only manga-ocr-charspot-small, TASlation works with that model alone. The status line says so in one line,
and it is not an error. Running `install.cmd` installs the other two.

All the OCR runs on the CPU, and the three models share the `ocr_threads` setting. The GPU is left free for Ollama. When the CPU is busy with
other work, setting `ocr_threads` to half the number of cores can make it faster.

Ollama's model is put in GPU memory only when it is needed. It is not loaded at start, but when a line that needs translating comes up
(this takes a few seconds and shows in the status). It is not loaded for a page whose translations are in the cache. A loaded model stays for
`ollama_keep_alive` ("5m" by default) after the last request, then is released automatically. While you read on through untranslated pages, each request
extends this, so it is not loaded again for every page. In a whole-book run, the model is not loaded while pages are being read,
but when the reading is over and it moves on to the notes and the translation. At the end of a run (a stop or a failure included) and when the window closes, it is released at once.
With `ollama_keep_alive = "-1"`, as before, it is loaded at start, before the OCR models, and never released.
When only part of the loaded model fits on the graphics card, it is loaded once more, and if it still does not fit, you are told so.

### Trying it without a book

`python tools/fake_viewer.py` opens a stand-in viewer that shows synthetic test pages (left arrow for the next page).
Choose the window titled "Fake Viewer" in TASlation, and you can check that capture, the whole-book reading
and the passing of page keys all work.

### The error log and "Copy details"

The window records errors in `log.txt` in the state folder (when it grows large, it moves on to a next file, and the oldest are deleted, so it is about 1 MB in all).
It writes the environment at start (TASlation's version and date, Python, Tk, Windows, torch and the graphics card, Ollama's version), the names and values of settings changed from their defaults,
warnings, and errors with where they happened (the program's file name and line).
It does not write the page's text, OCR results, translations, book titles or window titles. For file locations, it writes only the state folder and the models folder, by name (`<state dir>` and the like),
and replaces the file names beyond them, and any other place, with `<path>`. Quotations in error messages, and characters that are not ASCII (Japanese and so on), are replaced with `…`.

"Copy details", in "Help > About TASlation" and on the screens that report an error, puts the same content (environment, changed settings, the last error) on the clipboard.
Paste it when you report a problem. It sends nothing anywhere. On the screen shown when it could not start, too, "Yes" copies it.

## Checking for yourself that it works offline

1. Check that `taslation doctor` prints
   `Network guard: ON (loopback:11434 only ...)`.
   In the window, "About TASlation" in the "Help" menu shows the same state. The status bar shows something
   only when the guard has blocked an attempt to connect (it then stays until you close the window).
2. `taslation audit tests/fixtures/sample_page.png --translator echo`
   runs the whole detection and OCR process and shows every network connection the process made. With the echo translator the list is empty;
   with Ollama, only `127.0.0.1:11434` is shown (the warm-up request that loads the model, and the page's request).
3. The test suite has a test
   that checks that a raw socket from inside the process cannot reach an outside address (`tests/test_netguard.py`).
4. Turn off Wi-Fi or unplug the cable, and use it as usual. Ollama goes on answering, and the OCR models
   are loaded from `models/`.

`docs/OFFLINE_VERIFICATION.md` records the procedure and the results of the checks made during development.

## How it works

See `docs/ARCHITECTURE.md` for the details. In outline: a page on the screen is identified by a 320-bit perceptual page fingerprint (one page at a time for a spread; the fingerprint is taken over the inked area on that page's paper, and in a viewer with a dark background, the page's large bright part and what lines up with it are taken as paper; any text in the area is treated as belonging to the page above, below or beside it),
and if it is in the cache, the saved translations are laid over the live page. If not, it detects the bubbles with OpenCV, runs the OCR,
translates with the Ollama model (with the series sheet and the pages just before as context; PLaMo one line at a time, Qwen once per page), erases and letters, and saves the translations in the cache.
A batch does the same for a whole book, in the two stages described above. The window's icon is drawn by `tools/make_icon.py`
with Pillow alone and kept in `taslation/ui/assets/`. Run it again if you change the drawing.

## Limitations

* Detection is classical image processing. It covers closed bubbles and boxes (bright and dark alike; dark bubbles, and light lettering on dark parts, are lettered in white)
  and dialogue and sound effects written straight on the page. For text written straight on the page, only the letters and the bright background around them are erased; the drawing next to them, fine lines and halftone dots included, is kept,
  and the translation is set in the space that is freed. When the drawing is close, the translation gets smaller, and small bits of drawing mistaken for parts of letters are erased with them.
  Text that runs into busy drawing of the same darkness is missed. With `translate_sfx = false`,
  hand-drawn sound effects are left as drawn. Why no neural-network detector is bundled is explained in `docs/THIRD_PARTY.md`.
* Bubbles that touch or overlap and form one white area are cut apart where they narrow, or where the outline turns sharply inward from both sides, and each is translated on its own.
  A single bubble with two sets of columns stays one region (`split_joined_bubbles`, which can also be changed in the book's settings).
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
* The quality of the translation depends on the Ollama model. Larger models do better, and are slower for it. The batch is there
  so that speed does not matter when you read. In languages the model is weak in, the translations are worse.
* Names are rendered consistently only when they are written in the series sheet. A name not written there is read by the model line by line, so its rendering may vary.
  Find such names with the review flags or "Find and replace...", and add them to the series sheet.
* Page fingerprints stand up to differences in window size and viewer background,
  but not to switching between single-page and two-page display (a spread is split into two pages, so pages batch-processed as spreads are recognised in single-page display too,
  but not the other way round).
* Capture is Windows only. On other operating systems, the `translate` command processes image files.
