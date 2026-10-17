# Transferred Stage A alert review

The transferred alert files support adding Stage A as a research overlay, not as an
automatic buy signal. The strongest repeatable observation is an extension effect:
first Stage A observations below 6% over EMA8 had materially better eight-session
outcomes than observations at or above 6%. The relationship is imperfect, so 6% is
a warning boundary rather than a rejection rule; 8% remains the overextension
boundary.

In the matured Stage A shadow sample, 97 observations across 40 symbols produced a
median eight-session close return of 0.76% and median MFE of 6.27%. On the first
Stage A observation per symbol, the below-6% group had a 2.83% median close return
and 66.7% positive rate (24 symbols), while the 6%-or-higher group had a -2.68%
median and 37.5% positive rate (16 symbols). These are small observational cohorts,
not a claim of deployable edge.

Volume above 2x is necessary to reproduce the historical setup. The sample does not
support assuming that ever-higher volume or ADR always improves results. ADR remains
a character floor, volume is recorded in ordinary/supporting/exceptional bands, and
neither receives an unvalidated linear bonus.

The broader alert exports also show why setup quality must be separated from entry
and exit quality. Several alert families produced sizable maximum favorable
excursions while also experiencing frequent stops and weak terminal returns. The
system should retain structural confirmation, explicit runway, causal deduplication,
and lifecycle exits rather than copying the original alert's immediate-entry logic.

The alert-timing shadow reinforces this distinction. Matured Stage A rows had a
9.2% median peak, 1.90% median terminal return, and 53.8% positive terminal rate;
Tier 2 trigger rows had a larger 14.59% median peak but a -3.80% median terminal
return and 40.9% positive rate. The transferred tight-stop study also stopped 80.2%
of long observations at 3% and 64.2% at 6%. Peak potential alone therefore must not
be confused with a complete trade plan.

Transferred liquid option-contract observations were strongest for the simple
breakout call cohort: 211 contracts had a 25.0% median eight-session maximum mark
gain and 42.7% reached +50%. Those figures measure maximum favorable mark, not
realized return, and remain vulnerable to spread, timestamp, survivorship, and exit
assumptions. They may rank options research candidates but cannot authorize an
options trade.

Stage B reload is not included. Its transferred history was materially weaker and
the original scanner itself documented repeated false reloads during continuing
breakdowns.

## Requested examples

The observations below are the relevant first or clearest Stage A rows in the
transfer. `SWKY` is interpreted as `SWKS` because no SWKY symbol exists in the files.

| Symbol | Date | Volume surge | Off 20d high | Over EMA8 | ADR20 | 8-session close | 8-session MFE |
|---|---:|---:|---:|---:|---:|---:|---:|
| SWKS | 2026-09-04 | 3.7x | -0.9% | 5.9% | 4.3% | 23.22% | 24.54% |
| DELL | 2026-09-08 | 4.4x | -0.9% | 7.9% | 6.1% | 6.50% | 11.65% |
| XP | 2026-09-17 | 3.4x | -2.4% | 2.8% | 4.0% | 0.05% | 6.47% |
| META | 2026-09-22 | 2.4x | -2.3% | 7.1% | 3.5% | -1.57% | 5.43% |
| P | 2026-09-30 | 9.8x | -1.9% | 7.1% | 5.5% | 18.75% | 20.08% |
| DXC | 2026-10-07 | 2.2x | -1.9% | 4.8% | 4.2% | pending | pending |
| MRNA | 2026-10-14 | 2.1x | -0.4% | 7.5% | 8.1% | pending | pending |

The mixed results are important: P and DELL ran despite extension warnings, META
did not retain its move, and MRNA and DXC lacked a completed eight-session horizon
at export time. Extension therefore remains a risk label, never a claim that a name
cannot run.
