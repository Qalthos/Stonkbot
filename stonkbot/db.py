from datetime import date
import shelve
from typing import Dict, Optional

from discord.ext import commands
from turnips.archipelago import Island, IslandModel
from turnips.multi import RangeSet
from turnips.ttime import TimePeriod

from stonkbot.models import WeekData
from stonkbot import utils


SHELVE_FILE = "turnips.db"


def rename(key: str, island_name: str) -> None:
    with shelve.open(SHELVE_FILE) as db:
        data = db.get(key)
        if not data:
            default_name = f"Island {key[-3:]}"
            data = WeekData(island=Island(name=default_name, data=IslandModel(timeline={})))
        data.rename(island_name)
        db[key] = data


def log(ctx: commands.Context, price: int, time: Optional[str] = None) -> str:
    if time:
        try:
            time = TimePeriod.normalize(time)
        except KeyError:
            return f"{time} is not a valid time period. Try 'Monday_PM' or 'Friday_AM'."

    key = str(ctx.author.id)
    with shelve.open(SHELVE_FILE) as db:
        data = db.get(key)
        if not data:
            default_name = f"Island {key[-3:]}"
            data = WeekData(island=Island(name=default_name, data=IslandModel(timeline={})))
        if not time:
            if not data.timezone:
                return (
                    "Cannot infer time period without knowing your time zone. "
                    "Try `!turnip timezone [time zone]` (e.g., America/New_York) and try again, "
                    f"or specify time period with `!turnip log {price} [Monday_AM]` or similar."
                )
            ts = ctx.message.created_at.replace(tzinfo=data.timezone)
            try:
                time = utils.datetime_to_timeperiod(ts)
            except ValueError as exc:
                return str(exc).format(price=price)
        data.set_price(price, time)
        db[key] = data

    return ""


def set_timezone(key: str, zone_name: str) -> bool:
    success = False
    with shelve.open(SHELVE_FILE) as db:
        data = db.get(key)
        if not data:
            default_name = f"Island {key[-3:]}"
            data = WeekData(island=Island(name=default_name, data=IslandModel(timeline={})))
        success = data.set_tz(zone_name)
        db[key] = data
    return success


def meta_stats() -> str:
    total = 0
    this_week = 0
    current = 0
    with shelve.open(SHELVE_FILE, flag="r") as db:
        for island in db.values():
            total += 1
            if island.is_current_week:
                this_week += 1
            if island.has_current_period:
                current += 1

    return f"I know about {total} islands, of which {this_week} have data from this week and {current} have data for right now."


def user_stats(key: str) -> str:
    with shelve.open(SHELVE_FILE, flag="r") as db:
        island_data = db[key]
    return "\n".join(island_data.summary())


def all_stats() -> str:
    islands = []
    with shelve.open(SHELVE_FILE, flag="r") as db:
        for week_data in db.values():
            if week_data.is_current_week:
                islands.append(week_data.island)

    stats: Dict[str, Dict] = {}
    for island in islands:
        for time, price_counts in island.model_group.histogram().items():
            current_stat = stats.get(time, {})

            price_set = current_stat.get("prices", RangeSet())
            for price in price_counts.keys():
                price_set.add(price)
            current_stat["prices"] = price_set
            max_price = max(price_counts.keys())

            price_type = "possibility"
            if len(island.model_group) == 1:
                price_type = "range"
            if len(price_counts) == 1:
                price_type = "fixed"

            top_prices = current_stat.get("top_prices", [])
            top_prices.append((max_price, island.name, price_type))
            current_stat["top_prices"] = sorted(top_prices, reverse=True)

            stats[time] = current_stat

    longest_price_set = 15
    for stat in stats.values():
        longest_price_set = max(longest_price_set, len(str(stat["prices"])))

    msg = []
    start = date.today().isoweekday() % 7 * 2
    if start != 0:
        msg.extend([f"Island forecasts for {TimePeriod(start).name[:-3]}:", "```"])
        msg.append(f"AM: {top_islands(stats[TimePeriod(start).name]['top_prices'], 5)}")
        msg.append(f"PM: {top_islands(stats[TimePeriod(start + 1).name]['top_prices'], 5)}")
        msg.append("```")

    start += 2

    msg.append("Predictions for the rest of the week:")
    msg.extend(["```", f"Time          {'Possible Prices'.ljust(longest_price_set)}  Top Three Islands"])
    for i in range(start, 14):
        time = TimePeriod(i).name
        stat_bundle = stats[time]
        prices = str(stat_bundle['prices']).ljust(longest_price_set)
        msg.append(f"{time:12}  {prices}  {top_islands(stat_bundle['top_prices'])}")
    msg.append("```")
    msg.append("* number is exactly as reported on island")
    msg.append("† number is possible on island, but pattern has not been confirmed")

    return "\n".join(msg)


def top_islands(top_prices, length: int = 3) -> str:
    prices = []
    for datum in top_prices[:length]:
        note = "*" if datum[2] == "fixed" else "†" if datum[2] == "possibility" else " "
        name = f"({datum[1]})".ljust(12)
        prices.append(f"{datum[0]:3d}{note} {name}")
    return ' '.join(prices)
