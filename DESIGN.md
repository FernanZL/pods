---
name: Pods
description: A local, cited research reader over a personal podcast library.
colors:
  indigo-shell: "#261a57"
  shell-ink: "#f1edff"
  shell-ink-muted: "#b3a9dc"
  shell-line: "#3a2d74"
  ground: "#f8f7fc"
  surface: "#ffffff"
  surface-sunk: "#efedf6"
  ink: "#17142a"
  ink-muted: "#57527a"
  ink-faint: "#6e6890"
  line: "#dcd8ea"
  line-strong: "#c3bddb"
  accent: "#3a2a85"
  accent-ink: "#ffffff"
  accent-hover: "#2d1f6e"
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
  state-new: "#57527a"
  state-progress: "#3d6be0"
  state-done: "#5b3fc4"
  state-failed: "#c0263d"
  state-cancelled: "#6e6890"
  state-warn: "#2f3f9e"
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
  nav-rail:
    backgroundColor: "{colors.indigo-shell}"
    textColor: "{colors.shell-ink-muted}"
    width: "72px"
  nav-rail-link-active:
    backgroundColor: "{colors.shell-line}"
    textColor: "{colors.shell-ink}"
    rounded: "{rounded.md}"
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
---

# Design System: Pods

## Overview

**Creative North Star: "The Reference Apparatus"**

Pods reads like a research paper that answers back. Every answer is a serif paragraph carrying numbered citation markers, and its reference list stands beside it the way a paper holds its sources: episode number first, title, a duration-exact speaker strip, then speaker and timestamp. The page is held by a deep indigo shell rail on a lavender-white ground, with hairline modules rather than cards and bubbles. The centered chat column with grey bubbles and source pills is the rejected model.

Density is high and calm. Rules are 1px hairlines, radii are small (3 to 10px), and nothing floats: depth is tonal (ground, surface, sunk surface) plus 1px rings. Every time, count, and catalog number is set in tabular numerals so columns of figures align. Colour is spent on meaning only: indigo for structure and action, a pale-pink chip for a citation at rest, magenta for the one citation the reader is looking at, a blue/magenta/violet/teal series for speakers, and a stamp family for job state.

The system follows the operating system's light or dark preference; both themes are defined from the same token names in `frontend/src/styles/tokens.css`, which is the contract file components consume.

**Key Characteristics:**
- Indigo shell rail (72px) on lavender-white ground; three-column chat (280px conversations, flexible centre, 380px references).
- Serif for reading (answers, summaries, episode titles); sans for all UI.
- Tabular numerals everywhere a number appears.
- Focusing a citation lifts its reference in magenta and dims the others to 45% opacity.
- Hairlines and 1px rings instead of shadows; no gradients, no glass.
- Authored SVG icons only; no emojis, no unicode glyphs as icons.

## Colors

A cool indigo-violet world with a single hot accent, magenta, rationed to the live citation.

