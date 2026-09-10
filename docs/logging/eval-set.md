# Logging eval set — thirty reports, written blind

Thirty hand-written reports with the outcome each one must produce: eighteen the
sentence determines, and twelve it does not. Written **before** the logging
agent's prompt or any of its output was seen — the same discipline as session
2's `docs/enrichment/reference-set.md`, and for the same reason: a set written
afterwards measures how well the author rationalises output they have already
read.

**What was consulted while writing this file**: `src/trainer/log.py` (the
document shape, the three provenance values, what adherence fills in, what is
refused and what is only flagged), `src/trainer/engine/exclusions.py`
(`classify` and the two granularities), `CONTEXT.md`, `ROADMAP.md` § Session 5,
`docs/work/05-logging-by-deviation/issues/05-the-measurement.md`,
`docs/enrichment/reference-set.md` as the format precedent, and the catalog
itself in `trainer.sqlite` through read-only queries. **What was not**:
`src/trainer/agent.py`, any run record, anything under a scratchpad or temp
directory, `git log` / `show` / `diff`, and no command that reaches a model —
`trainer log` and `trainer eval` were never run. The confirmation at the end of
this file restates that in full.

The reports are in **Italian** and everything around them is English. That is
ROADMAP.md § Session 5's own decision: they are fixtures, not documentation, and
an eval over English sentences would measure a system nobody uses.

---

## How to read a row

Each row carries the report verbatim, the expected outcome, and a **note**
saying which words in the report the expected answer rests on. A row the author
is genuinely unsure about is marked **`?`** with the doubt stated — an honest
`?` is worth more than a confident guess, because a reviewer can settle it in a
second.

**The expected `report` is the blockquote**, verbatim, and it is not repeated
inside the JSON below it. `PerformedWorkout.report` is a required field and the
agent must emit the user's own words exactly; the runner reads them off the
blockquote rather than from a copy, because two copies of the same sentence in
one row is one copy that can be edited without the other.

**Only the deviations are written.** Adherence is the engine's job: what the
report does not mention was performed as prescribed and is filled in by
`log.to_performed` with a provenance of `assumed`. An expected document that
restates the unchanged parts is wrong about what the agent should emit.

**Volume is rounds performed**, over the *resolved* workout — what the report
said plus everything adherence filled in, which is what gets written and what
`workout_volume` counts. A round counts whole to the exercise's movement pattern
and whole to each of its primary muscles; nothing is divided, so a block of two
exercises for four rounds is four rounds of each (CONTEXT.md § Volume). Every
figure below was computed from the rounds and each exercise's own
`movement_pattern` and `primary_muscles`, read out of the catalog.

## What the runner has to set up

- **`today` is `2026-09-10`** for every row. `log_workout` takes it, so the set
  does not drift with the calendar.
- **P1-P4 exist as prescribed workouts** in the database the eval reads,
  prescribed before `today`, holding ids 1, 2, 3 and 4 in that order. The
  `workout_id` in each expected document is that id.
- **One prior performed workout supplies the load history** row U5 needs:
  `Barbell_Squat` last recorded at **80 kg**. Without it
  `state.last_performed_load` answers *I don't know* and the jump flag cannot
  fire.
- **The runner is `trainer eval --suite log`**, and everything above is what
  `log_evaluation.prepared` builds: a throwaway copy of the project database
  holding these four prescriptions and that one performed workout, with
  `TRAINER_DB` pointed at it so the agent's own tools read it too. Added after
  the rows were written, and it changes none of them.
- **Two fields are not scored by equality.** `proposed_exclusion.retest_date` is
  scored only as *a date strictly after `today`* — which day the agent picks is
  a judgement the document does not constrain. `proposed_exclusion.why` is free
  prose. Everything else in the document is equality.

---

## 1. The prescriptions

Four ordinary workouts. Every id below was read out of `exercises` and verified
character for character; the pattern and muscles beside each are the catalog's
own values, and they are what the volume figures are computed from.

