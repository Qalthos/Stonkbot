import shelve

from turnips.archipelago import Island, IslandModel
from turnips.meta import MetaModel
from turnips.multi import RangeSet
from turnips.ttime import TimePeriod

from models import WeekData


def rename(key: str, island_name: str):
    with shelve.open("turnips.db") as db:
        data = db.get(key)
        if not data:
            return
        data.rename(island_name)
        db[key] = data


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

    stats = {}
    longest_pset = 0
    for island in islands:
        for time, pricecounts in island.model_group.histogram().items():
            current_stat = stats.get(time, {})

            pset = current_stat.get("prices", RangeSet())
            for price in pricecounts.keys():
                pset.add(price)
            longest_pset = max(longest_pset, len(str(pset)))
            current_stat["prices"] = pset
            max_price = max(pricecounts.keys())

            if current_stat.get("top_price", {}).get("price", 0) < max_price:
                current_stat["top_price"] = dict(name=island.name, price=max_price)

            stats[time] = current_stat

    msg = ["```", f"Time          {'Possible Prices'.ljust(longest_pset)} Top Possible Island"]
    for time, statbundle in stats.items():
        msg.append(f"{str(time):13} {str(statbundle['prices']).ljust(longest_pset)} {statbundle['top_price']['price']} at {statbundle['top_price']['name']}")
    msg.append("```")

    return "\n".join(msg)
