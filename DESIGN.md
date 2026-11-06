---
name: Pods
description: A local, cited research reader over a personal podcast library.
colors:
  slate-shell: "#1d2638"
  shell-ink: "#eef1f7"
  shell-ink-muted: "#a9b3c9"
  shell-line: "#2d3850"
  marigold: "#f4b33e"
  ground: "#f4f5f8"
  surface: "#ffffff"
  surface-sunk: "#eceef3"
  ink: "#141821"
  ink-muted: "#525a6b"
  ink-faint: "#656d80"
  line: "#d9dde6"
  line-strong: "#bfc5d2"
  accent: "#36435f"
  accent-ink: "#ffffff"
  accent-hover: "#2a354d"
  cite-bg: "#f6ddec"
  cite-ink: "#6b1d4c"
  cite-live: "#b8287a"
  cite-live-ink: "#ffffff"
  cite-live-tint: "#fbeaf4"
  speaker-1: "#3d6be0"
  speaker-2: "#b4389a"
  speaker-3: "#7a4fd0"
  speaker-4: "#1f8fb0"
  speaker-other: "#8a84a8"
  tape-s0: "#f4b33e"
  tape-s1: "#f3f2ee"
  tape-s2: "#ff8a7a"
  tape-s3: "#8fb3e8"
  state-new: "#525a6b"
  state-progress: "#3d6be0"
  state-done: "#4a4fb0"
  state-failed: "#c0263d"
  state-cancelled: "#656d80"
  state-warn: "#2f3f9e"
  selection: "#dfe4ee"
  home-wall: "#36435f"
  home-wall-ink: "#eef1f7"
  home-wall-muted: "#c3cbdc"
  home-bin: "#131418"
  home-bin-edge: "#272a33"
  home-bin-ink: "#c2c6cf"
  home-divider-soft: "#fbe0ae"
  home-sticker: "#ff8a7a"
  home-stamp-ink: "#b8473a"
  home-paper: "#f3f2ee"
  home-card: "#ffffff"
  home-ink: "#131418"
  home-muted: "#555963"
  home-slip-line: "#b6b9c2"
  home-vinyl: "#191b21"
typography:
  display:
    fontFamily: "Source Serif 4 Variable, Source Serif 4, Georgia, serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.22
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 600
    lineHeight: 1.3
  prose:
    fontFamily: "Source Serif 4 Variable, Source Serif 4, Georgia, serif"
    fontSize: "1.1875rem"
    fontWeight: 400
    lineHeight: 1.62
  body:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "\"tnum\""
  body-sm:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "\"tnum\""
  label:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.45
    fontFeature: "\"tnum\""
  home-sign:
    fontFamily: "Anton, Archivo Variable, Source Sans 3 Variable, system-ui, sans-serif"
    fontSize: "clamp(2.5rem, 4.1vw, 3.75rem)"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.004em"
  home-block-head:
    fontFamily: "Anton, Archivo Variable, Source Sans 3 Variable, system-ui, sans-serif"
    fontSize: "clamp(1.75rem, 2.4vw, 2.125rem)"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.01em"
  home-text:
    fontFamily: "Archivo Variable, Source Sans 3 Variable, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  home-hand:
    fontFamily: "Permanent Marker, Archivo Variable, cursive"
    fontSize: "1.375rem"
    fontWeight: 400
    lineHeight: 1.12
rounded:
  chip: "3px"
  sm: "4px"
  md: "6px"
  lg: "10px"
spacing:
  s-1: "4px"
  s-2: "8px"
  s-3: "12px"
  s-4: "16px"
  s-5: "20px"
  s-6: "24px"
  s-8: "32px"
  s-10: "40px"
  s-12: "48px"