### P1 — push day

| block | rounds | rest | exercise id | prescribed | movement pattern | primary muscles |
|---|---|---|---|---|---|---|
| 1 | 4 | 150 | `Barbell_Bench_Press_-_Medium_Grip` | 8 reps | horizontal push | chest |
| 2 | 3 | 120 | `Standing_Military_Press` | 10 reps | vertical push | shoulders |
| 3 | 3 | 60 | `Triceps_Pushdown` | 12 reps | isolation | triceps |

Prescribed volume — pattern: horizontal push 4, vertical push 3, isolation 3.
Muscle: chest 4, shoulders 3, triceps 3.

### P2 — pull day

| block | rounds | rest | exercise id | prescribed | movement pattern | primary muscles |
|---|---|---|---|---|---|---|
| 1 | 4 | 150 | `Pullups` | 6 reps | vertical pull | lats |
| 2 | 4 | 120 | `Bent_Over_Barbell_Row` | 8 reps | horizontal pull | middle back |
| 3 | 3 | 60 | `Barbell_Curl` | 12 reps | isolation | biceps |

Prescribed volume — pattern: vertical pull 4, horizontal pull 4, isolation 3.
Muscle: lats 4, middle back 4, biceps 3.

### P3 — leg day

| block | rounds | rest | exercise id | prescribed | movement pattern | primary muscles |
|---|---|---|---|---|---|---|
| 1 | 4 | 180 | `Barbell_Squat` | 5 reps | squat | quadriceps |
| 2 | 3 | 120 | `Romanian_Deadlift` | 8 reps | hip hinge | hamstrings |
| 3 | 3 | 60 | `Standing_Calf_Raises` | 15 reps | isolation | calves |

Prescribed volume — pattern: squat 4, hip hinge 3, isolation 3.
Muscle: quadriceps 4, hamstrings 3, calves 3.

### P4 — superset and timed work

| block | rounds | rest | exercise id | prescribed | movement pattern | primary muscles |
|---|---|---|---|---|---|---|
| 1 | 3 | 120 | `Dumbbell_Bench_Press` | 10 reps | horizontal push | chest |
| 1 | 3 | 120 | `Seated_Cable_Rows` | 10 reps | horizontal pull | middle back |
| 2 | 3 | 60 | `Plank` | 45 seconds | core anti-extension | abdominals |
| 3 | 3 | 90 | `Sled_Overhead_Backward_Walk` | 40 seconds | carry | shoulders |

Block 1 is the superset — one round is one trip through both exercises, and it
counts whole to each. Blocks 2 and 3 are the timed work, prescribed in seconds.

Prescribed volume — pattern: horizontal push 3, horizontal pull 3, core
anti-extension 3, carry 3. Muscle: chest 3, middle back 3, abdominals 3,
shoulders 3.

`Sled_Overhead_Backward_Walk` is the catalog's **only** `carry`. There is no
second candidate to vary it with.

---

## 2. Eighteen unambiguous reports

### U1 — perfect adherence — P1

> tutto liscio, fatto come sta scritto

```json
{
  "workout_id": 1,
  "blocks": [],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, vertical push 3, isolation 3
- **volume (muscle):** chest 4, shoulders 3, triceps 3

*Note.* "fatto come sta scritto" states no deviation at all, and logging is by
deviation: the empty `blocks` is the whole answer, and adherence fills in all
three prescribed blocks as `assumed`. A document that restates the prescription
is the commonest wrong answer here.

### U2 — fewer rounds — P1

> panca bene, di militari solo 2 serie che ero cotto

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Standing_Military_Press",
          "unit": "reps",
          "amount": 10,
          "amount_source": "assumed"
        }
      ],
      "rounds": 2,
      "rounds_source": "reported",
      "rest": 120,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, vertical push 2, isolation 3
- **volume (muscle):** chest 4, shoulders 2, triceps 3

*Note.* "solo 2 serie" is *sets*, which in this engine are **rounds** — 2 of the
prescribed 3, not 2 reps. "panca bene" is not a deviation and must not appear in
the document. The 10 reps nobody mentioned are `assumed` at the prescribed
value, which is the only value `assumed` is allowed to carry.

### U3 — more rounds — P2

> di curl mi e avanzato tempo e ne ho fatta una serie in piu, 4

```json
{
  "workout_id": 2,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Barbell_Curl",
          "unit": "reps",
          "amount": 12,
          "amount_source": "assumed"
        }
      ],
      "rounds": 4,
      "rounds_source": "reported",
      "rest": 60,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** vertical pull 4, horizontal pull 4, isolation 4
