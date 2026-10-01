# Research Challenges & Lessons

Getting from "insiders who buy their own stock tend to be informative" to a
live, trusted signal involved real dead ends. This page covers three of
them: model overfitting, a recurring class of data leakage, and position
sizing. No charts here — the real backtest visualizations all have specific
thresholds, weights, and performance figures baked directly into the image
(unlike text, a rendered chart can't be selectively redacted), so this page
is prose-only by design. See [methodology.md](methodology.md) for the
research pipeline these lessons fed into.

## Overfitting: two guards, both warnings, not auto-rejects

Two independent checks were built to catch a model or parameter set that
looked great in training but wouldn't generalize:

- **On the model itself**: if validation R² comes in well below a fraction
  of training R², it's flagged as potential overfitting.
- **On the hyperparameter search**: if the validation score drops sharply
  from the training score for the best-found parameter set, it's flagged the
  same way.

Deliberately, **neither guard auto-rejects anything** — they print a warning
and move on. The alternative (auto-discarding any flagged run) sounds
safer but isn't: it would have silently thrown away runs that were fine but
happened to validate on a harder stretch of market, and it hides the signal
a human reviewer needs to notice a real pattern (e.g. the same feature
causing the drop across multiple runs). Flagged runs get looked at by hand
instead of trusted or discarded automatically.

## Feature leakage: not one bug, a recurring class of mistake

The headline incident: a backtest dataset let a signal's own purchase count
toward its own historical track record, because the cutoff for "prior
history" was the entry date rather than the signal's own purchase date. A
signal always looks perfect in hindsight to itself, so this inflated
every win-rate-dependent backtest that used it — dramatically, not
marginally. Once caught, the fix was to require that prior history be both
transacted *and filed* strictly before the signal's own date, and to treat
the inflated numbers as never having been real.

What made this worth a page of its own: it wasn't a one-off bug, it was the
same root mistake recurring across different features, each time the
underlying cause was using information technically not yet public at
decision time (Form 4s aren't public until filed, often a day or more after
the actual transaction). Once that pattern was recognized, it reshaped how
every subsequent feature was built:

- A momentum/reversal feature was designed anti-look-ahead from the start
  once the lesson landed, rather than retrofitted later.
- A trend-context module went through a dedicated rewrite specifically to
  make it point-in-time, after an earlier version was found to risk the same
  mistake.
- A short-interest feature turned out to be **impossible to fully fix** —
  point-in-time short-interest data isn't available, only current data is.
  Rather than quietly use a leaky feature or scrap the idea entirely, it was
  explicitly labeled "directional only, look-ahead biased" in the code and
  excluded from live decision-making. When a feature can't be made honest,
  labeling it beats hiding it or deleting the evidence that it was tried.

The general lesson: look-ahead bias isn't a single checkbox you tick once —
it's a class of mistake that shows up anywhere a "prior history" cutoff is
one day off from when the information was actually knowable, and it's worth
auditing every feature for it specifically, not just the obvious ones.

## Portfolio allocation: there's no single best sizing scheme

Before settling on a live approach, a wide range of position-sizing schemes
were backtested against each other — fixed percentages of the portfolio,
sizing off available cash, several variants of the Kelly criterion (half,
quarter, with fallbacks), fully-invested, and a few adaptive/seasonal
variants. Real problems turned up along the way:

- **Signal clustering starves later signals.** Opportunities don't arrive
  evenly — some stretches produce many signals, others few. A sizing scheme
  that's too aggressive early in a busy stretch can leave too little capital
  for signals that show up later in the same stretch, even though those
  later signals are just as good. One fix tested was a floor that prevents a
  late-arriving signal from getting a trivially small position just because
  of when it happened to show up.
- **Pure Kelly sizing can run out of room.** Kelly-based sizing scales with
  the portfolio's current state, which means a heavily-deployed portfolio can
  end up sizing new signals down to nothing — or skipping them — purely
  because of how much capital happens to be tied up at that moment, not
  because the signal itself is weaker. The fix tested was a fallback: once
  capital utilization crosses a threshold, switch to sizing off whatever cash
  remains instead of letting a signal get skipped outright.
- **A scheme can be fragile to arrival order, not just outcomes.** Beyond
  the usual "what if the trades had gone differently" stress test, the
  *order* signals arrived in was independently reshuffled (holding the
  actual outcomes fixed) to check whether a sizing scheme's apparent edge
  depended on a lucky sequence of clustering, separate from whether the
  underlying trades were good.

The takeaway that generalizes beyond this specific project: every sizing
scheme is a tradeoff between return, max drawdown, how much rides on any
single trade, and how much capital sits idle vs. deployed — there's no
scheme that wins on all four at once. The live service's actual sizing
approach (not detailed here, along with its exact parameters) reflects a
deliberate choice on that tradeoff curve, not just "whichever backtested
highest."
