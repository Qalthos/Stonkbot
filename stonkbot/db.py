import shelve
from typing import Dict

from turnips.archipelago import Island, IslandModel
from turnips.multi import RangeSet
from turnips.ttime import TimePeriod

from stonkbot.models import WeekData


def rename(key: str, island_name: str) -> bool:
    with shelve.open("turnips.db") as db:
        data = db.get(key)
        if not data:
            return False
        data.rename(island_name)
        db[key] = data
    return True


def log(key: str, price: int, time: TimePeriod) -> None:
    with shelve.open("turnips.db") as db:
        data = db.get(key)
        if not data:
            data = WeekData(island=Island(name=key, data=IslandModel(timeline={})))
        data.set_price(price, time)
        db[key] = data


def user_stats(key: str) -> str:
    with shelve.open("turnips.db", flag="r") as db:
        island_data = db[key]
    return "\n".join(island_data.summary())


def all_stats() -> str:
    islands = []
    with shelve.open("turnips.db", flag="r") as db:
        for data in db.values():
            if data.is_current_week:
                islands.append(data.island)

    stats: Dict[str, Dict] = {}
    longest_price_set = 0
    for island in islands:
        for time, price_counts in island.model_group.histogram().items():
            current_stat = stats.get(time, {})

            price_set = current_stat.get("prices", RangeSet())
            for price in price_counts.keys():
                price_set.add(price)
            longest_price_set = max(longest_price_set, len(str(price_set)))
            current_stat["prices"] = price_set
            max_price = max(price_counts.keys())

            if current_stat.get("top_price", {}).get("price", 0) < max_price:
                current_stat["top_price"] = dict(name=island.name, price=max_price)

            stats[time] = current_stat

    msg = ["```", f"Time          {'Possible Prices'.ljust(longest_price_set)} Top Possible Island"]
    for time, stat_bundle in stats.items():
        prices = str(stat_bundle['prices']).ljust(longest_price_set)
        top_island = f"{stat_bundle['top_price']['price']} at {stat_bundle['top_price']['name']}"
        msg.append(f"{str(time):13} {prices} {top_island}")
    msg.append("```")

    return "\n".join(msg)