- **volume (muscle):** lats 4, middle back 4, biceps 4

*Note.* "una serie in piu, 4" gives both the direction and the total, so rounds
is 4 `reported` and not 3+1 left to arithmetic. A deviation upward is a
deviation like any other.

### U4 — a load stated — P1

> panca con 70 kg, tutte e 4 le serie

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Barbell_Bench_Press_-_Medium_Grip",
          "unit": "reps",
          "amount": 8,
          "amount_source": "assumed",
          "load_kg": 70,
          "load_kg_source": "reported"
        }
      ],
      "rounds": 4,
      "rounds_source": "reported",
      "rest": 150,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, vertical push 3, isolation 3
- **volume (muscle):** chest 4, shoulders 3, triceps 3

*Note.* "70 kg" is the user's own number, so `load_kg_source` is `reported`;
`assumed` is refused outright for a load, because a plan prescribes none and
there is nothing for one to have been assumed from. "tutte e 4 le serie"
confirms the prescribed round count in the user's own words, so `rounds_source`
is `reported` even though the number is unchanged. A load moves no volume: it is
not part of either axis.

### U5 — a load that jumped — P3

> squat oggi 110, non so cosa mi sia preso

```json
{
  "workout_id": 3,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Barbell_Squat",
          "unit": "reps",
          "amount": 5,
          "amount_source": "assumed",
          "load_kg": 110,
          "load_kg_source": "reported"
        }
      ],
      "rounds": 4,
      "rounds_source": "assumed",
      "rest": 180,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** squat 4, hip hinge 3, isolation 3
- **volume (muscle):** quadriceps 4, hamstrings 3, calves 3

*Note.* 110 against the fixture's recorded 80 kg is +37.5%, past `LOAD_JUMP`'s
fifth, so `log.flags` raises *moved from 80 kg to 110 kg*. The flag is the
engine's and is not part of the document — what is scored here is that the agent
records 110 and does **not** soften it, refuse it or ask about it. "non so cosa
mi sia preso" is colour, not a number.

### U6 — a substitution — P1

> panca bilanciere occupata, ho fatto quella coi manubri, 4 serie da 10

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Dumbbell_Bench_Press",
          "unit": "reps",
          "amount": 10,
          "amount_source": "reported"
        }
      ],
      "rounds": 4,
      "rounds_source": "reported",
      "rest": 150,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 8, vertical push 3, isolation 3
- **volume (muscle):** chest 8, shoulders 3, triceps 3

*Note.* "quella coi manubri" after "panca bilanciere occupata" names the
substitute unambiguously. The substituted block pairs with no prescribed block,
so nothing in it can be `assumed` except where the prescription is silent — the
rest nobody mentioned. **The horizontal push count is 8 and that is not an
arithmetic slip**: `to_performed` leaves the prescribed barbell bench `assumed`
*as well as* recording the substitute, deliberately, because which of the two the
user meant is a judgement the engine does not make. Both are flagged. An expected
figure of 4 would fail a correct agent.

### U7 — an exercise skipped entirely — P1 `?`

> panca e militari ok, i tricipiti li ho saltati che chiudevano

```json
{
  "workout_id": 1,
  "blocks": [],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, vertical push 3, isolation 3
- **volume (muscle):** chest 4, shoulders 3, triceps 3

*Note.* "li ho saltati" is unambiguous prose, and **the document shape cannot
express it**: `PerformedBlock.rounds` is `ge=1` and `items` is `min_length=1`, so
there is no way to say *not done*, and every prescribed block the report does not
name is filled in by adherence as performed. The only emission that is not a lie
is the empty one — which is byte-identical to U1's, and produces 3 rounds of
`isolation` the user did not do.

**`?` — the doubt.** This row is honestly labelled and currently worth little as
a measurement: it cannot distinguish a correct agent from one that ignored the
sentence. What it does test is that the agent invents nothing — no `rounds: 0`
(the schema refuses it), no exclusion, no question. If a later ticket gives the
shape a way to say *not performed*, this row's expected outcome changes and the
volume becomes horizontal push 4, vertical push 3, isolation 0. See the note at
the end of this file.

### U8 — a workout nobody prescribed

> oggi a casa, 4 per 8 di trazioni poi 3 per 15 di piegamenti, pausa 90

```json
{
  "workout_id": null,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Pullups",
          "unit": "reps",
          "amount": 8,
          "amount_source": "reported"
        }
      ],
      "rounds": 4,
      "rounds_source": "reported",
      "rest": 90,
      "rest_source": "reported"
    },
    {
      "items": [
        {
          "exercise_id": "Pushups",
          "unit": "reps",
          "amount": 15,
          "amount_source": "reported"
        }
      ],
      "rounds": 3,
      "rounds_source": "reported",
      "rest": 90,
      "rest_source": "reported"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** vertical pull 4, horizontal push 3
- **volume (muscle):** lats 4, chest 3

*Note.* "oggi a casa" with no reference to a plan is training nobody prescribed,
so `workout_id` is null — a real answer, not a missing value. With no
prescription behind it **every** value must be `reported` or `asked`:
`_nothing_assumed_without_a_prescription` refuses `assumed` anywhere here, rest
included, which is why "pausa 90" has to be in the sentence for this row to be
answerable at all. "poi" makes the two exercises sequential blocks rather than a
superset. `log.flags` adds *this reports no prescribed workout*.

### U9 — RPE volunteered — P2

> trazioni durissime oggi, rpe 9, il resto normale

```json
{
  "workout_id": 2,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Pullups",
          "unit": "reps",
          "amount": 6,
          "amount_source": "assumed"
        }
      ],
      "rounds": 4,
      "rounds_source": "assumed",
      "rest": 150,
      "rest_source": "assumed",
      "rpe": 9
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** vertical pull 4, horizontal pull 4, isolation 3
- **volume (muscle):** lats 4, middle back 4, biceps 3

