from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from typing import Iterable, Optional

from dateutil import tz
from turnips.archipelago import Island, IslandModel
from turnips.ttime import TimePeriod
from turnips.model import ModelEnum
from turnips.multi import RangeSet


@dataclass
class Record:
    price: int
    date: date
    is_am: bool

    def set_price(self, price: int, is_am: bool):
        self.price = price
        self.date = date.today()
        self.is_am = is_am

    def dump(self):
        return {
            "price": self.price,
            "date": self.date.isoformat(),
            "is_am": self.is_am,
        }

    @classmethod
    def load(cls, data):
        return cls(price=data["price"], date=date.fromisoformat(data["date"]), is_am=data["is_am"])


@dataclass
class WeekData:
    island: Island
    updated: datetime = datetime(2020, 3, 20)
    record: Record = Record(0, date.min, False)
    tz_name: Optional[str] = None

    def set_price(self, price: int, time: TimePeriod):
        if not self.is_current_week:
            if self.is_last_week:
                self.set_previous_week()
            self.data.timeline = {}

        if price:
            self.data.timeline[time] = price
            if price > self.record.price:
                self.record.set_price(price, time.value % 2 == 1)
        elif time in self.data.timeline:
            del self.data.timeline[time]
        self.island.process()
        self.updated = datetime.now()

    def set_previous_week(self):
        model_group = self.island.model_group
        model_counter = Counter(model.model_type for model in model_group.models)

        if len(model_counter) == 1:
            self.data.previous_week = model_counter.most_common()[0][0]
        else:
            self.data.previous_week = ModelEnum.unknown

    def set_tz(self, zone_name: str) -> bool:
        if tz.gettz(zone_name):
            self.tz_name = zone_name
            return True
        return False

    def rename(self, new_name):
        self.island._name = new_name

    def summary(self):
        yield f"Here's what I know about {self.island.name}:"
        model_group = self.island.model_group

        fixed_points = {}
        speculations = {}
        price_width = 0
        last_fixed = "Sunday_PM"
        for time, price_counts in model_group.histogram().items():
            if len(price_counts) == 1:
                fixed_points[time] = list(price_counts.keys())[0]
                last_fixed = time
                continue

            stats = {}
            # Gather possible prices
            price_set = RangeSet()
            for price in price_counts.keys():
                price_set.add(price)
            stats["all"] = str(price_set)
            price_width = max(price_width, len(str(price_set)))

            speculations[time] = stats

        if TimePeriod[last_fixed] != TimePeriod.Sunday_PM:
            days = []
            values = []
            for i in range(2, TimePeriod[last_fixed].value + 1):
                time = TimePeriod(i).name
                price = str(fixed_points.get(time, '--'))
                values.append(price.center(4))
                if i % 2 == 0:
                    days.append(time[:-3].center(9))

            yield "```"
            yield "|".join(days)
            yield "|".join(values)
            yield "```"

        yield self.predictions()

        if TimePeriod[last_fixed] != TimePeriod.Saturday_PM:
            yield "```"
            yield f"Time          {'Price'.ljust(price_width)}"
            for i in range(TimePeriod[last_fixed].value + 1, 14):
                time = TimePeriod(i).name
                stats = speculations[time]
                yield f"{time:12}  {stats['all']:{price_width}}"

            yield "```"
            yield f"For more detail, check <{self.prophet_link}>"

    def predictions(self) -> str:
        model_group = self.island.model_group
        model_count = Counter(model.model_name for model in model_group.models)
        patterns = model_count.most_common()

        if len(patterns) == 0:
            return "Uh oh! Your prices don't match any pattern I know about"
        if len(patterns) == 1:
            pattern = patterns[0][0]
            if pattern == "decay":
                pattern += ". Better luck next week"
            return f"Your pattern is {pattern}."
        if self.island.previous_week == ModelEnum.unknown:
            pattern_str_list = [f"{count} {'are' if count > 1 else 'is'} {name}" for name, count in patterns]
            pattern_str_list[-1] = f"and {pattern_str_list[-1]}"
            if len(patterns) == 2:
                return f"Out of {len(model_group)} possible patterns, {' '.join(pattern_str_list)}."
            return f"Out of {len(model_group)} possible patterns, {', '.join(pattern_str_list)}."

        weights = [
            [20, 30, 15, 35],
            [50, 5, 20, 25],
            [25, 45, 5, 25],
            [45, 25, 15, 15],
        ]
        expected_patterns = [56, 7, 1, 8]
        expected_weights = weights[self.island.previous_week.value]
        probabilities = [0, 0, 0, 0]
        for pattern_name, count in patterns:
            model_value = ModelEnum[pattern_name].value
            probabilities[model_value] = count / expected_patterns[model_value] * expected_weights[model_value]

        pattern_str_list = [
            f"{factor / sum(probabilities) * 100:.1f}% likely to be {ModelEnum(i).name}"
            for i, factor in enumerate(probabilities) if factor > 0
        ]
        pattern_str_list[-1] = f"and {pattern_str_list[-1]}"
        if len(patterns) == 2:
            return f"Your pattern is {' '.join(pattern_str_list)}."
        return f"Your pattern is {', '.join(pattern_str_list)}."

    @property
    def data(self):
        return self.island._data

    @property
    def timezone(self):
        return tz.gettz(self.tz_name)

    @property
    def is_current_week(self) -> bool:
        now = datetime.now()
        sunday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.isoweekday() % 7)
        return self.updated > sunday

    @property
    def is_last_week(self) -> bool:
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sunday = midnight - timedelta(days=midnight.isoweekday() % 7)
        last_sunday = midnight - timedelta(days=(midnight.isoweekday() % 7) + 7)
        return sunday > self.updated > last_sunday

    @property
    def prophet_link(self) -> str:
        url = "https://turnipprophet.io/?prices={prices}&pattern={pattern}"
        pattern_map = {
            ModelEnum.triple: 0,
            ModelEnum.spike: 1,
            ModelEnum.decay: 2,
            ModelEnum.bump: 3,
            ModelEnum.unknown: 4,
        }
        prices = [str(self.data.base_price or "")]
        prices.extend((str(self.data.timeline.get(TimePeriod(i), "")) for i in range(2, 14)))
        return url.format(prices=".".join(prices), pattern=pattern_map[self.island.previous_week])

    # Migration methods
    def dump(self) -> dict:
        return {
            "island_name": self.island.name,
            "updated": self.updated.isoformat(),
            "prices": {k.name: v for k, v in self.data.timeline.items()},
            "last_week": self.island.previous_week.name,
            "record": self.record.dump(),
            "timezone": self.timezone,
        }

    @classmethod
    def load(cls, data):
        timeline = {TimePeriod[k]: v for k, v in data["prices"].items()}
        island = Island(name=data["island_name"], data=IslandModel(timeline=timeline))
        updated = datetime.fromisoformat(data["updated"])
        record = Record.load(data["record"])
        instance = cls(island=island, updated=updated, record=record, timezone=data["timezone"])
        instance.data.previous_week = ModelEnum[data["last_week"]]
        return instance
