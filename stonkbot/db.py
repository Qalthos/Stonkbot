import shelve
from typing import Dict

from turnips.archipelago import Island, IslandModel
from turnips.multi import RangeSet
from turnips.ttime import TimePeriod

from stonkbot.models import WeekData


SHELVE_FILE = "turnips.db"


def rename(key: str, island_name: str) -> bool:
    with shelve.open(SHELVE_FILE) as db:
        data = db.get(key)
        if not data:
            return False
        data.rename(island_name)
        db[key] = data
    return True


def log(key: str, price: int, time: TimePeriod) -> None:
    with shelve.open(SHELVE_FILE) as db:
        data = db.get(key)
        if not data:
            default_name = f"Island {key[-3:]}"
            data = WeekData(island=Island(name=default_name, data=IslandModel(timeline={})))
        data.set_price(price, time)
        db[key] = data


def meta_stats() -> str:
    islands = 0
    current = 0
    with shelve.open(SHELVE_FILE, flag="r") as db:
        islands = len(db.keys())
        current = len([v for v in db.values() if v.is_current_week])

    return f"I know about {islands} islands, of which I have current data for {current} of them."


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

    msg = ["```", f"Time          {'Possible Prices'.ljust(longest_price_set)}  Top Three Islands"]
    for time, stat_bundle in stats.items():
        prices = str(stat_bundle['prices']).ljust(longest_price_set)
        top_islands = []
        for datum in stat_bundle["top_prices"][:3]:
            note = "*" if datum[2] == "fixed" else "†" if datum[2] == "possibility" else ""
            top_islands.append(f"{datum[0]}{note} ({datum[1]})")
        msg.append(f"{str(time):12}  {prices}  {' '.join(top_islands)}")
    msg.append("```")
    msg.append("* number is exactly as reported on island")
    msg.append("† number is possible on island, but pattern has not been confirmed")

    return "\n".join(msg)
