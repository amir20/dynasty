from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import pandas as pd
from mongoengine import DateTimeField, DictField, DynamicDocument, EmbeddedDocumentField, IntField, ListField, Q, StringField
from slugify import slugify

import clashleaders.clash.clan_calculation
import clashleaders.clash.transformer
import clashleaders.model
import clashleaders.queue.calculation
import clashleaders.queue.player
from clashleaders.clash import api
from clashleaders.clash.api import clan_warlog
from clashleaders.insights.clan_activity import clan_status
from clashleaders.model.clan_delta import ClanDelta
from clashleaders.text.clan_description_processor import transform_description

logger = logging.getLogger(__name__)


class Clan(DynamicDocument):
    updated_on = DateTimeField(default=datetime.now)
    tag: str = StringField(required=True, unique=True)
    slug: str = StringField(required=True)
    cluster_label = IntField(default=-1)
    members: int = IntField()
    active_members: int = IntField()
    inactive_members: int = IntField()
    new_members: int = IntField()
    clanPoints: int = IntField()
    clanVersusPoints: int = IntField()
    page_views: int = IntField(default=0)
    name: str = StringField()
    description: str = StringField()
    badgeUrls = DictField()
    location = DictField()
    clanLevel: int = IntField()
    verified_accounts = ListField(StringField())
    computed: ClanDelta = EmbeddedDocumentField(ClanDelta)
    day_delta: ClanDelta = EmbeddedDocumentField(ClanDelta)
    week_delta: ClanDelta = EmbeddedDocumentField(ClanDelta)
    month_delta: ClanDelta = EmbeddedDocumentField(ClanDelta)
    labels: List[Dict] = ListField(DictField())
    warLeague: Dict = DictField()
    warLosses: int = IntField(default=0)
    warTies: int = IntField(default=0)
    warWins: int = IntField(default=0)

    meta = {
        "index_background": True,
        "indexes": [
            "updated_on",
            "location.countryCode",
            "cluster_label",
            ("cluster_label", "clanPoints"),
            "verified_accounts",
            "clanPoints",
            "clanVersusPoints",
            "tag",
            "slug",
            "members",
            "active_members",
            "inactive_members",
            ("members", "-clanPoints"),
            ("members", "-clanVersusPoints"),
            "isWarLogPublic",
            "page_views",
            # Aggregated indexes
            "week_delta.avg_attack_wins",
            "week_delta.avg_versus_wins",
            # Active clans
            ["week_delta.total_attack_wins", "updated_on", "members"],
            ["active_members", "updated_on"],
            ["active_members", "-updated_on"],
            "computed.total_attack_wins",
            # Leaderboards
            "week_delta.total_trophies",
            "week_delta.total_gold_grab",
            # Country
            ("location.countryCode", "-clanPoints"),
            ("location.countryCode", "-month_delta.avg_cwl_stars_percentile"),
            ("location.countryCode", "-month_delta.avg_games_xp_percentile"),
            ("location.countryCode", "-week_delta.avg_war_stars_percentile"),
            ("location.countryCode", "-week_delta.avg_donations_percentile"),
            ("location.countryCode", "-week_delta.avg_attack_wins_percentile"),
            # Explore
            "week_delta.avg_gold_grab",
            "week_delta.avg_donations",
            "week_delta.avg_war_stars",
            "month_delta.avg_cwl_stars_percentile",
            "month_delta.avg_games_xp_percentile",
            "week_delta.avg_war_stars_percentile",
            "week_delta.avg_donations_percentile",
            "week_delta.avg_attack_wins_percentile",
            # For computing clan activity
            "computed.avg_donations",
            "computed.avg_games_xp",
            "computed.avg_cwl_stars",
            "computed.avg_attack_wins",
        ],
    }

    @property
    def rich_description(self):
        return transform_description(self.description)

    @property
    def war_total(self) -> int:
        return self.warLosses + self.warTies + self.warWins

    @property
    def war_win_ratio(self) -> float:
        return 0 if self.war_total == 0 else self.warWins / self.war_total

    def update_calculations(self):
        return clashleaders.clash.clan_calculation.update_calculations(self)

    def to_historical_df(self) -> pd.DataFrame:
        histories = clashleaders.model.HistoricalClan.objects(tag=self.tag)
        df = pd.DataFrame(h.to_dict() for h in histories)
        return df.set_index("created_on")

    def historical_near_time(self, dt) -> clashleaders.model.HistoricalClan:
        return clashleaders.model.HistoricalClan.find_by_tag_near_time(tag=self.tag, dt=dt)

    def historical_near_days_ago(self, days) -> clashleaders.model.HistoricalClan:
        dt = datetime.now() - timedelta(days=int(days))
        return clashleaders.model.HistoricalClan.find_by_tag_near_time(tag=self.tag, dt=dt)

    def historical_near_now(self) -> clashleaders.model.HistoricalClan:
        return clashleaders.model.HistoricalClan.find_by_tag_near_time(tag=self.tag, dt=datetime.now())

    def similar_clans(self) -> Tuple[int, List[Clan]]:
        less = Clan.objects(cluster_label=self.cluster_label, clanPoints__lt=self.clanPoints).order_by("-clanPoints").limit(4)
        more = Clan.objects(cluster_label=self.cluster_label, clanPoints__gt=self.clanPoints).order_by("clanPoints").limit(2)

        clans = sorted([*less, self, *more], key=lambda c: c.clanPoints, reverse=True)[:5]
        start_count = Clan.objects(cluster_label=self.cluster_label, clanPoints__gt=clans[0].clanPoints).count() + 1

        return start_count, clans

    def days_of_history(self) -> int:
        first: clashleaders.model.HistoricalClan = clashleaders.model.HistoricalClan.objects(tag=self.tag).order_by("created_on").first()
        return (datetime.now() - first.created_on).days

    def player_activity(self):
        return clan_status(self)

    def trophy_history(self) -> Dict:
        df = self.to_historical_df()[["members", "clanPoints"]].resample("D").mean().dropna()
        df = df.reset_index().rename(columns={"created_on": "labels"})
        df["labels"] = df["labels"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00Z")
        return df.to_dict("list")

    def warlog(self):
        return clan_warlog(self.tag)["items"]

    def to_dict(self, short=False) -> Dict:
        data = dict(self.to_mongo())
        data["computed"] = dict(data["computed"])
        data["day_delta"] = dict(data["day_delta"])
        data["week_delta"] = dict(data["week_delta"])
        del data["memberList"]
        del data["_id"]

        if short:
            keys = {"tag", "slug", "name", "description", "clanPoints", "clanVersusPoints", "members", "badgeUrls"}
            data = {k: data[k] for k in keys}

        return data

    def __repr__(self):
        return "<Clan {0}>".format(self.tag)

    def __str__(self):
        return "<Clan {0}>".format(self.tag)

    @classmethod
    def find_by_tag(cls, tag) -> Clan:
        clan = Clan.objects(tag=prepend_hash(tag)).first()

        if not clan:
            clan = Clan.fetch_and_update(tag, sync_calculation=True)

        return clan

    @classmethod
    def find_by_slug(cls, slug) -> Clan:
        return Clan.objects.get(slug=slug)

    @classmethod
    def active(cls, update_before=None):
        query = Q(active_members__gte=8)
        if update_before:
            query = Q(updated_on__lte=update_before) & query

        return Clan.objects(query).no_cache().only("tag")

    @classmethod
    def fetch_and_update(cls, tag, sync_calculation=True) -> Clan:
        tag = prepend_hash(tag)

        # Fetch from API
        clan_response = api.find_clan_by_tag(tag)
        tags = [member["tag"] for member in clan_response["memberList"]]
        players_response = api.fetch_all_players(tags)

        # Store all players data using historical compressed format
        save_historical_clan(clan_response, players_response)

        # Enqueue player json to queue
        clashleaders.queue.player.update_players(players_response)

        clan_response["clan_type"] = clan_response["type"]
        del clan_response["type"]
        clan_response["slug"] = slugify(f"{clan_response['name']}-{tag}", to_lower=True)
        clan_response["updated_on"] = datetime.now()

        clan = Clan.objects(tag=tag).upsert_one(**clan_response)

        if sync_calculation:
            clan.update_calculations()
        else:
            clan.job = clashleaders.queue.calculation.update_calculations.delay(tag)

        return clan


def prepend_hash(tag):
    return "#" + tag.lstrip("#").upper()


def save_historical_clan(clan_json, player_json):
    try:
        players = [clashleaders.model.HistoricalPlayer(**p).save() for p in player_json]
        clashleaders.model.HistoricalClan(**clan_json, players=players).save()
    except:
        logging.exception("Error while saving save_historical_clan")