*Note.* "rpe 9" is volunteered, so it is recorded; it carries no `_source` and is
never asked for. Nothing else deviated — "il resto normale" — so every other
value on the block is the prescription's, `assumed`. RPE is not volume and moves
no figure.

### U10 — timed work reported in seconds — P4

> plank tenuto 60 secondi invece di 45, il resto come sempre

```json
{
  "workout_id": 4,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Plank",
          "unit": "seconds",
          "amount": 60,
          "amount_source": "reported"
        }
      ],
      "rounds": 3,
      "rounds_source": "assumed",
      "rest": 60,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 3, horizontal pull 3, core anti-extension 3, carry 3
- **volume (muscle):** chest 3, middle back 3, abdominals 3, shoulders 3

*Note.* "60 secondi" keeps the prescribed unit — `seconds`, not reps — and the
amount is `reported` because the user gave it. **Holding a plank longer changes
no volume**: volume is rounds performed, and the rounds did not move. An expected
figure that grew with the seconds would be counting the wrong thing.

### U11 — two blocks at once — P3

> squat 3 serie invece di 4, e gli stacchi tutti e 3 ma con 60 kg

```json
{
  "workout_id": 3,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Barbell_Squat",
          "unit": "reps",
          "amount": 5,
          "amount_source": "assumed"
        }
      ],
      "rounds": 3,
      "rounds_source": "reported",
      "rest": 180,
      "rest_source": "assumed"
    },
    {
      "items": [
        {
          "exercise_id": "Romanian_Deadlift",
          "unit": "reps",
          "amount": 8,
          "amount_source": "assumed",
          "load_kg": 60,
          "load_kg_source": "reported"
        }
      ],
      "rounds": 3,
      "rounds_source": "reported",
      "rest": 120,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** squat 3, hip hinge 3, isolation 3
- **volume (muscle):** quadriceps 3, hamstrings 3, calves 3

*Note.* One sentence, two blocks, two different kinds of deviation: "3 serie
invece di 4" is rounds, "tutti e 3" is the prescribed round count confirmed out
loud, and "con 60 kg" is a load on the second block only. The calf raises are
never mentioned and come back whole and `assumed`.

### U12 — the third block and nothing else — P1

> solo i tricipiti sono andati male, 8 ripetizioni invece di 12

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Triceps_Pushdown",
          "unit": "reps",
          "amount": 8,
          "amount_source": "reported"
        }
      ],
      "rounds": 3,
      "rounds_source": "assumed",
      "rest": 60,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, vertical push 3, isolation 3
