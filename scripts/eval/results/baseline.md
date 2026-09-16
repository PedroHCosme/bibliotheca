# Eval: baseline

Answer cost = total tokens / answers that are both correct and cited. Lower is better.
360 runs: 3 corpora x 20 questions x 3 arms, Sonnet 5, targeted questions repeated 3x.
Judged by Haiku 4.5 against a reviewed gold set (rubric v2); 10% spot-checked by Claude,
1 disagreement in 12. Corpora, questions and answers stay local (company-internal).

Arms, identical flags, differing only in working directory and skill:
- **A** - the original source files; glob/grep/Read; no skills.
- **B-current** - the same sources plus the Bibliotheca skill (main + the name-collision fix).
- **C** - the Bibliotheca slice folder (no CLAUDE.md, no database); glob/grep/Read; no skills.

Corpora: `robotics` (419-page PDF + 1 note), `organized` (224 company docs in named folders),
`scrambled` (94 files, opaque names, mixed .pdf/.tex/.txt/.md).

`used biblio` counts runs that called the CLI; in arm C those 3 are failed attempts (no CLI on PATH).

| corpus | kind | arm | runs | answer cost | correct | cited | tokens min–max | tool calls | errors | used biblio |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| organized | targeted | A | 30 | 147,306 | 67% | 90% | 45,197–262,932 | 3.8 | 0 | 0 |
| organized | targeted | B-current | 30 | 133,872 | 57% | 87% | 43,622–144,538 | 3.5 | 0 | 0 |
| organized | targeted | C | 30 | 171,588 | 63% | 83% | 50,268–205,950 | 6.1 | 0 | 0 |
| organized | thematic | A | 10 | 179,583 | 80% | 90% | 43,573–589,449 | 5.5 | 0 | 0 |
| organized | thematic | B-current | 10 | 136,641 | 80% | 90% | 71,183–203,962 | 5.0 | 0 | 0 |
| organized | thematic | C | 10 | 163,208 | 50% | 90% | 65,964–148,067 | 5.5 | 0 | 0 |
| robotics | targeted | A | 30 | 133,414 | 87% | 100% | 41,895–351,089 | 6.4 | 0 | 0 |
| robotics | targeted | B-current | 30 | 114,981 | 87% | 100% | 41,938–163,974 | 5.8 | 0 | 0 |
| robotics | targeted | C | 30 | 104,516 | 87% | 100% | 47,518–183,729 | 4.5 | 0 | 0 |
| robotics | thematic | A | 10 | 134,052 | 90% | 90% | 41,310–175,320 | 6.6 | 0 | 0 |
| robotics | thematic | B-current | 10 | 127,029 | 100% | 100% | 71,926–159,727 | 7.0 | 0 | 0 |
| robotics | thematic | C | 10 | 155,342 | 80% | 100% | 61,169–226,022 | 7.3 | 0 | 3 |
| scrambled | targeted | A | 30 | 107,911 | 93% | 100% | 57,849–382,117 | 5.9 | 0 | 0 |
| scrambled | targeted | B-current | 30 | 131,773 | 93% | 93% | 59,205–501,588 | 6.4 | 0 | 2 |
| scrambled | targeted | C | 30 | 342,908 | 60% | 60% | 63,881–563,415 | 10.6 | 0 | 0 |
| scrambled | thematic | A | 10 | 177,953 | 80% | 80% | 83,881–223,931 | 10.2 | 0 | 0 |
| scrambled | thematic | B-current | 10 | 232,548 | 90% | 100% | 80,030–486,782 | 11.2 | 0 | 1 |
| scrambled | thematic | C | 10 | 548,866 | 50% | 50% | 90,635–927,984 | 11.6 | 0 | 0 |
