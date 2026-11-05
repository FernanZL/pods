---
version: 1
slug: "frontend-src-pages-chatpage-tsx"
primary_target: "frontend/src/pages/ChatPage.tsx"
related_targets: ["frontend/src/pages/LibraryPage.tsx","frontend/src/pages/EpisodePage.tsx","frontend/src/pages/JobsPage.tsx"]
---

# Surface brief: Pods web app (Chat home, Library, Episode, Jobs)

Mode: Operate. Build path: code-led (no image generation).
Audience/job: one owner chatting over a locally built podcast library; occasional bulk-processing sessions in Library.
Constraints: no emojis anywhere; follow-system light and dark; WCAG 2.2 AA; cost confirmation before any paid step.

## Direction contract
THESIS: Every answer is a cited paragraph with its reference list beside it, the way a research paper holds its sources. Refuses the centered chat column with grey bubbles and source pills.
OWN-WORLD: Deep indigo shell rail (#261A57) on lavender-white ground (#F8F7FC), ink #17142A; magenta (#E0569F) reserved for the live/focused citation; pale-pink citation chips; speakers coded blue/magenta/violet/teal. Source Serif 4 for answer prose and episode titles, Source Sans 3 for all UI, tabular numerals for every time and count. Hairline module borders, 6px radii, no shadows beyond 1px rings. Dark: ground #13111C, rail #1A1338.
STORY: The owner asks, reads a cited answer, checks who said it and when, and jumps to that moment; or builds the library by selecting many episodes and confirming the cost.
FIRST VIEWPORT: Indigo rail (Chat, Library, Jobs) far left; conversation list 280px; centre: index strip (episodes · passages · hours · scope picker), question as a heading line, serif answer with numbered superscript markers, composer pinned bottom; right 380px References column, each entry aligned with episode title, speaker strip, speaker · timestamps · Ep. number. Signature move: focusing a marker lifts its reference in magenta and dims the rest; references carry duration-exact speaker strips. Raises: hairline density in Library (japanese-high-density-web); focus-dims-others (streaming wall); catalog numbers first (saville); exact-duration strips (labanotation); stamped persistent states (ticket wallet); tabular numerals (ikeda).
FORM: Reference Apparatus, grounded candidate 7 of 7, palette re-pinned by the user to indigo/magenta. seed:e3d8f168320e92c8
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