- **volume (muscle):** chest 4, shoulders 3, triceps 3

*Note.* "8 ripetizioni invece di 12" is **reps**, not rounds — the one place the
*serie*/*ripetizioni* distinction has to be read the other way round, and the
rounds stay at the prescribed 3. The block is the third one prescribed and the
only one mentioned; `_paired` matches it by exercise, so this row fails
immediately for any agent that files the first reported block under the first
prescribed one.

### U13 — pain, joint granularity — P1

> la spalla destra ha iniziato a bruciare in panca, solo 2 serie. fermiamo tutto quello che carica la spalla

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Barbell_Bench_Press_-_Medium_Grip",
          "unit": "reps",
          "amount": 8,
          "amount_source": "assumed"
        }
      ],
      "rounds": 2,
      "rounds_source": "reported",
      "rest": 150,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": {
    "value": "shoulder",
    "retest_date": "<any date after 2026-09-10>",
    "why": "la spalla destra ha iniziato a bruciare in panca"
  }
}
```

- **volume (pattern):** horizontal push 2, vertical push 3, isolation 3
- **volume (muscle):** chest 2, shoulders 3, triceps 3

*Note.* "tutto quello che carica la spalla" names the **joint**, not a pattern:
it is everything loading the shoulder, which is what the `joint` granularity
means and what `classify` returns for `shoulder`. The value has to be `shoulder`
character for character — a catalog `loaded_joints` value — and never an exercise
id. "solo 2 serie" is the training deviation, separate from the exclusion.

### U14 — pain, pattern granularity — P1

> in panca zero problemi, ma sopra la testa il dolore torna sempre. 1 serie di militari e ho mollato

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Standing_Military_Press",
          "unit": "reps",
          "amount": 10,
          "amount_source": "assumed"
        }
      ],
      "rounds": 1,
      "rounds_source": "reported",
      "rest": 120,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": {
    "value": "vertical push",
    "retest_date": "<any date after 2026-09-10>",
    "why": "sopra la testa il dolore torna sempre, in panca nessun problema"
  }
}
```

- **volume (pattern):** horizontal push 4, vertical push 1, isolation 3
- **volume (muscle):** chest 4, shoulders 1, triceps 3

*Note.* "sopra la testa" is overhead work — the `vertical push` pattern — and
"in panca zero problemi" is what rules the joint out: the bench loads the
shoulder too, so a `shoulder` exclusion would wall off a movement the user has
just said is fine. This row and U13 are the pair that measures whether
granularity is read off the sentence rather than defaulted to one of the two.

### U15 — pain, joint granularity — P3

> il ginocchio sinistro punge sotto il parallelo, squat fermato a 2 serie. per un po' niente carichi sul ginocchio

```json
{
  "workout_id": 3,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Barbell_Squat",
          "unit": "reps",
          "amount": 5,
          "amount_source": "assumed"
        }
      ],
      "rounds": 2,
      "rounds_source": "reported",
      "rest": 180,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": {
    "value": "knee",
    "retest_date": "<any date after 2026-09-10>",
    "why": "il ginocchio sinistro punge sotto il parallelo"
  }
}
```

- **volume (pattern):** squat 2, hip hinge 3, isolation 3
- **volume (muscle):** quadriceps 2, hamstrings 3, calves 3

*Note.* "niente carichi sul ginocchio" is the joint said in as many words. Left
and right are not a granularity this engine has, so "sinistro" is carried in
`why` and nowhere else. The calf raises load the ankle and the Romanian deadlift
the hip and lumbar spine, so neither is touched by the proposal — and neither is
a deviation, so neither appears in the document.

### U16 — pain, joint granularity — P3

> stacchi, la schiena bassa ha tirato subito, 1 serie e ho smesso. la zona lombare va lasciata stare

```json
{
  "workout_id": 3,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Romanian_Deadlift",
          "unit": "reps",
          "amount": 8,
          "amount_source": "assumed"
        }
      ],
      "rounds": 1,
      "rounds_source": "reported",
      "rest": 120,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": {
    "value": "lumbar spine",
    "retest_date": "<any date after 2026-09-10>",
    "why": "la schiena bassa ha tirato subito sugli stacchi"
  }
}
```

- **volume (pattern):** squat 4, hip hinge 1, isolation 3
- **volume (muscle):** quadriceps 4, hamstrings 1, calves 3

*Note.* "la zona lombare va lasciata stare" is `lumbar spine`, the catalog's own
`loaded_joints` value, written with the space and in lower case. The trap here is
`hip hinge`: the user named a body part and not a movement, and the squat — which
also loads the lumbar spine — is untouched in the report, so nothing licenses
excluding the pattern the deadlift happens to belong to.

### U17 — timed work, more seconds and a load — P4

> il carry l'ho tenuto 60 secondi a giro invece di 40, con 30 kg

```json
{
  "workout_id": 4,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Sled_Overhead_Backward_Walk",
          "unit": "seconds",
          "amount": 60,
          "amount_source": "reported",
          "load_kg": 30,
          "load_kg_source": "reported"
        }
      ],
      "rounds": 3,
      "rounds_source": "assumed",
      "rest": 90,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 3, horizontal pull 3, core anti-extension 3, carry 3
- **volume (muscle):** chest 3, middle back 3, abdominals 3, shoulders 3

*Note.* "a giro" is *per round*, so 60 seconds is the amount on each of the three
rounds and not a total to be divided. Both numbers are the user's, so both are
`reported`. The rounds did not move and neither did any volume figure.

### U18 — rest deviated — P3

> sullo squat ho recuperato 4 minuti invece di 3, ero morto

```json
{
  "workout_id": 3,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Barbell_Squat",
          "unit": "reps",
          "amount": 5,
          "amount_source": "assumed"
        }
      ],
      "rounds": 4,
      "rounds_source": "assumed",
      "rest": 240,
      "rest_source": "reported"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** squat 4, hip hinge 3, isolation 3
- **volume (muscle):** quadriceps 4, hamstrings 3, calves 3

*Note.* "4 minuti" is **240 seconds** — the field is seconds, never minutes and
never milliseconds, and a `rest` of 4 is the whole reason the schema says so out
loud. "ero morto" is not an RPE: it is not a number, and RPE is never inferred.
Rest is not volume.

---

## 3. Twelve reports that must make it ask

Scored binary on `LogRecord.questions` being non-empty. Each row states what the
sentence leaves open and the value a confident model fills in instead — the
**wrong answer** is what makes false confidence something code can detect rather
than a feeling.

### A1 — how many rounds — P1

> in panca ho tolto qualche serie, ero scarico

- **unknowable:** "qualche serie" gives a direction and no number — the rounds
  performed are anywhere from 1 to 3 of the prescribed 4.
- **wrong answer:** `rounds: 3, rounds_source: "reported"` on the bench block —
  one fewer, because *qualche* reads as *one or two* and 3 is the nearest.

*Note.* The deviation is stated and its size is not, which is the shape of this
whole half. No provenance can carry the guess either: `assumed` would have to
mean 4, and `reported` would be a number the user never said.

### A2 — substituted with what — P1

> invece dei militari ho fatto un'altra roba per le spalle

- **unknowable:** "un'altra roba per le spalle" names a muscle and not an
  exercise, and the catalog holds dozens of shoulder movements across two
  patterns.
- **wrong answer:** a block naming `Dumbbell_Shoulder_Press` — the nearest
  obvious swap for a military press.

*Note.* The substitution is certain and the substitute is not, and an id is not
something a document can hedge: the exercise chosen decides the pattern, the
muscles and every volume figure downstream.

### A3 — a bare number — P3

> allenamento da 7 oggi

- **unknowable:** 7 is effort, or discomfort, or a count of something — the
  sentence attaches it to nothing.
- **wrong answer:** `rpe: 7` on every block.

*Note.* RPE is recorded only when volunteered, and volunteering it means saying
it *is* one. Nothing here says which scale the 7 is on, and this project has no
pain scale at all.

### A4 — a load on which lift — P3

> ho caricato 60

- **unknowable:** P3 has two loadable lifts, `Barbell_Squat` and
  `Romanian_Deadlift`, and the sentence names neither.
- **wrong answer:** `load_kg: 60, load_kg_source: "reported"` on `Barbell_Squat`
  — the first block and the heavier lift.

*Note.* A load attached to the wrong exercise is worse than no load: it is what
`last_performed_load` answers with next time, and what the jump flag measures
against.

### A5 — what hurt and how much was cut — P2

> mi tirava e ho chiuso prima

- **unknowable:** two gaps in six words — *what* was pulling (no body area, no
  movement) and *how much* of the workout was cut.
- **wrong answer:** `rounds: 2` on the pullups block plus a `proposed_exclusion`
  on `shoulder`.

*Note.* This is the row where guessing costs most: the invented exclusion walls
off a joint on the strength of a sentence that named no part of the body.

### A6 — how much longer — P4

> il plank l'ho tenuto molto di piu

- **unknowable:** "molto di piu" than 45 seconds is 60, or 90, or three minutes.
- **wrong answer:** `unit: "seconds", amount: 60, amount_source: "reported"`.

*Note.* The unit and the direction are both certain, which is exactly what makes
the fill tempting. `assumed` cannot rescue it either — that would have to say 45,
which the user has just denied.

### A7 — half of what — P2

> trazioni fatte a meta

- **unknowable:** half the rounds (2 of 4) or half the reps (3 of 6) — and "a
  meta" is used for both in gym Italian.
- **wrong answer:** `rounds: 2, rounds_source: "reported"`.

*Note.* The *serie*/*ripetizioni* ambiguity with no word to settle it. The two
readings differ in volume — 2 rounds of `vertical pull` against 4 — so the guess
is not a rounding error.

