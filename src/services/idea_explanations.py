""""What is this?" registry for Ideas (Workstream 12, checkpoint I2).

One registry of short explanations shared by the Ideas tab, panels and, later,
Copilot (I5). Each entry has three parts, per the spec's "Explanations on
demand":

- ``measures``: what it measures, in one sentence;
- ``why``: why it matters, one sentence per idea stance;
- ``computed``: how Gamma computes it, pointing at the transformation and the
  source. The UI shows the live provenance of the specific reading beside it.

The texts describe; they do not judge. They never say whether an idea is good,
and they sit behind an icon so they do not become static interpretive notes on
a data surface (``docs/design_principles.md``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.models.ideas import IDEA_STANCES


@dataclass(frozen=True)
class IdeaExplanation:
    key: str
    title: str
    measures: str
    why: Mapping[str, str]
    computed: str
    source: str | None = None

    def __post_init__(self) -> None:
        missing = [stance for stance in IDEA_STANCES if not self.why.get(stance)]
        if missing:
            raise ValueError(f"Explanation {self.key} lacks a 'why' line for {missing}.")
        object.__setattr__(self, "why", MappingProxyType(dict(self.why)))

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "measures": self.measures,
            "why": dict(self.why),
            "computed": self.computed,
            "source": self.source,
        }


def _why(long: str, short: str, relative: str, event: str, neutral: str) -> dict[str, str]:
    return {"long": long, "short": short, "relative": relative, "event": event, "neutral": neutral}


_ENTRIES: tuple[IdeaExplanation, ...] = (
    # -- observables ------------------------------------------------------
    IdeaExplanation(
        key="observable.equity_close",
        title="Equity or ETF close",
        measures="The last daily closing price of a listed share or fund, and its change over a window.",
        why=_why(
            "A close below your level is the plainest sign the market disagrees with a long thesis.",
            "A close above your level says the move you expected against the stock has not come.",
            "Each leg's close drives the spread between the legs of a relative idea.",
            "The close after the event shows how the market priced it.",
            "The close gives context for what the idea is watching.",
        ),
        computed=(
            "Daily closes from the research market data path (Yahoo Finance, then IBKR when Trader Workstation is "
            "connected). Each close counts on its session date; nothing before the criterion was armed can trigger it."
        ),
        source="Research market data",
    ),
    IdeaExplanation(
        key="observable.macro_series",
        title="Macro series",
        measures="The latest value of an economic or rates series, such as a Treasury yield or CPI, and its change.",
        why=_why(
            "Rates and inflation set the discount rate and demand behind most long theses.",
            "A macro print moving your way is often the catalyst a short thesis waits for.",
            "Macro moves can shift one leg against the other, for example cyclicals against defensives.",
            "The release is often the event itself.",
            "The series is the backdrop the idea is set against.",
        ),
        computed=(
            "Observations from Macro's series history (FRED or US Treasury). Each value counts on its observation "
            "date; revisions are not back-applied to past evaluations."
        ),
        source="Macro series history",
    ),
    IdeaExplanation(
        key="observable.prediction_probability",
        title="Prediction contract probability",
        measures="The implied probability of a prediction market contract, from its last traded or mid price.",
        why=_why(
            "The crowd's odds of the outcome your long thesis needs.",
            "The crowd's odds of the outcome your short thesis needs.",
            "Odds can explain why one leg should move against the other.",
            "For an event idea, this is the market's live estimate of the event itself.",
            "The odds give context the idea can be compared with.",
        ),
        computed=(
            "Prices from Prediction Markets (Polymarket or Kalshi) read as a probability in percent; \"occurs\" "
            "reads the venue's resolution. Thin books move on small trades; the provenance shows the venue and time."
        ),
        source="Prediction Markets",
    ),
    IdeaExplanation(
        key="observable.commodity_price",
        title="Commodity price",
        measures="The front-month or benchmark price of a commodity, and its change over a window.",
        why=_why(
            "Input or output prices drive margins for the companies a long thesis is about.",
            "A price moving your way confirms the pressure a short thesis expects.",
            "Commodity moves often decide relative ideas between producers and consumers.",
            "Supply events show up in the price first.",
            "The price is context for the idea.",
        ),
        computed=(
            "Daily benchmark prices from the Commodities service: EIA and FRED series by default, IBKR futures "
            "when Trader Workstation is connected."
        ),
        source="Commodities",
    ),
    IdeaExplanation(
        key="observable.commodity_spread",
        title="Commodity spread",
        measures="The current value of a commodity spread, such as a crack spread, a ratio or a calendar spread.",
        why=_why(
            "Margins between inputs and outputs drive the earnings of processors a long thesis may own.",
            "A spread moving your way confirms the margin squeeze a short thesis expects.",
            "A spread is itself a relative position between two commodities or two dates.",
            "Supply shocks often show up in spreads before outright prices.",
            "The spread is context for the idea.",
        ),
        computed=(
            "The latest value the Commodities service builds. Only level rules are offered, because some spread "
            "histories are proxies until historical futures curves are configured."
        ),
        source="Commodities",
    ),
    IdeaExplanation(
        key="observable.option_atm_iv",
        title="At-the-money implied volatility",
        measures="The options market's implied volatility for strikes near the current price, as an annual percentage.",
        why=_why(
            "Rising implied volatility means the market expects bigger moves, in either direction, than before.",
            "Implied volatility often rises as a stock falls; it can confirm stress a short thesis expects.",
            "A volatility gap between legs can say which one the market sees as riskier.",
            "Implied volatility usually rises into an event and falls after it.",
            "It measures how much movement the market is paying for.",
        ),
        computed=(
            "From the Options IV snapshot of the listed chain. It needs Trader Workstation; without it the "
            "criterion is unavailable, not holding."
        ),
        source="Options IV snapshot",
    ),
    IdeaExplanation(
        key="observable.option_skew",
        title="Volatility skew",
        measures="How much more implied volatility out-of-the-money puts carry than calls, in volatility points.",
        why=_why(
            "Steep skew means investors are paying up for downside protection.",
            "Rising skew can confirm the downside fear a short thesis expects.",
            "Skew differences between legs show where downside fear sits.",
            "Skew often steepens before an event with downside risk.",
            "It measures the price of crash protection.",
        ),
        computed=(
            "From the Options IV snapshot: put minus call implied volatility at matching distance from the money. "
            "It needs Trader Workstation."
        ),
        source="Options IV snapshot",
    ),
    IdeaExplanation(
        key="observable.crypto_price",
        title="Crypto price",
        measures="The latest price of a crypto token in US dollars, and its change over a window.",
        why=_why(
            "A price below your level says the market disagrees with a long thesis.",
            "A price above your level says the move against the token has not come.",
            "Each token's price drives a relative crypto idea.",
            "The price reaction shows how the market took the event.",
            "The price is context for the idea.",
        ),
        computed="Daily prices from CoinGecko; the latest point may be intraday and is labelled with its time.",
        source="CoinGecko",
    ),
    IdeaExplanation(
        key="observable.script_signal",
        title="Script signal",
        measures="A number your Research Script returned in its latest accepted run, such as a position or a score.",
        why=_why(
            "Your own model's reading of whether the long thesis still holds.",
            "Your own model's reading of whether the short thesis still holds.",
            "Your own model's spread or ranking between the legs.",
            "Your own model's reading around the event.",
            "Your own model's reading, tracked over time.",
        ),
        computed=(
            "Read from the latest completed run of the script; Gamma does not run the script to evaluate a "
            "criterion. A run older than seven days is shown as stale."
        ),
        source="Research Script runs",
    ),
    IdeaExplanation(
        key="observable.macro_event",
        title="Scheduled economic event",
        measures="A scheduled release on the macro calendar, its time and, once out, its actual value.",
        why=_why(
            "The release can confirm or break the macro story behind a long thesis.",
            "The release can be the catalyst a short thesis waits for.",
            "A release can move one leg more than the other.",
            "For an event idea, this is the event.",
            "The release is a dated checkpoint for the idea.",
        ),
        computed=(
            "From Macro's economic calendar. The calendar drops past events, so after the scheduled time Gamma uses "
            "the time stored with the criterion. The calendar has no released values; use a macro series for the print."
        ),
        source="Macro calendar",
    ),
    IdeaExplanation(
        key="observable.calendar_date",
        title="Date",
        measures="A date you set, such as a review date or a deadline for the thesis to play out.",
        why=_why(
            "A deadline keeps a long thesis honest: by then it should be working.",
            "A deadline keeps a short thesis honest: by then it should be working.",
            "A deadline for the spread to move.",
            "The date the event should have happened by.",
            "A date to look again.",
        ),
        computed="Gamma's clock in UTC; no data provider is involved.",
        source="Clock",
    ),
    # -- conditions --------------------------------------------------------
    IdeaExplanation(
        key="condition.above",
        title="Above",
        measures="Met when an observation is strictly above the threshold.",
        why=_why(
            "Use it for a confirming level or a stop on the upside.",
            "Use it for the level that would prove a short thesis wrong.",
            "Use it on the leg or spread that should not get away from you.",
            "Use it for the outcome level the event should reach.",
            "Use it for a level worth knowing about.",
        ),
        computed="Every observation that is new since the criterion was armed is checked, including late publications dated earlier, so a level met while Gamma was closed still triggers.",
    ),
    IdeaExplanation(
        key="condition.below",
        title="Below",
        measures="Met when an observation is strictly below the threshold.",
        why=_why(
            "Use it for the level that would prove a long thesis wrong.",
            "Use it for a confirming level on the way down.",
            "Use it on the leg or spread that should not fall through a level.",
            "Use it for the outcome level the event should not fall under.",
            "Use it for a level worth knowing about.",
        ),
        computed="Every observation that is new since the criterion was armed is checked, including late publications dated earlier, so a level met while Gamma was closed still triggers.",
    ),
    IdeaExplanation(
        key="condition.crosses_above",
        title="Crosses above",
        measures="Met when one observation is at or below the threshold and the next is above it.",
        why=_why(
            "A breakout through resistance, rather than already being above it.",
            "A move back above the level that would hurt a short.",
            "A spread moving through a level, not sitting past it.",
            "The outcome moving through a level after the event.",
            "A change of regime rather than a level.",
        ),
        computed="Pairs of consecutive observations; the later one must be new since the criterion was armed: dated on or after that day, or newer than the latest observation known then.",
    ),
    IdeaExplanation(
        key="condition.crosses_below",
        title="Crosses below",
        measures="Met when one observation is at or above the threshold and the next is below it.",
        why=_why(
            "A breakdown through support.",
            "A breakdown that confirms a short.",
            "A spread moving through a level on the way down.",
            "The outcome moving through a level after the event.",
            "A change of regime rather than a level.",
        ),
        computed="Pairs of consecutive observations; the later one must be new since the criterion was armed: dated on or after that day, or newer than the latest observation known then.",
    ),
    IdeaExplanation(
        key="condition.change_over_window",
        title="Change over a window",
        measures="Met when the change from the start of the window to an observation reaches the threshold: a rise for a positive threshold, a fall for a negative one.",
        why=_why(
            "A drawdown of a set size often says more than a fixed level.",
            "A rally of a set size can break a short thesis.",
            "Relative moves are often stated as changes, not levels.",
            "The size of the reaction to an event.",
            "A move large enough to look again.",
        ),
        computed=(
            "Prices change in percent; rates and probabilities in points. The start of the window is the last "
            "observation on or before the window's first day."
        ),
    ),
    IdeaExplanation(
        key="condition.date_reached",
        title="Date reached",
        measures="Met once the date or the event's scheduled time has passed.",
        why=_why(
            "A deadline for the long thesis to show results.",
            "A deadline for the short thesis to show results.",
            "A deadline for the spread to move.",
            "The scheduled time of the event.",
            "A reminder to look again.",
        ),
        computed="Compared with Gamma's clock in UTC.",
    ),
    IdeaExplanation(
        key="condition.event_occurs",
        title="Event occurs",
        measures="Met once the prediction market resolves Yes, or resolves to the outcome you chose.",
        why=_why(
            "The release the long thesis depends on is out.",
            "The release the short thesis depends on is out.",
            "The release that should move the legs apart is out.",
            "The event happened.",
            "The release is out.",
        ),
        computed="From the venue's resolution of the contract; an open or unresolved market has not occurred yet.",
    ),
    # -- states ------------------------------------------------------------
    IdeaExplanation(
        key="state.pending",
        title="Pending",
        measures="The criterion has not been evaluated yet.",
        why=_why(
            "Draft ideas are not evaluated; activate the idea to start.",
            "Draft ideas are not evaluated; activate the idea to start.",
            "Draft ideas are not evaluated; activate the idea to start.",
            "Draft ideas are not evaluated; activate the idea to start.",
            "Draft ideas are not evaluated; activate the idea to start.",
        ),
        computed="Only active ideas are evaluated; an edited rule is pending until its next evaluation.",
    ),
    IdeaExplanation(
        key="state.holding",
        title="Holding",
        measures="The latest fresh reading does not meet the condition.",
        why=_why(
            "Nothing in this rule says the long thesis is broken or confirmed yet.",
            "Nothing in this rule says the short thesis is broken or confirmed yet.",
            "The spread has not reached the rule.",
            "The event has not happened or not reached the level.",
            "Nothing to act on in this rule.",
        ),
        computed="A reading was taken and checked; missing or stale data is never shown as holding.",
    ),
    IdeaExplanation(
        key="state.triggered",
        title="Triggered",
        measures="An observation since the criterion was armed met the condition.",
        why=_why(
            "An invalidation trigger says the long thesis met the condition you set as wrong; a confirm trigger says it played out.",
            "An invalidation trigger says the short thesis met the condition you set as wrong; a confirm trigger says it played out.",
            "The spread met the rule you set in advance.",
            "The event or level you set in advance happened.",
            "The condition you set in advance happened.",
        ),
        computed=(
            "A trigger stays until the rule is edited, even if the value moves back; it keeps the value, the date "
            "first met and the source."
        ),
    ),
    IdeaExplanation(
        key="state.unavailable",
        title="Unavailable",
        measures="Gamma could not take a reading, for example because Trader Workstation is closed, a key is missing or the source failed.",
        why=_why(
            "The rule cannot say anything until the data returns.",
            "The rule cannot say anything until the data returns.",
            "The rule cannot say anything until the data returns.",
            "The rule cannot say anything until the data returns.",
            "The rule cannot say anything until the data returns.",
        ),
        computed="The reason is shown with the state; Gamma retries at the next evaluation.",
    ),
    IdeaExplanation(
        key="state.stale",
        title="Stale",
        measures="The latest reading is older than this observable normally allows and does not meet the condition.",
        why=_why(
            "Old data can hide a move that already broke the thesis.",
            "Old data can hide a move that already broke the thesis.",
            "Old data can hide a move in either leg.",
            "Old data can hide the event.",
            "Old data can hide a change.",
        ),
        computed="Each observable sets its own tolerance, for example five days for daily closes.",
    ),
    # -- cadence and kinds -------------------------------------------------
    IdeaExplanation(
        key="cadence",
        title="Cadence",
        measures="When Gamma evaluates the criterion: on open, at the daily close or intraday.",
        why=_why(
            "Daily closes avoid reacting to intraday noise.",
            "Daily closes avoid reacting to intraday noise.",
            "Daily closes keep both legs on the same clock.",
            "On open checks again whenever you look at the idea.",
            "On open is enough for slow series.",
        ),
        computed=(
            "Evaluation runs only while Gamma runs: at start, when the idea is opened, after each US close and, "
            "with Trader Workstation connected, every five minutes for intraday criteria. Without it, intraday "
            "falls back to the daily close and says so."
        ),
    ),
    IdeaExplanation(
        key="kind.invalidate",
        title="Invalidate",
        measures="A rule that, if met, says the thesis was wrong.",
        why=_why(
            "Writing it before the outcome stops the goalposts moving later.",
            "Writing it before the outcome stops the goalposts moving later.",
            "Writing it before the outcome stops the goalposts moving later.",
            "Writing it before the outcome stops the goalposts moving later.",
            "Writing it before the outcome stops the goalposts moving later.",
        ),
        computed="Kept with its trigger in the journal; I3's review counts how often invalidation fired before a loss.",
    ),
    IdeaExplanation(
        key="kind.confirm",
        title="Confirm",
        measures="A rule that, if met, says the thesis is playing out.",
        why=_why(
            "It makes \"working\" concrete instead of a feeling.",
            "It makes \"working\" concrete instead of a feeling.",
            "It makes \"working\" concrete instead of a feeling.",
            "It makes \"working\" concrete instead of a feeling.",
            "It makes \"working\" concrete instead of a feeling.",
        ),
        computed="Kept with its trigger in the journal.",
    ),
    IdeaExplanation(
        key="kind.review",
        title="Review",
        measures="A rule that, if met, asks you to look at the idea again.",
        why=_why(
            "A checkpoint, not a verdict.",
            "A checkpoint, not a verdict.",
            "A checkpoint, not a verdict.",
            "A checkpoint, not a verdict.",
            "A checkpoint, not a verdict.",
        ),
        computed="Triggers reach the notification center like the others.",
    ),
    # -- statistics shown in an idea --------------------------------------
    IdeaExplanation(
        key="stat.evidence_balance",
        title="Evidence by stance",
        measures="How many pins you tagged as supporting, challenging or context.",
        why=_why(
            "A long thesis with no challenging pins has not been tested against the other side.",
            "A short thesis with no challenging pins has not been tested against the other side.",
            "Pins on both legs show both sides were looked at.",
            "Context pins often matter most before an event.",
            "The balance shows what has been collected.",
        ),
        computed="Counted from the pins on the idea; each keeps the provenance it had when captured.",
    ),
    IdeaExplanation(
        key="stat.days_to_review",
        title="Days to review",
        measures="Days from today to the idea's review date; negative when the review is overdue.",
        why=_why(
            "A thesis without a review date tends to be held by default.",
            "A thesis without a review date tends to be held by default.",
            "A thesis without a review date tends to be held by default.",
            "Event ideas usually review right after the event.",
            "A date to look again.",
        ),
        computed="From the review date in the idea's horizon and today's date in UTC.",
    ),
)

EXPLANATIONS: Mapping[str, IdeaExplanation] = MappingProxyType({entry.key: entry for entry in _ENTRIES})


def list_explanations() -> list[IdeaExplanation]:
    return list(_ENTRIES)


def get_explanation(key: str) -> IdeaExplanation | None:
    return EXPLANATIONS.get(key)
