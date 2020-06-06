from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from typing import Dict, Iterable, Optional

from dateutil import tz
from turnips.ttime import TimePeriod
from turnips.model import ModelEnum
from turnips.meta import MetaModel
from turnips.multi import RangeSet, MultiModel, BumpModels


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
    name: str

    timeline: Dict[TimePeriod, int]
    _initial_week: bool = False
    _previous_week: ModelEnum = ModelEnum.unknown

    updated: datetime = datetime(2020, 3, 20)
    record: Record = Record(0, date.min, False)
    tz_name: str = ""

    def set_price(self, price: int, time: TimePeriod) -> None:
        if not self.is_current_week:
            if self.is_last_week:
                self._previous_week = self.current_pattern
                self._initial_week = False
            self.timeline = {}

        if price:
            self.timeline[time] = price
            if price > self.record.price:
                self.record.set_price(price, time.value % 2 == 1)
        elif time in self.timeline:
            del self.timeline[time]
        self.updated = datetime.now(tz=self.timezone)

    def set_tz(self, zone_name: str) -> bool:
        if tz.gettz(zone_name):
            self.tz_name = zone_name
            self.updated = self.updated.astimezone(self.timezone)
            return True
        return False

    def summary(self) -> Iterable[str]:
        yield f"Here's what I know about {self.name}:"

        fixed_points: Dict[str, int] = {}
        speculations: Dict[str, str] = {}
        last_fixed: Optional[str] = None
        buy_price = self.timeline.get(TimePeriod.Sunday_AM)
        if buy_price:
            fixed_points["Sunday_AM"] = buy_price
            last_fixed = "Sunday_PM"
        for time, price_counts in self.models.histogram().items():
            if len(price_counts) == 1:
                fixed_points[time] = list(price_counts.keys())[0]
                last_fixed = time
                continue

            # Gather possible prices
            price_set = RangeSet()
            for price in price_counts.keys():
                price_set.add(price)
            speculations[time] = str(price_set)

        if last_fixed:
            days = ["Buy"]
            values = [str(fixed_points.get("Sunday_AM", "--")).center(3)]
            for i in range(2, TimePeriod[last_fixed].value + 1):
                time = TimePeriod(i).name
                price = str(fixed_points.get(time, "--"))
                values.append(price.center(4))
                if i % 2 == 0:
                    days.append(time[:-3].center(9))

            yield "```"
            yield "|".join(days)
            yield "|".join(values)
            yield "```"

        yield self.predictions()

        if last_fixed != "Saturday_PM":
            price_width = max((len(stat) for stat in speculations.values()))
            yield "```"
            yield f"Time          {'Price'.ljust(price_width)}"
            for i in range(TimePeriod[last_fixed].value + 1, 14):
                time = TimePeriod(i).name
                stats = speculations[time]
                yield f"{time:12}  {stats:{price_width}}"

            yield "```"
            yield f"For more detail, check <{self.prophet_link}>"

    def predictions(self) -> str:
        model_count = Counter(model.model_name for model in self.models.models)
        patterns = model_count.most_common()

        if len(patterns) == 0:
            return "Uh oh! Your prices don't match any pattern I know about"
        if len(patterns) == 1:
            pattern = patterns[0][0]
            if pattern == "decay":
                pattern += ". Better luck next week"
            return f"Your pattern is {pattern}."
        if self._previous_week == ModelEnum.unknown:
            pattern_str_list = [f"{count} {'are' if count > 1 else 'is'} {name}" for name, count in patterns]
            pattern_str_list[-1] = f"and {pattern_str_list[-1]}"
            if len(patterns) == 2:
                return f"Out of {len(self.models)} possible patterns, {' '.join(pattern_str_list)}."
            return f"Out of {len(self.models)} possible patterns, {', '.join(pattern_str_list)}."

        weights = [
            [20, 30, 15, 35],
            [50, 5, 20, 25],
            [25, 45, 5, 25],
            [45, 25, 15, 15],
        ]
        expected_patterns = [56, 7, 1, 8]
        expected_weights = weights[self._previous_week.value]
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
    def models(self) -> MultiModel:
        base = self.timeline.get(TimePeriod.Sunday_AM)
        if self._initial_week:
            models = BumpModels()
        else:
            models = MetaModel.blank(base)

        for time, price in self.timeline.items():
            if price is None:
                continue
            if time.value < TimePeriod.Monday_AM.value:
                continue
            models.fix_price(time, price)
        return models

    @property
    def current_pattern(self) -> ModelEnum:
        model_counter = Counter(model.model_type for model in self.models.models)

        if len(model_counter) == 1:
            return model_counter.most_common()[0][0]
        return ModelEnum.unknown

    @property
    def timezone(self) -> Optional[tzinfo]:
        return tz.gettz(self.tz_name)

    @property
    def is_current_week(self) -> bool:
        now = datetime.now(tz=self.timezone)
        sunday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.isoweekday() % 7)
        return self.updated > sunday

    @property
    def is_last_week(self) -> bool:
        midnight = datetime.now(tz=self.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        sunday = midnight - timedelta(days=midnight.isoweekday() % 7)
        last_sunday = midnight - timedelta(days=(midnight.isoweekday() % 7) + 7)
        return sunday > self.updated > last_sunday

    @property
    def has_current_period(self) -> bool:
        now = datetime.now(tz=self.timezone)
        weekday = now.isoweekday() % 7
        time_index = (weekday * 2) + int(now.hour >= 12)

        # Don't bother looking for Sunday_PM
        if time_index == 1:
            time_index = 0
        return TimePeriod(time_index) in self.timeline

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
        prices = [str(self.timeline.get(TimePeriod.Sunday_AM, ""))]
        prices.extend((str(self.timeline.get(TimePeriod(i), "")) for i in range(2, 14)))
        return url.format(prices=".".join(prices), pattern=pattern_map[self._previous_week])

    # Migration methods
    def dump(self) -> dict:
        return {
            "island_name": self.name,
            "updated": self.updated.isoformat(),
            "prices": {k.name: v for k, v in self.timeline.items()},
            "last_week": self._previous_week.name,
            "record": self.record.dump(),
            "timezone": self.tz_name,
        }

    @classmethod
    def load(cls, data) -> WeekData:
        timeline = {TimePeriod[k]: v for k, v in data["prices"].items()}
        previous_week = ModelEnum[data["last_week"]]
        updated = datetime.fromisoformat(data["updated"])
        record = Record.load(data["record"])
        instance = cls(name=data["island_name"], timeline=timeline, _previous_week=previous_week, updated=updated, record=record, tz_name=data["timezone"])
        return instance