### A8 — which first part — P4

> ho fatto solo la prima parte

- **unknowable:** the first block of three, or only the first exercise of the
  superset that block is.
- **wrong answer:** a document reporting block 1 alone and leaving blocks 2 and 3
  to adherence.

*Note.* P4's first block holds two exercises, which is what makes "la prima
parte" genuinely two-valued here; it would not be against P1.

### A9 — what was added — P1

> alla fine ho aggiunto un esercizio

- **unknowable:** which exercise, for how many rounds, of how many reps, with
  what rest — four fields and no words behind any of them.
- **wrong answer:** a fourth block naming some plausible push accessory, at 3
  rounds of 10.

*Note.* The one row where the document is short by a whole block. Everything
about it is `reported` or `asked` territory — there is no prescribed counterpart
for the added block to have been assumed from.

### A10 — heavier than what — P4

> il carry l'ho fatto piu pesante

- **unknowable:** no load is prescribed anywhere in a plan and none is recorded
  for `Sled_Overhead_Backward_Walk`, so "piu pesante" has neither a baseline nor
  a size.
- **wrong answer:** `load_kg: 40, load_kg_source: "reported"`.

*Note.* Unlike A6 there is not even a number to be *more* than. A load invented
here becomes the history the next jump flag is measured against.

### A11 — six of what — P1