components:
  button-default:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: "7px 12px"
  button-default-hover:
    backgroundColor: "{colors.surface-sunk}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: "7px 12px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.md}"
    padding: "7px 12px"
  button-ghost-hover:
    backgroundColor: "{colors.surface-sunk}"
    textColor: "{colors.ink}"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.state-failed}"
    rounded: "{rounded.md}"
    padding: "7px 12px"
  button-sm:
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "7px 12px"
  citation-marker:
    backgroundColor: "{colors.cite-bg}"
    textColor: "{colors.cite-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "1px 5px"
  citation-marker-live:
    backgroundColor: "{colors.cite-live}"
    textColor: "{colors.cite-live-ink}"
  reference-entry-live:
    backgroundColor: "{colors.cite-live-tint}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  status-stamp:
    backgroundColor: "transparent"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "1px 7px"
  nav-topbar:
    backgroundColor: "{colors.slate-shell}"
    textColor: "{colors.shell-ink-muted}"
    height: "52px"
  nav-topbar-link-active:
    textColor: "{colors.shell-ink}"
  composer:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "12px 16px"
  data-table-header:
    backgroundColor: "{colors.surface-sunk}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
    padding: "8px 12px"
  dialog:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "20px 24px"
  home-ask-field:
    backgroundColor: "{colors.home-card}"
    textColor: "{colors.home-ink}"
    typography: "{typography.home-text}"
    height: "60px"
    padding: "0 18px"
  home-ask-button:
    backgroundColor: "{colors.marigold}"
    textColor: "{colors.home-ink}"
    padding: "0 26px"
  home-divider-tab:
    backgroundColor: "{colors.marigold}"
    textColor: "{colors.home-bin}"
    typography: "{typography.home-hand}"
    rounded: "6px 6px 0 0"
    height: "50px"
    padding: "8px 16px 0"
  home-bin:
    backgroundColor: "{colors.home-bin}"
    textColor: "{colors.home-bin-ink}"
    padding: "0 24px"
  home-sticker:
    backgroundColor: "{colors.home-sticker}"
    textColor: "{colors.home-bin}"
    rounded: "50%"
  home-seal:
    backgroundColor: "{colors.home-sticker}"
    textColor: "{colors.home-bin}"
    padding: "5px 8px"
  home-staff-pick:
    backgroundColor: "{colors.home-paper}"
    textColor: "{colors.home-ink}"
    typography: "{typography.home-hand}"
    width: "270px"
    padding: "18px 16px 16px"
  home-hold-slip:
    backgroundColor: "{colors.home-card}"
    textColor: "{colors.home-ink}"
    padding: "44px 14px 12px"
  home-rubber-stamp:
    backgroundColor: "transparent"
    textColor: "{colors.home-stamp-ink}"
    rounded: "{rounded.chip}"
    padding: "3px 8px 2px"
---

# Design System: Pods

## Overview

**Creative North Star: "The Reference Apparatus"**

Pods reads like a research paper that answers back. Every answer is a serif paragraph carrying numbered citation markers, and its reference list stands beside it the way a paper holds its sources: episode number first, title, a duration-exact speaker strip, then speaker and timestamp. The working pages are held by a deep slate top bar on a cool grey-white ground, with hairline modules rather than cards and bubbles. The centered chat column with grey bubbles and source pills is the rejected model.

Density is high and calm. Rules are 1px hairlines, radii are small (3 to 10px), and nothing floats: depth is tonal (ground, surface, sunk surface) plus 1px rings. Every time, count, and catalog number is set in tabular numerals so columns of figures align. Colour is spent on meaning only: slate for structure and action, one marigold rule for where you are, a pale-pink chip for a citation at rest, magenta for the one citation the reader is looking at, a blue/magenta/violet/teal series for speakers, and a stamp family for job state.

The front door is a different room in the same building. The home page ("Browse Bins") is the library as a record shop: a slate shop wall with taped posters and a staff pick, a near-black crate of sleeves along the bottom, and a paper counter for new books and asking. It shares the top bar's slate and marigold so the shell and the wall read as one family, but it owns its type, materials, and depth (see Components, Home). The apparatus rules below hold on every other page.

The system follows the operating system's light or dark preference; both themes come from the same token names in `frontend/src/styles/tokens.css`, the contract file components consume. The home page scopes its own `--h-*` tokens on `.home` in `frontend/src/pages/HomePage.css`, built on the shared slate, marigold, and tape tokens.

**Key Characteristics:**
- Slate top bar (52px) on a cool grey-white ground; the active section carries a 2px marigold rule.
- Serif for reading (answers, summaries, episode titles); sans for all UI.
- Tabular numerals everywhere a number appears.
- Focusing a citation lifts its reference in magenta and dims the others to 45% opacity.
- Apparatus pages: hairlines and 1px rings instead of shadows; no gradients, no glass.
- Home: a record shop built from physical objects (sleeves, divider cards, taped posters, slips), in Anton, Archivo, and Permanent Marker.
- Authored SVG icons only; no emojis, no unicode glyphs as icons.

