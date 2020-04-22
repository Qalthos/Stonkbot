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
    with shelve.open("turnips.db", flag="r") as db:
        islands = []
        for data in db.values():
            if data.is_current_week:
                islands.append(data.island.model_group)
        model = MetaModel(-1, islands)
    return "\n".join(summary(model))


def summary(model):
    yield "```"
    yield "Time          Prices"

    for time, pricecounts in model.histogram().items():
        # Gather possible prices
        pset = RangeSet()
        for price in pricecounts.keys():
            pset.add(price)

        yield f"{str(time):13} {str(pset)}"

    yield "```"
