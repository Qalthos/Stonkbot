import collections
from dataclasses import dataclass, field
from datetime import date, timezone
import logging
import operator
import shelve
from typing import Counter, Dict, List, Optional

from discord.ext import commands
from turnips.model import ModelEnum
from turnips.multi import RangeSet
from turnips.ttime import TimePeriod

from stonkbot.models import WeekData
from stonkbot import utils


SHELVE_FILE = "turnips.db"
logger = logging.getLogger("stonkbot")


# Helper dataclasses & functions
@dataclass
class StatBundle:
    max_price: int
    name: str
    confidence: str


@dataclass
class PriceBundle:
    prices: RangeSet = field(default_factory=RangeSet)
    _top_prices: List[StatBundle] = field(default_factory=list)

    def add_price(self, stats: StatBundle):
        self._top_prices.append(stats)

    @property
    def top_prices(self) -> List[StatBundle]:
        return list(sorted(self._top_prices, key=operator.attrgetter("max_price"), reverse=True))


def _islands_to_stats(islands: List[WeekData]) -> Dict[str, PriceBundle]:
    stats: Dict[str, PriceBundle] = {}
    for island in islands:
        for time, price_counts in island.models.histogram().items():
            current_stat = stats.get(time, PriceBundle())

            for price in price_counts.keys():
                current_stat.prices.add(price)
            max_price = max(price_counts.keys())

            price_type = "possibility"
            if len(island.models) == 1:
                price_type = "range"
            if len(price_counts) == 1:
                price_type = "fixed"

            current_stat.add_price(StatBundle(max_price, name=island.name, confidence=price_type))

            stats[time] = current_stat

    return stats


def _top_islands(top_prices: List[StatBundle], length: int = 3) -> str:
    prices = []
    for stat in top_prices[:length]:
        note = "*" if stat.confidence == "fixed" else "†" if stat.confidence == "possibility" else " "
        name = f"({stat.name})".ljust(12)
        prices.append(f"{stat.max_price:3d}{note} {name}")
    return ' '.join(prices)


# Read-only functions
def meta_stats() -> str:
    total = 0
    this_week = 0
    current = 0
    patterns: Counter[ModelEnum] = collections.Counter()
    with shelve.open(SHELVE_FILE, flag="r") as shelf:
        for island in shelf.values():
            total += 1
            if island.is_current_week:
                this_week += 1
            if island.has_current_period:
                current += 1
            patterns[island.current_pattern] += 1

    pattern_str = ", ".join(f"{count} {'has' if count == 1 else 'have'} pattern {model.name}" for model, count in patterns.items())
    return f"I know about {total} islands, of which {this_week} have data from this week and {current} have data for right now.\n{pattern_str}"


def user_stats(key: str) -> str:
    with shelve.open(SHELVE_FILE, flag="r") as shelf:
        island_data = shelf[key]
    return "\n".join(island_data.summary())


def all_stats() -> str:
    islands = []
    with shelve.open(SHELVE_FILE, flag="r") as shelf:
        for week_data in shelf.values():
            if week_data.is_current_week:
                islands.append(week_data)

    stats = _islands_to_stats(islands)

    msg = []
    start = date.today().isoweekday() % 7 * 2
    if start != 0:
        msg.extend([f"Island forecasts for {TimePeriod(start).name[:-3]}:", "```"])
        msg.append(f"AM: {_top_islands(stats[TimePeriod(start).name].top_prices, 5)}")
        msg.append(f"PM: {_top_islands(stats[TimePeriod(start + 1).name].top_prices, 5)}")
        msg.append("```")

    start += 2

    longest_price_set = max(15, *(len(str(stat.prices)) for stat in stats.values()))
    msg.append("Predictions for the rest of the week:")
    msg.extend(["```", f"Time          {'Possible Prices'.ljust(longest_price_set)}  Top Three Islands"])
    for i in range(start, 14):
        time = TimePeriod(i).name
        stat_bundle = stats[time]
        prices = str(stat_bundle.prices).ljust(longest_price_set)
        msg.append(f"{time:12}  {prices}  {_top_islands(stat_bundle.top_prices)}")
    msg.append("```")
    msg.append("* number is exactly as reported on island")
    msg.append("† number is possible on island, but pattern has not been confirmed")

    return "\n".join(msg)


# Modifying functions
def rename(key: str, island_name: str) -> None:
    with shelve.open(SHELVE_FILE) as shelf:
        data = shelf.get(key)
        if not data:
            data = WeekData(name=island_name, timeline={})
        else:
            data.name = island_name
        shelf[key] = data


def log(ctx: commands.Context, price: int, time: Optional[str] = None) -> str:
    if time:
        try:
            time = TimePeriod.normalize(time)
        except KeyError:
            return f"{time} is not a valid time period. Try 'Monday_PM' or 'Friday_AM'."

    key = str(ctx.author.id)
    with shelve.open(SHELVE_FILE) as shelf:
        data = shelf.get(key)
        if not data:
            default_name = f"Island {key[-3:]}"
            data = WeekData(name=default_name, timeline={})
        if not time:
            if not data.timezone:
                return (
                    "Cannot infer time period without knowing your time zone. "
                    "Try `!turnip timezone [time zone]` (e.g., America/New_York) and try again, "
                    f"or specify time period with `!turnip log {price} [Monday_AM]` or similar."
                )
            # Get message created time (which is UTC) and convert to user's local time
            timestamp = ctx.message.created_at.replace(tzinfo=timezone.utc).astimezone(data.timezone)
            logger.info("Computed local message time as %s", timestamp.isoformat())
            try:
                time = utils.datetime_to_timeperiod(timestamp)
                logger.info("Trunip time period is %s", time)
            except ValueError as exc:
                return str(exc).format(price=price)
        data.set_price(price, time)
        shelf[key] = data

    return ""


def set_timezone(key: str, zone_name: str) -> bool:
    success = False
    with shelve.open(SHELVE_FILE) as shelf:
        data = shelf.get(key)
        if not data:
            default_name = f"Island {key[-3:]}"
            data = WeekData(name=default_name, timeline={})
        success = data.set_tz(zone_name)
        shelf[key] = data
    return success
