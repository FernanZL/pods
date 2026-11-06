---
version: 1
slug: "frontend-src-pages-homepage-tsx"
primary_target: "frontend/src/pages/HomePage.tsx"
related_targets: ["frontend/src/pages/HomePage.css"]
---

# Home (/)

Scope: the app's front page. Visitor mode: Persuade (the owner opening their own tool; "something cool when I enter"), balanced mix of ask, collection and recent activity.

Audience and job: one person returning to their local podcast library. On arrival they should see what they have collected (episodes, books), be able to ask a question immediately, and pick up a chat or see running work.

Constraints: real data only; demo states labelled; no podcast branding as Pods identity (show artwork appears only as duotoned posters of that show); costs never triggered from here.

## Direction contract

THESIS: The library is a record shop. Episodes are sleeves in a crate, podcasts are hand-lettered divider cards, books are new arrivals at the counter, and asking is a word with the clerk. It refuses the SaaS hero (headline, search box, three columns) the old home shipped.

OWN-WORLD: Slate shop wall (#36435f) with faint panel seams, near-black crate (#131418), marigold divider cards and record labels (#f4b33e), coral price stickers (#ff8a7a), off-white counter paper (#f3f2ee). Anton shop-sign caps for headings, Archivo for text, Permanent Marker only on divider cards and the staff-pick card. Taped duotone posters, dashed hold slips, a square record sleeve whose art is the episode's conversation drawn as a spiral groove coloured by speaker.

STORY: The visitor sees everything they have collected at a glance, reads a real verified line on the staff-pick card, flips through the crate, opens a book, or asks the counter a question that lands in Chat with citations.

FIRST VIEWPORT: Desktop splits into the wall (left, ~55%) and the counter (right). Wall: headline "Dig through everything you've heard." top-left with a one-line lede; two taped duotone posters and the staff-pick card top-right of the wall; the crate along the bottom with the newest transcribed episode face-out (groove art, episode number large, duration sticker), sealed sleeves for untranscribed episodes behind, divider tabs per podcast, flip controls. Counter: "New in: books" with up to three real covers first, then "Ask the counter" with the ask field and Ask button (primary action), then On hold (latest chat) and Back room (running job or nothing processing).

FORM: Browse Bins, assigned index 6 of the ordered grounded list (record shop browse bins), seed:0b57bebe44c976b4. Raises kept: name and number in one label system (loteria); scarce live motion, only a running job moves (BBS); two faces plus marker for handwriting (phosphor); an empty margin around the ask field (accretion); crate order is time, newest face-out (deep dive). Signature interaction: flipping the crate (arrow buttons or arrow keys) tips the front sleeve back and brings the next forward.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