> di panca ne ho fatte 6

- **unknowable:** 6 rounds against the prescribed 4, or 6 reps against the
  prescribed 8 — "ne ho fatte" takes either, and the two point in opposite
  directions.
- **wrong answer:** `rounds: 6, rounds_source: "reported"` — *serie* is the
  commoner reading of a bare count.

*Note.* The vocabulary trap with the disambiguating noun removed. One reading
adds 2 rounds of `horizontal push` and the other removes none.

### A12 — bad enough to stop — P3

> ginocchio cosi cosi ma ho finito tutto

- **unknowable:** whether "cosi cosi" is a niggle to note or a reason to stop
  prescribing knee-loading work — and an exclusion is a hard boundary, never
  inferred from a mood.
- **wrong answer:** `proposed_exclusion: {"value": "knee", ...}`.

*Note.* The mirror of U13 and U15: the same body part, and nothing in the
sentence asking for anything to stop. "ho finito tutto" says the workout was
completed as prescribed, so the blocks are genuinely empty — the only open
question is the exclusion, and it has to be asked and confirmed rather than
inferred.

---

## 4. Confirmation

I wrote every row in this file before seeing anything the logging agent
produces. `src/trainer/agent.py` was never opened, and neither was any run
record, any `.json` output, or anything under a scratchpad or temporary
directory. I ran no `git log`, `git show`, `git diff` or any other command that
reads commit messages, and I ran no command that reaches a model — `trainer log`
and `trainer eval` were never invoked, in any form, against any database.

