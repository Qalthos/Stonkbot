from datetime import datetime

from turnips.ttime import TimePeriod


def datetime_to_timeperiod(dt: datetime) -> TimePeriod:
    weekday = dt.isoweekday() % 7
    if dt.hour < 8:
        raise ValueError(
            "This is way too early to log a price. If you meant to log a price for another "
            "day, try `!turnip log {price} [time period]` instead."
        )
    if weekday == 0 and dt.hour >= 12:
        raise ValueError(
            "Daisy Mae has already left your island. If you still want to log Sunday "
            "prices, use `!turnip log {price} Sunday_AM` instead."
        )
    if dt.hour >= 22:
        raise ValueError(
            "Nook's Cranny is closed for the day, but if you want to log past prices, "
            "use `!turnip log {price} [time period]` instead."
        )
    return TimePeriod(weekday * 2 + (0 if dt.hour < 12 else 1))
