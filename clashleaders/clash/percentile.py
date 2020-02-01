from __future__ import annotations

from cachetools import cached, TTLCache
from collections import OrderedDict
from bisect import bisect_left
from clashleaders.clash.transformer import deep_getattr

import clashleaders.model


def clan_percentile(clan: clashleaders.model.Clan, field: str):
    value = deep_getattr(clan, field)
    percentiles = field_percentiles(field)
    index = bisect_left(list(percentiles.keys()), value)
    return list(percentiles.values())[index]


@cached(cache=TTLCache(maxsize=32, ttl=3600))
def field_percentiles(field: str):
    max_value = deep_getattr(clashleaders.model.Clan.objects.order_by(f"-{field}").first(), field)
    step = max(int(max_value / 100), 1)
    exists_field = field.replace(".", "__")
    distribution = list(
        clashleaders.model.Clan.objects(**{f"{exists_field}__exists": True}).aggregate(
            {"$group": {"_id": {"$subtract": [f"${field}", {"$mod": [f"${field}", step]}]}, "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}
        )
    )
    total = sum([e["count"] for e in distribution])
    percentiles = OrderedDict()
    i = 0
    for item in distribution:
        key = item["_id"]
        i += item["count"]
        percentiles[key] = i / total

    return percentiles
