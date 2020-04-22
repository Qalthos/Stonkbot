from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from turnips.archipelago import Island
from turnips.ttime import TimePeriod
from turnips.meta import MetaModel
from turnips.model import ModelEnum
from turnips.multi import RangeSet


@dataclass
class WeekData:
    island: Island
    updated: datetime = datetime(2020, 3, 20)

    def set_price(self, price: int, time: TimePeriod):
        if not self.is_current_week:
            if self.is_last_week:
                self.set_previous_week()
            self.island._data.timeline = {}

        if price:
            self.island._data.timeline[time] = price
        elif time in self.island._data.timeline:
            del self.island._data.timeline[time]
        self.island.process()
        self.updated = datetime.now()

    def set_previous_week(self):
        mgroup = self.island.model_group
        model_counter = Counter(model.model_type for model in mgroup.models)

        if len(model_counter) == 1:
            self.island._data.previous_week = model_counter.most_common()[0][0]
        else:
            self.island._data.previous_week = ModelEnum.unknown

    def rename(self, new_name):
        self.island._name = new_name

    @property
    def is_current_week(self):
        now = datetime.now()
        sunday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.isoweekday() % 7)
        return self.updated > sunday

    @property
    def is_last_week(self):
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sunday = midnight - timedelta(days=midnight.isoweekday() % 7)
        last_sunday = midnight - timedelta(days=(midnight.isoweekday() % 7) + 7)
        return sunday > self.updated > last_sunday

    @property
    def prophet_link(self):
        url = "https://turnipprophet.io/?prices={prices}&pattern={pattern}"
        pattern_map = {
            ModelEnum.triple: 0,
            ModelEnum.spike: 1,
            ModelEnum.decay: 2,
            ModelEnum.bump: 3,
            ModelEnum.unknown: 4,
        }
        prices = [str(self.island._data.base_price or "")] + [str(self.island._data.timeline.get(TimePeriod(i), "")) for i in range(2, 14)]
        return url.format(prices=".".join(prices), pattern=pattern_map[self.island.previous_week])

    def summary(self):
        yield f"Here's what I know about {self.island.name}:"
        mgroup = self.island.model_group

        fixed_points = {}
        speculations = {}
        pwidth = 0
        lwidth = 0
        last_fixed = "Sunday_PM"
        for time, pricecounts in mgroup.histogram().items():
            if len(pricecounts) == 1:
                fixed_points[time] = next(iter(pricecounts.keys()))
                last_fixed = time
                continue

            stats = {}
            # Gather possible prices
            pset = RangeSet()
            for price in pricecounts.keys():
                pset.add(price)
            stats["all"] = str(pset)
            pwidth = max(pwidth, len(str(pset)))

            # Determine likeliest price(s)
            n_possibilities = sum(pricecounts.values())
            likeliest = max(pricecounts.items(), key=lambda x: x[1])
            likelies = list(filter(lambda x: x[1] >= likeliest[1], pricecounts.items()))

            sample_size = len(likelies) * likeliest[1]
            pct = 100 * (sample_size / n_possibilities)
            stats["chance"] = pct

            rset = RangeSet()
            for likely in likelies:
                rset.add(likely[0])
            stats["likely"] = str(rset)
            lwidth = max(lwidth, len(str(rset)))

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

        model_count = Counter(model.model_name for model in mgroup.models)
        # probably_model, probably_count = model_count.most_common(1)[0]
        # yield f"I think there is a {probably_count / len(mgroup) * 100:.02f}% chance this is a {probably_model} pattern"
        patterns = model_count.most_common()
        pattern_strs = [f"{count} {'are' if count > 1 else 'is'} {name}" for name, count in patterns]
        if len(patterns) == 1:
            yield f"Your pattern is {patterns[0][0]}"
        elif len(patterns) == 2:
            yield f"Out of {len(mgroup)} possible patterns, {' and '.join(pattern_strs)}"
        else:
            pattern_strs[-1] = f"and {pattern_strs[-1]}"
            yield f"Out of {len(mgroup)} possible patterns, {', '.join(pattern_strs)}"

        if TimePeriod[last_fixed] != TimePeriod.Saturday_PM:
            yield "```"
            yield f"Time          {'Price'.ljust(pwidth)}  {'Likely'.ljust(lwidth)}  Odds"
            for i in range(TimePeriod[last_fixed].value + 1, 14):
                time = TimePeriod(i).name
                stats = speculations[time]
                yield f"{time:12}  {stats['all']:{pwidth}}  {stats['likely']:{lwidth}}  ({stats['chance']:0.2f}%)"

            yield "```"
            yield f"For more detail, check {self.prophet_link}"