### Primary
- **Deep Indigo Shell** (indigo-shell): the navigation rail background; the darkest structural surface. Rail text is Shell Lavender (shell-ink) when active and Muted Shell Lavender (shell-ink-muted) at rest; Shell Seam (shell-line) is the rail's hover and active fill and its divider. Dark theme: #1a1338.
- **Ink Indigo** (accent): primary buttons, links, checkbox accent, active feed title. Hover deepens to accent-hover. Dark theme flips to a light violet (#a993ff, hover #c0afff) with dark ink (#160f33).

### Secondary
- **Citation Magenta** (cite-live): the live or focused citation marker, the lifted reference's 1px ring and number chip, the active transcript segment's ring, and the focus ring. Dark theme: #f06bb2 with dark ink #1a0b14. 5.8:1 against white in light.
- **Citation Blush** (cite-bg) with **Citation Plum** (cite-ink): every citation chip at rest (inline marker and reference number). **Lifted Blush** (cite-live-tint) is the background of a lifted reference or active transcript segment.

### Tertiary
- **Speaker series** (speaker-1 blue, speaker-2 magenta, speaker-3 violet, speaker-4 teal, speaker-other grey-violet): assigned in order of first appearance; used for speaker strips, 8 to 9px speaker swatches, and the speaker name that opens each transcript line.
- **State stamps** (state-new, state-progress, state-done, state-failed, state-cancelled, state-warn): text and 1px border colour of status stamps, and progress-bar fills (progress blue, done violet). New and cancelled reuse the muted and faint ink tones.

### Neutral
- **Lavender Ground** (ground): page background; also the 2px gap inside the focus ring. Dark: #13111c.
- **Paper** (surface): panels, inputs, references column, tables, dialogs, composer. Dark: #1c1929.
- **Sunk Lavender** (surface-sunk): conversation list, table header, disabled inputs, hover fills, empty strip track. Dark: #171424.
- **Indigo Ink** (ink), **Muted Ink** (ink-muted, secondary text, at least 4.5:1 on ground), **Faint Ink** (ink-faint, placeholders and meta, at least 4.5:1 on surface).
- **Hairline** (line) for module and row rules; **Strong Hairline** (line-strong) for control borders and blockquote rules.

### Named Rules
**The One Magenta Rule.** Citation Magenta (cite-live) belongs to the live/focused citation and the focus ring only. No other element may use the citation hue. Resting citation chips use cite-bg / cite-ink.

**The Cool Stamps Rule.** State colours stay in the indigo, blue, and violet family. Red (state-failed) appears only for failure. No amber and no green anywhere in the product.

**The Meaning-Only Colour Rule.** Every non-neutral colour encodes something (structure, action, citation, speaker, state). Decorative colour has no slot in the token file; components never hard-code colours.

## Typography

**Display Font:** Source Serif 4 Variable (with Georgia, serif)
**Body Font:** Source Sans 3 Variable (with system-ui, sans-serif)

**Character:** A bookish serif for anything the reader reads at length, a neutral humanist sans for everything they operate. The serif signals source material; the sans signals apparatus.

### Hierarchy
- **Display** (600, 2rem, 1.22, -0.015em, serif): episode title only, capped at 34ch; drops to 1.5rem below 768px. A sans catalog number at title size (1.1875rem, muted) may precede it.
- **Headline** (600, 1.5rem, 1.3, -0.01em, sans): the question line in a chat turn (max 44ch), page titles, empty-chat prompt.
- **Title** (600, 1.1875rem, sans): episode section headings, dialog titles.
- **Prose** (400, 1.1875rem, 1.62, serif): answer paragraphs, max 68ch. Episode summaries use the same serif at 0.9375rem with the same leading.
- **Body** (400, 0.9375rem, 1.4, sans): UI body, inputs, composer, transcript text (1.58 leading, 68ch).
- **Body small** (400 to 600, 0.8125rem, sans): table cells, buttons, reference titles, conversation titles.
- **Label** (600, 0.75rem, sans): stamps, column headers, meta lines, citation numbers (bold), nav labels. Sentence case; nothing in the product is set uppercase.

### Named Rules
**The Tabular Rule.** Body sets `font-variant-numeric: tabular-nums` globally; every time, duration, count, cost, and episode number stays tabular.

**The Serif Is Source Rule.** Serif is reserved for answer prose, summaries, and episode titles. Headings inside summaries, all controls, and all metadata are sans.

## Layout

A fixed shell grid: 72px indigo rail plus a flexible workspace. Below 768px the rail becomes a 52px sticky top bar with horizontal nav links.

**Chat** is three columns: 280px conversation list (sunk surface, sticky, full height), a flexible centre, and a 380px references column (surface, sticky, full height), separated by hairlines. The centre opens with an index strip (min 56px: episodes, passages, hours, scope picker, tabular counts separated by middle dots) and ends with a sticky composer (max 740px). Turns are 40px apart; question to answer 20px. Below 1200px the references column collapses into an inline disclosure under each answer and the conversation list becomes a drawer.

**Pages** (Library, Jobs, Episode) sit in a container max 1320px with 24px by 32px padding (16px below 768px), under a page header with a hairline beneath.

**Episode** stacks player/timeline, summary, and transcript in one shared column: a 56px timestamp gutter plus the 68ch measure. The speaker name opens each transcript line. Below 768px the gutter folds above the text.

**Library table** uses fixed layout so the title column absorbs slack: 34px checkbox, 84px episode number, then title. Titles stay on one line with ellipsis and the meta on a second line; rows are compact (7px vertical cell padding, about 50px). Below 768px, duration, speakers, status, passages, and job columns hide; titles clamp to two lines and duration plus status restack inside the title cell.

Spacing runs on a 4px base (s-1 to s-12); 8, 12, 16, and 20px carry most gaps.

## Elevation & Depth

Flat. There are no drop shadows. Depth comes from three tonal layers (sunk surface, ground, paper) and from 1px edges: hairline borders on modules and rows, and `inset 0 0 0 1px` rings for the selected conversation (line colour) and for the lifted reference or active transcript segment (magenta). Modal dialogs dim the page with a 45% ink scrim, not a shadow.

### Shadow Vocabulary
- **Selection ring** (`box-shadow: inset 0 0 0 1px var(--line)`): active conversation item.
- **Live ring** (`box-shadow: inset 0 0 0 1px var(--cite-live)`): lifted reference, active transcript segment.
- **Focus ring** (`box-shadow: 0 0 0 2px var(--ground), 0 0 0 4px var(--cite-live)`): every `:focus-visible`, replacing the outline.

### Named Rules
**The Ring Not Shadow Rule.** If something needs to stand forward, give it a 1px ring and a tonal fill. Blur shadows, gradients, and glass do not exist here.

## Shapes

Small, quiet corners: 3px on citation chips and reference numbers, 4px on stamps, small buttons, and timestamp buttons, 6px on buttons, inputs, modules, tables, and reference entries, 10px only on the composer and dialogs. Speaker strips are 6px tall (2px radius) when compact and 20px (4px radius, hairline) when full. Borders are 1px throughout; the only exception is the 1.5px logo square in the rail. Any side rule (blockquote) is 1px Strong Hairline.

## Components

### Buttons
Compact and quiet; the label, not the fill, carries most of them.
- **Shape:** gently rounded (6px); small variant 4px.
- **Default:** paper fill, ink text, 1px Strong Hairline border, 7px by 12px padding, 0.8125rem semibold.
- **Primary:** Ink Indigo fill and border with white text; hover deepens to accent-hover.
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
- **Background:** paper on ground; sunk lavender for side panels and selection bars.
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
Indigo top bar (52px) across every page: 28px serif monogram plus "Pods" wordmark (links home), then Chat / Library / Jobs as icon-and-label links in muted shell lavender; the active section turns shell ink with a 2px underline rule flush with the bar's bottom edge. A right-hand slot holds page actions (Chat's "Conversations" menu, which drops a 360px panel below the bar). No side rails. Below 768px the wordmark hides; below 420px link icons hide.