What I did read: `src/trainer/log.py` in full, for the document shape, the three
provenance values, what `validate` refuses against what `flags` merely records,
and what `to_performed` fills in; `src/trainer/engine/exclusions.py` for
`classify` and the two granularities; `src/trainer/engine/state.py` and
`src/trainer/tools.py` only for the volume-deficit wording; `CONTEXT.md` for the
vocabulary; `ROADMAP.md` § Session 5; the ticket
`docs/work/05-logging-by-deviation/issues/05-the-measurement.md`; and
`docs/enrichment/reference-set.md` as the format precedent. Everything else came
from the database: every exercise id, movement pattern, primary muscle, joint
value and pattern name in this file was read out of `trainer.sqlite` with
read-only SQL, and all of them were re-verified as a set in one final query
rather than typed from memory.

Every volume figure was computed by re-implementing `log.to_performed`'s pairing
and fill against the four prescriptions above and summing rounds per pattern and
per muscle from the catalog's own labels — not estimated by eye. The figures for
U6 and U7 look wrong at a glance and are not: U6 double-counts `horizontal push`
because a substitution deliberately leaves the prescribed exercise `assumed`
beside the substitute, and U7 counts a block the user says they skipped because
the shape has no way to say so.

**One row carries a `?`: U7.** The shape cannot express a skipped exercise —
`rounds` is `ge=1`, `items` is `min_length=1`, and adherence fills in every
prescribed block the report does not name. The expected document is therefore
the empty one, identical to U1's, and the expected volume counts 3 rounds of
`isolation` the user did not perform. The row is in the set because the sentence
is unambiguous and the gap is real; whoever builds the scorer should know that
this row measures only that nothing was invented, and that it needs rewriting
the day the document learns to say *not performed*.