## Colors

A cool slate world with one warm marker (marigold) for place and one hot accent (magenta) rationed to the live citation; the home page adds coral and counter paper.

### Primary
- **Deep Slate Shell** (slate-shell): the top bar and the book-cover placeholder; the darkest structural surface. Bar text is Shell Frost (shell-ink) when active and Muted Shell Frost (shell-ink-muted) at rest; Shell Seam (shell-line) is the bar's bottom rule and the placeholder progress track. Dark theme: #121826.
- **Slate** (accent): primary buttons, links, caret, checkbox accent, active feed title. Hover deepens to accent-hover. Dark theme flips to a pale slate blue (#a9bce2, hover #c3d2ef) with dark ink (#10131a). The same slate is the home page's shop wall.

### Secondary
- **Citation Magenta** (cite-live): the live or focused citation marker, the lifted reference's 1px ring and number chip, the active transcript segment's ring, and the focus ring (including on the home page's ask field). Dark theme: #f06bb2 with dark ink #1a0b14. 5.8:1 against white in light.
- **Citation Blush** (cite-bg) with **Citation Plum** (cite-ink): every citation chip at rest (inline marker and reference number). **Lifted Blush** (cite-live-tint) is the background of a lifted reference or active transcript segment.
- **Marigold** (marigold): the 2px active-section underline in the top bar, and inside the home world the divider cards, record labels, the Ask button, the headline's emphasised word, pins, and the back-room progress fill. Same value in both themes. As tape-s0 it is also the first voice on dark slate (record grooves) and the book-cover placeholder's progress fill.

### Tertiary
- **Speaker series** (speaker-1 blue, speaker-2 magenta, speaker-3 violet, speaker-4 teal, speaker-other grey-violet): assigned in order of first appearance; used for speaker strips, 8 to 9px speaker swatches, and the speaker name that opens each transcript line on light surfaces.
- **Tape series** (tape-s0 marigold, tape-s1 counter paper, tape-s2 coral, tape-s3 sky): the speaker series for voices drawn on dark slate or black (the home groove and its caption swatches); same in both themes. Voices below 5% of the talk, and any after the fourth, draw in a neutral grey.
- **State stamps** (state-new, state-progress, state-done, state-failed, state-cancelled, state-warn): text and 1px border colour of status stamps, and progress-bar fills (progress blue, done indigo). New and cancelled reuse the muted and faint ink tones.

### Neutral
- **Cool Ground** (ground): page background; also the 2px gap inside the focus ring. Dark: #10131a.
- **Paper** (surface): panels, inputs, references column, tables, dialogs, composer. Dark: #181c26.
- **Sunk Slate** (surface-sunk): conversation list, table header, disabled inputs, hover fills, empty strip track. Dark: #141821.
- **Slate Ink** (ink), **Muted Ink** (ink-muted, secondary text, at least 4.5:1 on ground), **Faint Ink** (ink-faint, placeholders and meta, at least 4.5:1 on surface).
- **Hairline** (line) for module and row rules; **Strong Hairline** (line-strong) for control borders and blockquote rules.
- **Selection** (selection): text selection on apparatus pages; the home page selects in marigold on crate black.

### Home palette (page-scoped)
- **Shop Wall** (home-wall, the accent slate) with faint 1px panel seams every 160px; **Wall Frost** (home-wall-ink) for the headline and **Wall Muted** (home-wall-muted, 6:1 on the wall) for the lede. Dark: wall #2b3550.
- **Crate Black** (home-bin) with **Crate Lip** (home-bin-edge) and **Crate Ink** (home-bin-ink); also the 10px seam between wall and counter, the 8px shelf under the book rack, and the Ask field's 3px frame on the wall. **Vinyl** (home-vinyl) is the record disc.
- **Coral Sticker** (home-sticker): the round duration sticker, "Sealed" seals, the third divider card, and the rubber-stamp border. **Soft Marigold** (home-divider-soft) is the first divider card.
- **Counter Paper** (home-paper) behind the counter; **Card White** (home-card) for slips, the ask field, and book backing; **Counter Ink** (home-ink), **Counter Muted** (home-muted), and **Slip Rule** (home-slip-line) for dashed slip borders and the progress track. Dark: paper #181c26, card #1f2430, ink #e8ebf2, muted #aab2c3, slip rule #3a4256, links #a9bce2.

### Named Rules
**The One Magenta Rule.** Citation Magenta (cite-live) belongs to the live/focused citation and the focus ring only. No other element may use the citation hue. Resting citation chips use cite-bg / cite-ink.

**The Cool Stamps Rule.** State colours stay in the slate, blue, indigo, and violet family; red (state-failed) appears only for failure; no green anywhere. Marigold and coral are never state colours.

**The Marigold Is Place Rule.** Outside the home world, marigold marks exactly one thing per screen: the active section's 2px rule (plus the tape-s0 progress fill on a dark book placeholder). Inside the home world it is the shop's sign paint. It never appears as a fill, badge, or highlight on apparatus pages.

**The Meaning-Only Colour Rule.** Every non-neutral colour encodes something (structure, action, place, citation, speaker, state). Components consume colours through tokens; the home page's colours live in its `--h-*` scope, never inline.

## Typography

**Display Font:** Source Serif 4 Variable (with Georgia, serif)
**Body Font:** Source Sans 3 Variable (with system-ui, sans-serif)
**Home faces:** Anton (shop-sign caps), Archivo Variable (text), Permanent Marker (handwriting), all self-hosted via fontsource and loaded only by the home page.

**Character:** A bookish serif for anything the reader reads at length, a neutral humanist sans for everything they operate. The serif signals source material; the sans signals apparatus. The home swaps both for a shop: condensed sign caps, a sturdy grotesque, and a marker hand.

### Hierarchy
- **Display** (600, 2rem, 1.22, -0.015em, serif): episode title only, capped at 34ch; drops to 1.5rem below 768px. A sans catalog number at title size (1.1875rem, muted) may precede it.
- **Headline** (600, 1.5rem, 1.3, -0.01em, sans): the question line in a chat turn (max 44ch), page titles, empty-chat prompt.
- **Title** (600, 1.1875rem, sans): episode section headings, dialog titles.
- **Prose** (400, 1.1875rem, 1.62, serif): answer paragraphs, max 68ch. Episode summaries use the same serif at 0.9375rem with the same leading.
- **Body** (400, 0.9375rem, 1.4, sans): UI body, inputs, composer, transcript text (1.58 leading, 68ch).
- **Body small** (400 to 600, 0.8125rem, sans): table cells, buttons, reference titles, conversation titles.
- **Label** (600, 0.75rem, sans): stamps, column headers, meta lines, citation numbers (bold), nav labels. Sentence case.
- **Wordmark** (600, 1.0625rem, serif) beside a 15px serif monogram in the top bar.

### Home hierarchy
- **Shop sign** (Anton 400, clamp(2.5rem, 4.1vw, 3.75rem), 1.0, uppercase, balanced): the one h1, max 440px wide; one word may be painted marigold.
- **Counter heads** (Anton 400, clamp(1.75rem, 2.4vw, 2.125rem), 1.0, uppercase): "New in: books", "Ask the counter", each with a 13px semibold Archivo link on the right.
- **Sleeve type**: Anton for the catalog number (clamp 20 to 36px) and sealed titles (clamp 16 to 27px); Archivo 800 uppercase tracked 0.08em for the show name; Archivo 600 for the two-line episode title.
- **Text** (Archivo 400 to 600, 0.75 to 1.0625rem): lede (1rem, 1.5, 36ch), captions, book titles (14px bold), meta (12px), ask input (500, 1.0625rem).
- **Hand** (Permanent Marker): divider-card names (clamp 14 to 20px) and the staff-pick quote (1.375rem, 1.12) only.

### Named Rules
**The Tabular Rule.** Body sets `font-variant-numeric: tabular-nums` globally; every time, duration, count, cost, and episode number stays tabular, on the home crate too.

**The Serif Is Source Rule.** Serif is reserved for answer prose, summaries, episode titles, and the wordmark. Headings inside summaries, all controls, and all metadata are sans.

**The Sentence Case Rule.** Apparatus pages set nothing in uppercase. Uppercase belongs to the home world's signage (Anton heads, sleeve show names, seals, stickers, the Ask button).

**The Marker Is Handwriting Rule.** Permanent Marker appears only where a clerk would write by hand: divider cards and the staff-pick quote. Never for headings, buttons, or body.

## Layout

A fixed shell: a 52px sticky slate top bar above a flexible workspace. There are no side rails.

**Chat** is two or three columns: a flexible centre and a 380px references column (surface, sticky, full height) separated by a hairline; conversations open from the top bar's "Conversations" menu as a 360px panel below the bar. The centre opens with an index strip (min 56px: episodes, passages, hours, scope picker, tabular counts separated by middle dots) and ends with a sticky composer (max 740px). Turns are 40px apart; question to answer 20px. Below 1200px the references column collapses into an inline disclosure under each answer.

**Pages** (Library, Books, Jobs, Episode) sit in a container max 1320px with 24px by 32px padding (16px below 768px), under a page header with a hairline beneath.

**Episode** stacks player/timeline, summary, and transcript in one shared column: a 56px timestamp gutter plus the 68ch measure. The speaker name opens each transcript line. Below 768px the gutter folds above the text.

**Library table** uses fixed layout so the title column absorbs slack: 34px checkbox, 84px episode number, then title. Titles stay on one line with ellipsis and the meta on a second line; rows are compact (7px vertical cell padding, about 50px). Below 768px, duration, speakers, status, passages, and job columns hide; titles clamp to two lines and duration plus status restack inside the title cell.

**Home** fills the viewport under the bar (min-height 100svh minus 52px) as two columns: the wall (1.18fr) and the counter (min 400px, 1fr), joined by a 10px crate-black seam. The wall is a grid of intro (left) and a 330px pinboard (right) over the crate, which spans the wall's full width at its foot (aspect 100:54, max 440px tall). The counter stacks books, ask, and two slips (1.4fr and 1fr) with 32px between blocks. At 1100px and below the page becomes one column, the counter drops under the wall, and the seam turns horizontal; the crate caps at 820px. At 700px and below the pinboard becomes a two-column grid (posters side by side, staff pick full width), the ask field moves onto the wall under the lede (the counter's ask block hides), the crate sizes from the viewport width, the bin caption and flip controls stack, the third divider card hides, and the slips stack.

Spacing runs on a 4px base (s-1 to s-12); 8, 12, 16, and 20px carry most gaps. The home uses the same steps plus clamp() padding (20 to 44px) at its edges.

## Elevation & Depth

Apparatus pages are flat. There are no drop shadows. Depth comes from three tonal layers (sunk surface, ground, paper) and from 1px edges: hairline borders on modules and rows, and `inset 0 0 0 1px` rings for the selected item (line colour) and for the lifted reference or active transcript segment (magenta). Modal dialogs dim the page with a 45% ink scrim, not a shadow.

The home world is made of physical objects and is allowed their weight: pinned and leaned things cast one-sided, negatively spread drop shadows that fall below them, and the wall, cellophane, and ruled paper are drawn with gradients. None of this crosses into other pages.

### Shadow Vocabulary
- **Selection ring** (`box-shadow: inset 0 0 0 1px var(--line)`): active conversation item.
- **Live ring** (`box-shadow: inset 0 0 0 1px var(--cite-live)`): lifted reference, active transcript segment.
- **Focus ring** (`box-shadow: 0 0 0 2px var(--ground), 0 0 0 4px var(--cite-live)`): every `:focus-visible`, replacing the outline; also the home ask field's focus-within.
- **Home, front sleeve** (`0 30px 40px -18px rgba(0,0,0,0.6)`): the face-out record.
- **Home, back sleeve** (`0 18px 30px -18px rgba(0,0,0,0.55)`): sleeves behind it.
- **Home, book cover** (`0 16px 22px -14px rgba(0,0,0,0.55)`): covers on the counter rack.
- **Home, poster** (`0 14px 24px -14px rgba(0,0,0,0.6)`) and **staff pick** (`0 12px 20px -12px rgba(0,0,0,0.6)`): things taped or pinned to the wall.

### Named Rules
**The Ring Not Shadow Rule.** On apparatus pages, if something needs to stand forward, give it a 1px ring and a tonal fill. Blur shadows, gradients, and glass do not exist there.

**The Objects Cast Shadows Rule.** On the home page only an object (sleeve, cover, poster, pinned card) casts a shadow, and only downward with negative spread. Text blocks, controls, and the counter never do.

## Shapes

Apparatus: small, quiet corners: 3px on citation chips and reference numbers, 4px on stamps, small buttons, and timestamp buttons, 6px on buttons, inputs, modules, tables, and reference entries, 10px only on the composer and dialogs. Speaker strips are 6px tall (2px radius) when compact and 20px (4px radius, hairline) when full. Borders are 1px throughout; the only exception is the 1.5px logo square in the top bar. Any side rule (blockquote) is 1px Strong Hairline.

Home: square paper and board. Sleeves are square with 2px corners; posters, slips, the staff pick, and the ask field are square-cornered; divider cards are rounded only on top (6px 6px 0 0); the duration sticker and pin are circles. Objects sit at slight tilts (sleeves -4 to 1deg, posters 2.5 and -4deg, staff pick -2deg, divider cards -1 to 1.2deg, sticker 9deg, stamps -5 to -6deg). Borders here are heavier and material: a 3px frame on the ask field (with a 3px inset rule before the Ask button), 1.5px dashed slips, a 2px stamp border, a 6px crate lip, and an 8px shelf under the books.

## Components

### Buttons
Compact and quiet; the label, not the fill, carries most of them.
- **Shape:** gently rounded (6px); small variant 4px.
- **Default:** paper fill, ink text, 1px Strong Hairline border, 7px by 12px padding, 0.8125rem semibold.
- **Primary:** Slate fill and border with white text; hover deepens to accent-hover.
- **Ghost:** transparent, muted ink; hover gains a sunk fill and hairline border.
- **Danger:** paper fill, failure-red text and border.
- **Hover / Focus:** 120ms colour transitions on the standard ease-out; focus uses the magenta focus ring. Disabled drops to 50% opacity.

### Citation Markers (signature)
- **Style:** superscript chip, 0.75rem bold tabular, 1px by 5px padding, 3px radius, Citation Blush on Citation Plum.
- **State:** hover or live flips to Citation Magenta with white ink over 220ms. The matching reference entry lifts (Lifted Blush fill, magenta 1px ring, magenta number chip) and every other entry dims to 45% opacity.

### Reference Entries
- **Layout:** 26px number column plus body; 10px by 12px padding; hairline between entries, 6px radius.
- **Content order:** episode number prefix (muted) and title, compact speaker strip, then speaker swatch, speaker, timestamps; optional 0.75rem snippet.

### Status Stamps
- **Style:** transparent fill, 1px border in currentColor, 0.75rem semibold tabular text, 1px by 7px padding, 4px radius. The colour is the state token; stamps never use a solid background.
- **Pipeline tally:** episode states (New / Downloaded / Transcribed / Indexed) carry three 3x9px ticks, filled per completed step (download, transcribe, index); unfilled ticks sit at 22% opacity.
- **Running:** the stamp fills left-to-right with its progress at 12% of the state colour.
- **Finished:** Done and Indexed are double-ruled (inset paper ring + currentColor ring), like a validation stamp.
- **Cancelled:** text struck through; cancelled and failed work stays listed, never hidden.

### Library Brief (new-chat apparatus)
The empty new chat is never a void: heading, one-line explainer, then a "Recently indexed" reference list (up to 6 entries: Ep. number column, serif title on one line, speaker swatches, duration, passages, date) with an "Ask about this" action that scopes the chat to that episode and focuses the composer; closes with a link to the full Library.

### Cited-Passage Apparatus (Episode page)
- **Margin:** at 1200px and wider, the transcript's right margin holds a sticky "Cited in your conversations" column: each conversation that cited the episode, linking back to it, with [n] timestamp chips (Citation Blush on Citation Plum) that jump the transcript. Below 1200px it moves above the transcript.
- **Marks:** transcript segments overlapping a saved citation get a "cited" chip under their timestamp in the same resting citation colours. Magenta stays reserved for the live citation.

### Pipeline Explainer (Jobs empty state)
An empty queue explains itself: three hairline-divided steps (Download, Transcribe, Index), each headed by the stamp it produces, naming the real models from config and which step is paid, then one primary action into the Library.

### Speaker Strip (signature)
A duration-exact horizontal bar on a sunk track: each speaker turn is a block in its speaker colour positioned by time. The full variant (20px) is seekable, with a 2px ink playhead and hover readout of speaker and time.

### Cards / Containers
- **Corner Style:** 6px.
- **Background:** paper on ground; sunk slate for side panels and selection bars.
- **Shadow Strategy:** none; see Elevation & Depth.
- **Border:** 1px hairline.
- **Internal Padding:** 16px (player), 20px by 24px (summary), 12px by 16px (cost bar).

### Inputs / Fields
- **Style:** paper fill, 1px Strong Hairline, 6px radius, 7px by 12px padding, 0.9375rem; small variant 5px by 10px at 0.8125rem.
- **Hover:** border darkens to faint ink. **Focus:** magenta focus ring; the composer box instead turns its border magenta on focus-within.
- **Disabled:** sunk fill, faint ink, not-allowed cursor.

### Data Tables
Dense ledger: paper module with hairline border and 6px radius; sunk header row with 0.75rem semibold muted labels; 0.8125rem tabular cells with 8px by 12px padding and hairline rows; row hover shows the ground tone.

### Navigation
Slate top bar (52px, 1px Shell Seam beneath) across every page: a 28px serif monogram square (1.5px muted border) plus "Pods" wordmark (links home), then Chat / Library / Books / Jobs as icon-and-label links in muted shell frost, 0.8125rem semibold. Hover and active turn shell frost; the active section adds a 2px marigold underline rule inset 12px from the link edges and flush with the bar's bottom edge. A progress-blue count badge may follow a link. A right-hand slot holds page actions (Chat's "Conversations" menu, which drops a 360px panel below the bar). Below 768px the wordmark hides; below 420px link icons hide.

