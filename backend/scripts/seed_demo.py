"""Seed an offline fictional Demo Podcast with 3 diarized episodes and index them.

Usage:
    uv run python -m scripts.seed_demo
    uv run python -m scripts.seed_demo --allow-paid
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import select

from app import db, storage
from app.config import get_settings
from app.domain import Segment, Transcript
from app.models import Episode, Podcast, utcnow
from app.services import indexing

DEMO_PODCAST_TITLE = "Demo Podcast"
DEMO_PODCAST_RSS = "demo://podcast"
DEMO_SPEAKERS: dict[str, str] = {"A": "Host", "B": "Guest"}


@dataclass(frozen=True)
class _DemoEpisodeSpec:
    number: int
    guid: str
    title: str
    description: str
    published: datetime
    turns: list[tuple[str, float, float, str]]


_SLEEP_TURNS: list[tuple[str, float, float, str]] = [
    (
        "A",
        0.0,
        14.5,
        "Welcome to this fictional demo episode on sleep architecture and circadian alignment. "
        "Today our guest walks through practical habits for restorative sleep.",
    ),
    (
        "B",
        15.0,
        32.0,
        "Glad to be here on the demo show. Sleep is governed by two interacting processes: "
        "homeostatic sleep pressure from adenosine accumulation and the twenty-four-hour "
        "circadian clock.",
    ),
    (
        "A",
        32.6,
        45.0,
        "Let us start with the morning anchor. Why does outdoor daylight shortly after waking "
        "matter so much for falling asleep sixteen hours later?",
    ),
    (
        "B",
        45.5,
        66.0,
        "Specialized retinal ganglion cells detect bright morning sky light and signal the "
        "master circadian pacemaker. That morning light pulse sets an early cortisol peak and "
        "starts a timer for evening melatonin release.",
    ),
    (
        "A",
        66.5,
        79.0,
        "Does looking through a living room window or staring at a phone screen give the same "
        "circadian signal?",
    ),
    (
        "B",
        79.6,
        98.5,
        "Window glass filters a large fraction of the relevant irradiance, so stepping outside "
        "for ten minutes on a clear morning or twenty minutes under overcast skies is far more "
        "effective.",
    ),
    (
        "A",
        99.0,
        112.0,
        "Now let us talk about adenosine and caffeine. How does caffeine interact with sleep "
        "pressure across the afternoon?",
    ),
    (
        "B",
        112.6,
        133.0,
        "Adenosine builds steadily while you are awake. Caffeine competitively blocks adenosine "
        "receptors without clearing the molecule, and because its half-life is five to seven "
        "hours, late afternoon coffee fragments deep slow-wave sleep.",
    ),
    (
        "A",
        133.5,
        146.5,
        "So setting a caffeine cutoff eight to ten hours before bedtime protects slow-wave sleep "
        "architecture even if someone feels they can fall asleep after espresso?",
    ),
    (
        "B",
        147.0,
        166.0,
        "Exactly. Falling asleep is not the same as achieving deep non-REM slow-wave stages. "
        "Electroencephalography shows reduced slow-wave amplitude when caffeine remains active at "
        "midnight.",
    ),
    (
        "A",
        166.6,
        180.0,
        "What happens across a typical ninety-minute ultradian sleep cycle between slow-wave "
        "sleep and REM dreaming?",
    ),
    (
        "B",
        180.5,
        201.0,
        "Early night cycles are rich in deep slow-wave sleep, supporting metabolic clearance and "
        "tissue repair, whereas the final third of the night is dominated by REM sleep, which "
        "consolidates emotional and procedural memory.",
    ),
    (
        "A",
        201.6,
        214.5,
        "That explains why cutting sleep from eight hours to six hours disproportionately trims "
        "REM sleep in the early morning.",
    ),
    (
        "B",
        215.0,
        233.5,
        "Right, losing two hours at the tail end can remove half of your nightly REM quota, "
        "leaving mood regulation and creative problem solving noticeably impaired the next day.",
    ),
    (
        "A",
        234.0,
        247.5,
        "How does evening artificial lighting affect melatonin onset in the two hours before bed?",
    ),
    (
        "B",
        248.0,
        268.0,
        "After dusk the circadian system becomes extra sensitive to overhead bright light. "
        "Dimming lamps low in the room and reducing bright blue-enriched screens prevents "
        "melatonin suppression.",
    ),
    (
        "A",
        268.6,
        282.0,
        "Thermal regulation comes up frequently too. Why does a cool bedroom help people initiate "
        "and maintain sleep?",
    ),
    (
        "B",
        282.5,
        302.5,
        "Core body temperature needs to drop by roughly one degree Celsius to initiate sleep. "
        "Keeping bedroom air cool around eighteen degrees Celsius and taking a warm shower before "
        "bed accelerates peripheral heat dumping.",
    ),
    (
        "A",
        303.0,
        316.5,
        "How does a warm shower cool the core? That always sounds counterintuitive at first.",
    ),
    (
        "B",
        317.0,
        336.0,
        "Warm water dilates blood vessels in the hands, feet, and skin surface. Once you step "
        "out into cooler air, heat radiates rapidly from the extremities and core temperature "
        "falls.",
    ),
    (
        "A",
        336.6,
        350.0,
        "What about daytime naps for listeners who had a short night? Do naps hurt nighttime "
        "sleep latency?",
    ),
    (
        "B",
        350.5,
        369.5,
        "A brief twenty-minute nap before mid-afternoon refreshes alertness without venting too "
        "much adenosine, whereas ninety-minute naps late in the afternoon can delay bedtime.",
    ),
    (
        "A",
        370.0,
        383.5,
        "And if someone wakes at three in the morning with racing thoughts, what behavioral "
        "strategy works best?",
    ),
    (
        "B",
        384.0,
        403.5,
        "Avoid checking bright clocks. If wakefulness lasts past twenty minutes, sit in dim light "
        "reading a calm paper book until sleepiness returns so the bed stays associated with "
        "sleep rather than frustration.",
    ),
    (
        "A",
        404.0,
        416.5,
        "What single habit gives the highest return if someone can only change one thing this "
        "week?",
    ),
    (
        "B",
        417.0,
        436.0,
        "Anchor a consistent wake time within a thirty-minute window seven days a week and pair "
        "it with outdoor morning sunlight. Consistency stabilizes circadian phase better than "
        "weekend catch-up sleep.",
    ),
]

_DOPAMINE_TURNS: list[tuple[str, float, float, str]] = [
    (
        "A",
        0.0,
        15.0,
        "Welcome back to our fictional demo podcast. In episode two we unpack dopamine dynamics, "
        "reward prediction error, and sustainable daily motivation.",
    ),
    (
        "B",
        15.5,
        34.0,
        "Happy to join. People often call dopamine the pleasure molecule, yet in neuroscience "
        "dopamine primarily encodes anticipation, salience, craving, and the willingness to "
        "invest effort toward goals.",
    ),
    (
        "A",
        34.6,
        48.0,
        "Could you distinguish tonic baseline dopamine from phasic dopamine spikes for our "
        "listeners?",
    ),
    (
        "B",
        48.5,
        69.0,
        "Tonic dopamine is the steady background concentration circulating in striatal circuits "
        "that sets your general drive and readiness to act. Phasic bursts are rapid spikes above "
        "baseline triggered by unexpected cues or rewards.",
    ),
    (
        "A",
        69.6,
        83.0,
        "What happens right after a very tall phasic dopamine spike from intense novelty or "
        "layered stimulation?",
    ),
    (
        "B",
        83.5,
        104.0,
        "Homeostatic opponent processes pull tonic dopamine temporarily below the prior baseline. "
        "That post-spike trough feels like restlessness, boredom, or craving to repeat the "
        "stimulus.",
    ),
    (
        "A",
        104.6,
        118.5,
        "How does reward prediction error shape whether dopamine rises or drops when an outcome "
        "arrives?",
    ),
    (
        "B",
        119.0,
        140.0,
        "Dopamine neurons compare expected reward against actual reward. Better-than-expected "
        "outcomes produce a positive spike, expected outcomes produce modest activity, and "
        "disappointment drops firing below baseline.",
    ),
    (
        "A",
        140.6,
        154.0,
        "Why does stacking multiple high-stimulation inputs at once—like loud music, social "
        "feeds, and sugary snacks during work—backfire over several days?",
    ),
    (
        "B",
        154.5,
        175.0,
        "Stacking cues inflates the artificial peak required just to feel engaged, blunting "
        "sensitivity so ordinary meaningful work feels flat and unrewarding by comparison.",
    ),
    (
        "A",
        175.6,
        189.0,
        "That connects to intermittent reinforcement. How can someone use variable rewards "
        "constructively rather than getting hooked on slot-machine scrolling?",
    ),
    (
        "B",
        189.5,
        209.5,
        "Avoid celebrating every routine session with extravagant external rewards. Keeping "
        "external rewards occasional preserves sensitivity while training you to value the "
        "activity itself.",
    ),
    (
        "A",
        210.0,
        223.5,
        "Let us talk about effort mindset. Can framing hard cognitive or physical friction as "
        "valuable alter motivation circuits?",
    ),
    (
        "B",
        224.0,
        244.5,
        "Yes, associating the strain of focused effort itself with progress recruits prefrontal "
        "regulation over mesolimbic pathways, sustaining drive without needing constant external "
        "prizes.",
    ),
    (
        "A",
        245.0,
        258.0,
        "What role does Novelty play when procrastination hits at the start of a deep focus block?",
    ),
    (
        "B",
        258.5,
        278.5,
        "Procrastination often seeks micro-doses of novelty—checking inbox tabs—to escape initial "
        "task friction. Starting with five distraction-free minutes lets task momentum build.",
    ),
    (
        "A",
        279.0,
        292.5,
        "Does deliberate boredom or low-stimulation walks help restore baseline motivation?",
    ),
    (
        "B",
        293.0,
        312.5,
        "Unplugged walks without podcasts or scrolling let tonic dopamine replenish gradually, "
        "making ordinary creative work feel engaging again afterward.",
    ),
    (
        "A",
        313.0,
        326.5,
        "How closely tied are sleep deprivation and dopamine receptor availability?",
    ),
    (
        "B",
        327.0,
        346.5,
        "Brain imaging studies indicate acute sleep loss downregulates striatal D2 and D3 "
        "receptor availability, increasing impulsivity toward quick rewards while lowering "
        "appetite for sustained effort.",
    ),
    (
        "A",
        347.0,
        360.5,
        "What about cold water immersion or brisk morning movement that people discuss for "
        "alertness?",
    ),
    (
        "B",
        361.0,
        380.5,
        "Brief controlled stressors like brisk outdoor movement or cool water trigger a gradual, "
        "sustained rise in catecholamines—norepinephrine and dopamine—without a sharp crash.",
    ),
    (
        "A",
        381.0,
        394.0,
        "How should listeners structure ninety-minute work blocks around these motivation "
        "principles?",
    ),
    (
        "B",
        394.5,
        414.0,
        "Remove phone cues into another room, accept the first ten minutes of agitation as normal "
        "ramp-up friction, then take a low-stimulation visual break afterward rather than "
        "doomscrolling.",
    ),
    (
        "A",
        414.6,
        426.5,
        "Could you summarize one takeaway for protecting baseline drive across the week?",
    ),
    (
        "B",
        427.0,
        446.0,
        "Guard your baseline by spacing out intense dopamine spikes, sleeping consistently, and "
        "anchoring satisfaction to disciplined effort rather than purely to final milestones.",
    ),
]

_EXERCISE_TURNS: list[tuple[str, float, float, str]] = [
    (
        "A",
        0.0,
        14.5,
        "Welcome to episode three of our fictional demo podcast, where we explore cardiovascular "
        "endurance, VO2 max conditioning, and progressive resistance training.",
    ),
    (
        "B",
        15.0,
        33.5,
        "Great to be back. Longevity and physical performance rest on complementary pillars: "
        "aerobic metabolic efficiency, peak cardiorespiratory capacity, muscular strength, and "
        "movement stability.",
    ),
    (
        "A",
        34.0,
        47.5,
        "Listeners hear a lot about zone two cardio. How do you define zone two intensity without "
        "a laboratory lactate meter?",
    ),
    (
        "B",
        48.0,
        68.5,
        "Zone two is the highest steady output where mitochondrial fat oxidation clears lactate "
        "as fast as muscles produce it. Practically, you can speak full sentences with slight "
        "breathiness—the conversational pace test.",
    ),
    (
        "A",
        69.0,
        82.0,
        "What cellular adaptations come from accumulating three hours of zone two aerobic work "
        "each week?",
    ),
    (
        "B",
        82.5,
        103.0,
        "Sustained zone two training expands capillary networks around slow-twitch fibers, boosts "
        "mitochondrial density, and increases monocarboxylate transporters that recycle lactate "
        "efficiently.",
    ),
    (
        "A",
        103.6,
        117.0,
        "How does high-intensity VO2 max interval training complement that steady aerobic base?",
    ),
    (
        "B",
        117.5,
        138.0,
        "While zone two builds peripheral mitochondrial efficiency, four-minute intervals near "
        "maximal heart rate challenge cardiac stroke volume and oxygen delivery, raising your "
        "VO2 max ceiling.",
    ),
    (
        "A",
        138.6,
        152.0,
        "What work-to-rest structure works well for a weekly VO2 max session on a bike, rower, "
        "or track?",
    ),
    (
        "B",
        152.5,
        172.5,
        "Four to six repeats of three to four minutes at hard sustainable pace separated by "
        "three minutes of easy spinning works remarkably well once a week after a thorough "
        "warm-up.",
    ),
    (
        "A",
        173.0,
        186.5,
        "Switching to resistance training: how do strength adaptations differ from muscle "
        "hypertrophy?",
    ),
    (
        "B",
        187.0,
        207.5,
        "Maximal strength relies heavily on neural motor-unit recruitment at heavier loads of "
        "three to six reps, whereas muscle hypertrophy responds across five to twenty reps "
        "whenever sets approach muscular fatigue.",
    ),
    (
        "A",
        208.0,
        221.5,
        "What does progressive overload look like safely over months without joint overuse?",
    ),
    (
        "B",
        222.0,
        242.0,
        "Progress gradually by adding one repetition per set or two to five percent load while "
        "keeping controlled eccentric lowering and leaving one to two repetitions in reserve on "
        "most sets.",
    ),
    (
        "A",
        242.6,
        256.0,
        "Does combining endurance cardio and lifting in the same week cause an interference "
        "effect?",
    ),
    (
        "B",
        256.5,
        276.5,
        "For recreational athletes interference is minimal if sessions are separated by six hours "
        "or placed on alternating days, and if total caloric and protein intake matches energy "
        "expenditure.",
    ),
    (
        "A",
        277.0,
        290.5,
        "How many weekly working sets per major muscle group represent a solid target for "
        "strength and muscle maintenance?",
    ),
    (
        "B",
        291.0,
        310.5,
        "Ten to fifteen hard sets per muscle group per week split across two sessions captures "
        "the majority of hypertrophy gains while allowing connective tissue recovery.",
    ),
    (
        "A",
        311.0,
        324.5,
        "What role do electrolytes, hydration, and post-training nutrition play in recovery?",
    ),
    (
        "B",
        325.0,
        345.0,
        "Fluid and sodium replacement preserve plasma volume during sweat sessions, while "
        "distributing dietary protein evenly across meals supplies amino acids for myofibrillar "
        "remodeling.",
    ),
    (
        "A",
        345.6,
        359.0,
        "Sometimes palmar cooling or active walking between sets gets mentioned. Does active "
        "recovery beat passive sitting?",
    ),
    (
        "B",
        359.5,
        379.0,
        "Light walking between bouts promotes venous return and lactate clearance, and avoiding "
        "immediate icy immersion right after lifting preserves anabolic hypertrophy signaling.",
    ),
    (
        "A",
        379.6,
        393.0,
        "Why could jumping straight into an ice bath right after hypertrophy lifting blunt muscle "
        "growth?",
    ),
    (
        "B",
        393.5,
        412.5,
        "Acute local inflammation triggers satellite cell repair pathways. Aggressive cold "
        "vasoconstriction immediately post-lift dampens protein synthesis, so save cold exposure "
        "for separate days.",
    ),
    (
        "A",
        413.0,
        425.0,
        "How would you assemble a balanced, realistic weekly template for a busy listener?",
    ),
    (
        "B",
        425.5,
        445.0,
        "Aim for three zone two aerobic sessions of forty-five minutes, one brief VO2 max "
        "interval workout, and two to three full-body resistance training sessions pushing, "
        "pulling, and hinging.",
    ),
]

DEMO_EPISODES: list[_DemoEpisodeSpec] = [
    _DemoEpisodeSpec(
        number=1,
        guid="demo://podcast/ep-1",
        title="Episode 1: Sleep Architecture and Circadian Alignment",
        description=(
            "Fictional demo discussion covering circadian light timing, adenosine and caffeine, "
            "bedroom thermal regulation, and ultradian REM and slow-wave sleep cycles."
        ),
        published=datetime(2026, 1, 10, 8, 0, tzinfo=UTC),
        turns=_SLEEP_TURNS,
    ),
    _DemoEpisodeSpec(
        number=2,
        guid="demo://podcast/ep-2",
        title="Episode 2: Dopamine Dynamics, Reward, and Sustained Motivation",
        description=(
            "Fictional demo discussion covering tonic baseline dopamine, phasic spikes, reward "
            "prediction error, effort mindset, and distraction-free focus blocks."
        ),
        published=datetime(2026, 1, 17, 8, 0, tzinfo=UTC),
        turns=_DOPAMINE_TURNS,
    ),
    _DemoEpisodeSpec(
        number=3,
        guid="demo://podcast/ep-3",
        title="Episode 3: Aerobic Endurance, VO2 Max, and Resistance Training",
        description=(
            "Fictional demo discussion covering zone two aerobic conditioning, VO2 max intervals, "
            "progressive resistance training, and recovery."
        ),
        published=datetime(2026, 1, 24, 8, 0, tzinfo=UTC),
        turns=_EXERCISE_TURNS,
    ),
]


def seed_demo(*, allow_paid: bool = False) -> Podcast:
    """Create or update the Demo Podcast with 3 episodes and index them idempotently."""
    settings = get_settings()
    if settings.embeddings_provider != "fake" and not allow_paid:
        raise RuntimeError(
            "Refusing to run seed_demo when EMBEDDINGS_PROVIDER is not 'fake'. "
            "Pass --allow-paid to index demo episodes with a paid embeddings provider."
        )

    settings.ensure_dirs()
    db.init_db()
    now = utcnow()

    episode_ids: list[int] = []
    with db.session_scope() as session:
        podcast = session.exec(select(Podcast).where(Podcast.rss_url == DEMO_PODCAST_RSS)).first()
        if podcast is None:
            podcast = Podcast(
                title=DEMO_PODCAST_TITLE,
                rss_url=DEMO_PODCAST_RSS,
                slug=storage.slugify(DEMO_PODCAST_TITLE),
                description=(
                    "Fictional offline demo podcast covering sleep, motivation, and exercise."
                ),
                refreshed_at=now,
            )
            session.add(podcast)
            session.flush()
        else:
            podcast.title = DEMO_PODCAST_TITLE
            podcast.refreshed_at = now
            session.add(podcast)
            session.flush()

        assert podcast.id is not None

        for spec in DEMO_EPISODES:
            ep = session.exec(
                select(Episode).where(
                    Episode.podcast_id == podcast.id,
                    Episode.guid == spec.guid,
                )
            ).first()
            duration_sec = int(spec.turns[-1][2]) + 5
            if ep is None:
                ep = Episode(
                    podcast_id=podcast.id,
                    guid=spec.guid,
                    number=spec.number,
                    title=spec.title,
                    slug=storage.episode_slug(spec.number, spec.title),
                    description=spec.description,
                    published=spec.published,
                    audio_url=f"{DEMO_PODCAST_RSS}/audio/{spec.number}.mp3",
                    duration_seconds=duration_sec,
                    downloaded_at=now,
                    transcribed_at=now,
                    speakers=dict(DEMO_SPEAKERS),
                )
                session.add(ep)
                session.flush()
            else:
                ep.title = spec.title
                ep.description = spec.description
                ep.published = spec.published
                ep.duration_seconds = duration_sec
                ep.downloaded_at = ep.downloaded_at or now
                ep.transcribed_at = ep.transcribed_at or now
                ep.speakers = dict(DEMO_SPEAKERS)
                session.add(ep)
                session.flush()

            assert ep.id is not None
            ep_dir = storage.episode_dir(podcast, ep)
            transcript_path = ep_dir / "transcript.json"
            segments = [
                Segment(speaker=spk, start=start, end=end, text=text)
                for spk, start, end, text in spec.turns
            ]
            transcript = Transcript(
                episode_id=ep.id,
                model="demo-handwritten",
                speakers=dict(DEMO_SPEAKERS),
                segments=segments,
            )
            storage.write_transcript(transcript_path, transcript)
            ep.transcript_path = storage.to_rel(transcript_path)
            session.add(ep)
            episode_ids.append(ep.id)

        session.commit()
        session.refresh(podcast)

    for ep_id in episode_ids:
        indexing.index_episode(ep_id, force=False)

    with db.session_scope() as session:
        refreshed = session.get(Podcast, podcast.id)
        assert refreshed is not None
        return refreshed


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for ``python -m scripts.seed_demo``."""
    parser = argparse.ArgumentParser(description="Seed Demo Podcast episodes and index them.")
    parser.add_argument(
        "--allow-paid",
        action="store_true",
        help="Allow running when EMBEDDINGS_PROVIDER is not 'fake'.",
    )
    args = parser.parse_args(argv)
    try:
        podcast = seed_demo(allow_paid=args.allow_paid)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Seeded '{podcast.title}' ({DEMO_PODCAST_RSS}) with {len(DEMO_EPISODES)} episodes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
