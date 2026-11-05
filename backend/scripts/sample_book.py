"""Render the hand-written sample book (demo episode, no model calls) with several design seeds.

    uv run python -m scripts.sample_book <transcript.json> <out_dir> [seed ...]

Useful to preview the theme range. All quotes go through the real verifier.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.books.document import (
    Book,
    Callout,
    Chapter,
    Heading,
    Paragraph,
    PullQuote,
    QuotePair,
    SpeakerFigure,
)
from app.books.render import render_pdf
from app.books.theme import make_theme
from app.books.verify import find_quote, resolve_runs
from app.domain import Transcript
from app.storage import read_transcript

CHAPTERS = [
    dict(
        label="Part one",
        title="Two clocks, one night",
        start=15,
        end=99,
        dek="Why the night you are going to have is mostly decided in the first hour after you wake up.",
        opener="That morning light pulse sets an early cortisol peak and starts a timer for evening melatonin release.",
        blocks=[
            (
                "p",
                "Sleep feels like one thing, a switch you flip at night. The conversation starts by taking that idea apart. There are, the guest explains, two systems pulling on you at once: a pressure that builds the longer you stay awake, and a clock that keeps its own time whether you are tired or not. ⟦Sleep is governed by two interacting processes⟧, and most bad nights come from the two falling out of step.",
            ),
            (
                "p",
                "The pressure half has a name, adenosine, and it will matter in the next part. The clock half is where the morning comes in. It is easy to think of the clock as something that lives at bedtime, but the episode keeps pulling the story back to the start of the day, to a moment most people spend half awake, reaching for a phone.",
            ),
            ("h", "The morning anchor"),
            (
                "p",
                "The host frames it as a puzzle: why would light at seven in the morning have anything to do with falling asleep sixteen hours later? The answer is a set of cells in the eye that do not help you see at all. They exist to measure brightness and report it to the body's master clock, and their verdict starts a countdown.",
            ),
            (
                "pull",
                "Specialized retinal ganglion cells detect bright morning sky light and signal the master circadian pacemaker.",
            ),
            (
                "p",
                "That countdown is the point. A strong signal early means melatonin arrives on schedule in the evening. A weak or missing signal leaves the clock guessing, and a guessing clock is how you end up wide awake at midnight with nothing obviously wrong. The guest is careful to describe it as timing rather than willpower: nothing about the evening can fully make up for a morning the clock never registered.",
            ),
            ("h", "Glass is not the sky"),
            (
                "p",
                "The obvious shortcut, sitting by a bright window or scrolling a bright phone, does not count for much. ⟦Window glass filters a large fraction of the relevant irradiance⟧, which is why the guest's advice is so concrete: ten minutes outside when the sky is clear, closer to twenty when it is overcast. It is less a wellness ritual than a dose, and the dose depends on the weather.",
            ),
            (
                "pair",
                "Does looking through a living room window or staring at a phone screen give the same circadian signal?",
                "stepping outside for ten minutes on a clear morning or twenty minutes under overcast skies is far more effective.",
            ),
            (
                "p",
                "What makes the exchange useful is how ordinary the fix is. There is no device to buy and no protocol to memorise, only a door to walk through at roughly the same time each day.",
            ),
        ],
    ),
    dict(
        label="Part two",
        title="The caffeine debt",
        start=99,
        end=166,
        dek="Feeling sleepy and getting deep sleep turn out to be two very different things.",
        opener="Falling asleep is not the same as achieving deep non-REM slow-wave stages.",
        blocks=[
            (
                "p",
                "If the clock is one half of the system, adenosine is the other. It accumulates through the day like sand in an hourglass, and the heavier it gets the more you want to sleep. ⟦Adenosine builds steadily while you are awake⟧, the guest says, and that steady build is the pressure that lets a long day end in a deep night.",
            ),
            (
                "p",
                "Caffeine does not remove that pressure. It hides it. The molecule sits on the same receptors adenosine would use and blocks the message, while the adenosine itself stays exactly where it was. When the caffeine wears off, the debt is still due, and it tends to arrive at the least convenient moment.",
            ),
            (
                "pull",
                "Caffeine competitively blocks adenosine receptors without clearing the molecule",
            ),
            (
                "p",
                "The part that makes this a problem rather than a curiosity is timing. With a half-life of five to seven hours, a coffee at four in the afternoon is still half active late in the evening. People notice they can fall asleep anyway and conclude they are immune. The episode argues the opposite: the damage is not in falling asleep, it is in how deep the sleep gets once you are there.",
            ),
            (
                "callout",
                "From the episode: protecting deep sleep",
                [
                    "Set a caffeine cutoff eight to ten hours before your usual bedtime.",
                    'Treat "I can sleep after espresso" as a measure of falling asleep, not of sleep quality.',
                    "Move late coffees earlier before cutting them out entirely.",
                ],
            ),
            (
                "p",
                "The host's summary question lands the point, and the guest's answer is the line that sticks. Measured on the brain, caffeine still active at midnight shows up as shallower slow waves, even in people who swear they slept fine: ⟦Electroencephalography shows reduced slow-wave amplitude when caffeine remains active at midnight.⟧",
            ),
        ],
    ),
    dict(
        label="Part three",
        title="Where REM lives",
        start=166,
        end=268,
        dek="Why the last two hours of the night are not the optional ones.",
        opener="losing two hours at the tail end can remove half of your nightly REM quota",
        blocks=[
            (
                "p",
                "A night is not one long block. It runs in cycles of roughly ninety minutes, and the cycles are not identical. Early in the night they lean toward deep slow-wave sleep, the kind associated with repair and clearance. Later they tilt toward REM, the dreaming stage. ⟦the final third of the night is dominated by REM sleep⟧, which is where emotional and procedural memory gets consolidated.",
            ),
            (
                "fig",
                166,
                268,
                "<b>Who spoke when, 2:46 to 4:28.</b> Each mark is one turn at its exact length. The guest carries this stretch of the conversation.",
            ),
            (
                "p",
                "That asymmetry has an uncomfortable consequence, and the host spells it out: if you cut a night from eight hours to six, you are not trimming evenly. You are taking the end, and the end is mostly REM. The cost does not show up as tiredness so much as a flatter, more irritable, less inventive next day.",
            ),
            ("pull", "losing two hours at the tail end can remove half of your nightly REM quota"),
            ("h", "The evening half of the clock"),
            (
                "p",
                "The other lever is light again, this time in the evening. After dusk the clock becomes more sensitive, not less, which means bright overhead lighting at ten at night lands harder than the same light at noon. The guest's fix is low and simple: ⟦Dimming lamps low in the room and reducing bright blue-enriched screens prevents melatonin suppression.⟧",
            ),
        ],
    ),
    dict(
        label="Part four",
        title="Cooling down, waking up",
        start=268,
        end=10_000,
        dek="Temperature, naps, the three a.m. problem, and the one habit worth keeping.",
        opener="Consistency stabilizes circadian phase better than weekend catch-up sleep.",
        blocks=[
            (
                "p",
                "The last stretch of the episode turns practical. To start sleeping, the body's core temperature has to drop by about a degree, and the bedroom can help or fight that. The guest suggests cool air, around eighteen degrees, and then adds the counterintuitive part: a warm shower before bed.",
            ),
            (
                "p",
                "It sounds backwards, and the host says so. The explanation is that warmth pulls blood to the surface. ⟦Once you step out into cooler air, heat radiates rapidly from the extremities and core temperature falls.⟧ The shower is not warming you up for bed; it is opening the radiators.",
            ),
            ("h", "Naps and the middle of the night"),
            (
                "p",
                "Short naps get a qualified yes: about twenty minutes, before mid-afternoon, is enough to restore alertness without spending the adenosine you will want later. Long naps late in the day are the ones that push bedtime back.",
            ),
            (
                "p",
                "For waking at three in the morning with a busy head, the advice is about protecting the association between bed and sleep. Do not check the clock. If you are still awake after twenty minutes, ⟦sit in dim light reading a calm paper book until sleepiness returns⟧, and only then go back.",
            ),
            (
                "pull",
                "Anchor a consistent wake time within a thirty-minute window seven days a week",
            ),
            (
                "p",
                "Asked for a single habit, the guest does not pick a supplement or a gadget. The answer is the most boring one available, and the episode makes a good case that it is also the strongest: wake at the same time every day, weekends included, and get outside soon after.",
            ),
        ],
    ),
]


def build_book(tr: Transcript) -> Book:
    chapters: list[Chapter] = []
    rejected: list[str] = []
    end_of_talk = tr.segments[-1].end
    for c in CHAPTERS:
        blocks = []
        for b in c["blocks"]:
            kind = b[0]
            if kind == "p":
                runs, bad = resolve_runs(tr, b[1])
                rejected += bad
                blocks.append(Paragraph(runs))
            elif kind == "h":
                blocks.append(Heading(b[1]))
            elif kind == "pull":
                blocks.append(PullQuote(find_quote(tr, b[1])))
            elif kind == "pair":
                blocks.append(QuotePair(find_quote(tr, b[1]), find_quote(tr, b[2])))
            elif kind == "callout":
                blocks.append(Callout(b[1], b[2]))
            elif kind == "fig":
                blocks.append(SpeakerFigure(b[1], b[2], b[3]))
        chapters.append(
            Chapter(
                label=c["label"],
                title=c["title"],
                dek=c["dek"],
                start=c["start"],
                end=min(c["end"], end_of_talk),
                opener=find_quote(tr, c["opener"]),
                blocks=blocks,
            )
        )
    if rejected:
        raise SystemExit(f"unverified quotes: {rejected}")
    return Book(
        title="The Morning Anchor",
        title_accent="Anchor",
        deck="How light, adenosine and a cooler room build a night of deep sleep. A feature drawn "
        "from one conversation, with every quote taken from the recording.",
        podcast_title="Demo Podcast",
        episode_number=1,
        episode_title="Sleep Architecture and Circadian Alignment",
        speakers=[tr.speakers.get(k, k) for k in dict.fromkeys(s.speaker for s in tr.segments)],
        duration=end_of_talk,
        chapters=chapters,
        closing=find_quote(
            tr, "Consistency stabilizes circadian phase better than weekend catch-up sleep."
        ),
        demo=True,
    )


def main() -> None:
    tr = read_transcript(Path(sys.argv[1]))
    out = Path(sys.argv[2])
    args = sys.argv[3:]
    artwork = None
    if args and args[0].startswith("--artwork="):
        artwork = Path(args.pop(0).split("=", 1)[1])
    seeds = [int(s) for s in args] or [7]
    book = build_book(tr)
    for seed in seeds:
        theme = make_theme(seed)
        path = render_pdf(
            book, tr.segments, theme, out / f"sample-seed-{seed}.pdf", artwork=artwork
        )
        print(
            f"seed {seed}: {theme.family}, art={theme.art}, {theme.fonts.name}, "
            f"tapes={theme.tape_style}, cover={theme.cover_layout}, "
            f"opener={theme.opener_style}, primary={theme.palette.primary} accent={theme.palette.accent} "
            f"-> {path.name}"
        )


if __name__ == "__main__":
    main()