### Icons
Authored inline SVGs from a single module (`components/Icons.tsx`), 12 to 18px, stroke in currentColor. The home's flip chevrons are inline SVG paths at 14px.

### Home: Browse Bins (signature world)
The library as a record shop. Page-scoped; nothing here is reused on apparatus pages, and nothing from the apparatus's flat rules applies here except tokens, tabular numerals, the focus ring, and authored icons. Everything shown is real data: posters are the library's own shows, the quote is verified, the crate holds real episodes.

- **The wall:** Shop Wall slate with 1px seams every 160px. Top left: the shop-sign h1 ("Dig through everything you've heard.", "everything" in marigold) and a one-line lede of real counts in Wall Muted.
- **Taped duotone poster:** a white print (8px border, 26px bottom margin holding an 11px semibold caption "Show · episode count") with two translucent cream tape strips (54 by 20px, rotated -24 and 22deg) over its top corners. The art is the show's artwork duotoned locally to Deep Slate Shell shadows and Marigold highlights (served square from the podcast poster endpoint). If it fails to load, a type poster stands in: marigold board, show name in Anton, three horizontal bars (wall, coral, wall). Two posters at most, tilted 2.5 and -4deg.
- **Staff-pick card:** counter paper ruled every 26px in faint slate, 270px wide, tilted -2deg, a marigold pin at top right; a verified pull quote from a finished book in Permanent Marker, then speaker, episode number, and time in 12px semibold muted. The whole card links to that moment in the episode. Hover straightens it to -1deg and lifts 2px.
- **Crate:** a crate-black bin (84 to 112px tall, 6px Crate Lip on top) along the wall's foot. Its caption explains the groove with tape swatches naming each voice; at right, 34px square flip buttons (1.5px grey border, 4px radius, marigold border and 12% marigold wash on hover) and a tabular "n of m" count. Order is time: newest transcribed episode face-out, then the rest, then untranscribed episodes. Arrow keys flip when the crate has focus.
- **Sleeve with groove:** the face-out record, 42% of the crate width, square, tilted -4deg, sunk 56px into the bin. Its art is the whole conversation as a spiral groove (34 turns) on a vinyl disc, each turn stroked 2.2px in its speaker's tape colour, a marigold label and a centre hole. Show name (Archivo 800 caps) and two-line title top left, catalog number in Anton top right. Hover lifts 6px. A coral duration sticker (circle, 11.5% wide, min 70px, rotated 9deg) overlaps its corner: tabular duration over "n turns".
- **Sealed sleeve:** an untranscribed episode: slate-grey board under a diagonal cellophane gloss, title in Anton caps, a coral "Sealed" seal (Archivo 800 caps on coral). Back sleeves sit behind at 34% width, the nearer one showing "Ep. n · title" in Anton.
- **Divider tab:** one card per podcast in the crate (up to three), standing up from the bin behind the sleeves: marigold (first soft marigold, third coral), 6px top corners, 38 to 50px tall, show name in Permanent Marker, tilted -1 to 1.2deg. Clicking jumps the crate to that show's first sleeve; hover lifts 4px.
- **Counter blocks:** counter paper with Anton heads and right-aligned links. "New in: books" racks up to three real covers (640:854, shadowed, lift 4px on hover) on an 8px crate-black shelf, each with a bold title and "Told by narrator · n pages". "Ask the counter" holds the ask field: 60px, 3px ink frame, white card, Archivo 500 input, and a marigold "Ask" button (Archivo 800 caps tracked 0.08em, hover #f7c463) behind a 3px inset rule; a one-line note under it. Asking lands in Chat with the question.
- **Hold slips:** two dashed slips (1.5px Slip Rule, white card, 44px top padding) side by side: "On hold" (latest chat, title and relative date) and "Back room" (the running job with a 4px progress bar in marigold, or "Nothing processing" with the sealed count). Linked slips turn their dash slate on hover.
- **Rubber stamp:** the name of a slip or the staff pick, inked onto the object: Anton caps 0.9375rem tracked 0.05em, 2px coral border, 3px radius, rotated -5 to -6deg at 90% opacity, its ink holding at least 4.5:1 against the object's paper, pinned into a corner of the object (top right on slips, overlapping the top edge of the staff pick). It is decorative and hidden from assistive tech; each object carries its real name in text for screen readers. A stamp is never a small spaced-caps line set above a heading.
- **Empty and loading:** an empty crate shows a single "Empty bin" divider and a caption linking to podcast discovery; loading shows the bare bin; an empty rack and an empty ask explain the next step in one line.

**Motion.** The signature interaction is the crate flip: the front sleeve tips back into the bin over 180ms (`cubic-bezier(0.55, 0, 1, 0.45)`: down 34px, rotate to 3deg, scale 0.94, fade out), then the next rises over 520ms on the standard ease-out (from 22px low, -1deg, 35% opacity to its -4deg rest). The front link stays mounted so focus survives the flip. Hover lifts run 120 to 220ms on the ease-out. The only thing that moves on its own is the back-room progress bar (width, 600ms ease-out). Under reduced motion the flip swaps instantly.

## Do's and Don'ts

### Do:
- **Do** consume colours, type, space, radius, and motion only through the custom properties in `styles/tokens.css`, or the home's page-scoped `--h-*` tokens built on them.
- **Do** reserve Citation Magenta (cite-live) for the live/focused citation and the focus ring; resting chips use cite-bg / cite-ink.
- **Do** keep state stamps in the slate, blue, indigo, and violet family, with state-failed red only for failure.
- **Do** mark the active section with the 2px marigold rule and nothing else marigold on apparatus pages.
- **Do** set every number in tabular numerals.
- **Do** set reading text in Source Serif 4 at a 68ch measure and all UI in Source Sans 3.
- **Do** separate apparatus modules with 1px hairlines and lift with 1px rings plus tonal fills.
- **Do** align Episode player, summary, and transcript to one column (56px gutter plus 68ch) and open each transcript line with the speaker name.
- **Do** keep Library rows compact and one-line (title with meta beneath), restacking duration and status into the title cell below 768px.
- **Do** use authored SVG icons from `components/Icons.tsx`.
- **Do** use the shared motion: ease-out `cubic-bezier(0.16, 1, 0.3, 1)` at 120ms for controls and 220ms for citation lift and dimming, collapsed under reduced motion.
- **Do** build the home only from real data: the library's own shows as duotone posters, verified quotes, real episodes in time order, real counts.
- **Do** draw voices on dark slate or black in the tape series, and voices on light surfaces in the speaker series.

### Don't:
- **Don't** use emojis or unicode glyphs as icons anywhere.
- **Don't** use green anywhere, or marigold and coral as state colours.
- **Don't** give any element other than the live citation and the focus ring the magenta citation hue.
- **Don't** place eyebrow or kicker labels above headings; on the home, an object's name is a rubber stamp inked onto the object, never a caps line above its title.
- **Don't** use coloured border-left or border-right rules thicker than 1px on apparatus pages.
- **Don't** use drop shadows, gradients, or glass on apparatus pages; 1px rings only. Home shadows belong to objects.
- **Don't** carry Anton, Archivo, Permanent Marker, uppercase signage, or tilted objects out of the home page.
- **Don't** animate anything on the home page on its own except the back-room progress bar.
- **Don't** build chat as a centered column of grey bubbles with source pills.
- **Don't** use podcast logos or branding as the app's identity; show artwork appears only as a duotoned poster of that show.