### Home Hero (signature)
The indigo shell continues from the top bar into a full-width hero: serif "Ask your podcasts." at clamp(2.75rem, 6.2vw, 5.25rem), a one-line library summary in shell lavender, and a 58px paper ask field with an indigo Ask button. Behind it, speaker tapes: one row per recently indexed episode, each turn a rounded block at its exact duration in the tape colours (--tape-s0..3), drifting horizontally at different slow speeds and masked to fade behind the text. Rows are generated stand-ins until the library has episodes; reduced motion holds them still.

### Icons
Authored inline SVGs from a single module (`components/Icons.tsx`), 12 to 18px, stroke in currentColor.

## Do's and Don'ts

### Do:
- **Do** consume colours, type, space, radius, and motion only through the custom properties in `styles/tokens.css`; components never hard-code colour.
- **Do** reserve Citation Magenta (cite-live) for the live/focused citation and the focus ring; resting chips use cite-bg / cite-ink.
- **Do** keep state stamps in the indigo, blue, and violet family, with state-failed red only for failure.
- **Do** set every number in tabular numerals.
- **Do** set reading text in Source Serif 4 at a 68ch measure and all UI in Source Sans 3.
- **Do** separate modules with 1px hairlines and lift with 1px rings plus tonal fills.
- **Do** align Episode player, summary, and transcript to one column (56px gutter plus 68ch) and open each transcript line with the speaker name.
- **Do** keep Library rows compact and one-line (title with meta beneath), restacking duration and status into the title cell below 768px.
- **Do** use authored SVG icons from `components/Icons.tsx`.
- **Do** use the shared motion: ease-out `cubic-bezier(0.16, 1, 0.3, 1)` at 120ms for controls and 220ms for citation lift and dimming, collapsed under reduced motion.

### Don't:
- **Don't** use emojis or unicode glyphs as icons anywhere.
- **Don't** use amber or green, for states or for anything else.
- **Don't** give any element other than the live citation and the focus ring the magenta citation hue.
- **Don't** place eyebrow or kicker labels above headings.
- **Don't** use coloured border-left or border-right rules thicker than 1px.
- **Don't** use drop shadows, gradients, or glass; 1px rings only.
- **Don't** build chat as a centered column of grey bubbles with source pills.
- **Don't** use podcast logos or branding as the app's identity.
