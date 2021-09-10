from clashleaders.queue.war import update_wars
from clashleaders.clash.transformer import tag_to_slug
import logging

from datetime import datetime, timedelta
from time import sleep

import graphene
from graphene.types.generic import GenericScalar
from rq.exceptions import NoSuchJobError

import pandas as pd
from io import BytesIO
import base64
import clashleaders.model as model
from clashleaders.clash import api
from clashleaders.views import imgproxy_url

logger = logging.getLogger(__name__)


class PlayerActivity(graphene.ObjectType):
    labels = graphene.List(graphene.String)
    attack_wins = graphene.List(graphene.Float)
    donations = graphene.List(graphene.Float)
    gold_grab = graphene.List(graphene.Float)
    elixir_grab = graphene.List(graphene.Float)
    de_grab = graphene.List(graphene.Float)
    trophies = graphene.List(graphene.Float)


class BadgeUrls(graphene.ObjectType):
    large = graphene.String()
    medium = graphene.String()
    small = graphene.String()
    tiny = graphene.String()

    def resolve_large(self, info):
        return imgproxy_url(self.large)

    def resolve_medium(self, info):
        return imgproxy_url(self.medium)

    def resolve_small(self, info):
        return imgproxy_url(self.small)

    def resolve_tiny(self, info):
        return imgproxy_url(self.tiny)


class PlayerLeague(graphene.ObjectType):
    name = graphene.String()
    id = graphene.Int()
    iconUrls = graphene.Field(BadgeUrls)

    def resolve_iconUrls(self, info):
        return BadgeUrls(**self.iconUrls)


class ShortClan(graphene.ObjectType):
    name = graphene.String()
    tag = graphene.String()
    slug = graphene.String()
    members = graphene.Int()
    badge_urls = graphene.Field(BadgeUrls)

    def resolve_badge_urls(parent, info):
        if hasattr(parent, "badgeUrls"):
            return BadgeUrls(**parent.badgeUrls)
        else:
            return BadgeUrls(**parent["badgeUrls"])


class PlayerWarStats(graphene.ObjectType):
    avg_stars = graphene.Float()
    avg_destruction = graphene.Float()


class Player(graphene.ObjectType):
    name = graphene.String()
    tag = graphene.String()
    slug = graphene.String()
    role = graphene.String()
    townHallLevel = graphene.Int()
    trophies = graphene.Int()
    builderHallLevel = graphene.Int()
    expLevel = graphene.Int()
    defenseWins = graphene.Int()
    attackWins = graphene.Int()
    donations = graphene.Int()
    percentile = graphene.Int()
    activity = graphene.Field(PlayerActivity)
    league = graphene.Field(PlayerLeague)
    clan = graphene.Field(ShortClan)
    war_stats = graphene.Field(PlayerWarStats)

    def resolve_percentile(self, info):
        return self.player_score()

    def resolve_activity(self, info):
        df = self.to_historical_df()[["attack_wins", "donations", "gold_grab", "elixir_escapade", "heroic_heist", "trophies"]]
        resampled = df.resample("D").mean().dropna()
        diffed = resampled.diff().dropna().clip(lower=0)

        if diffed.empty:
            return PlayerActivity(labels=[], attack_wins=[], donations=[], gold_grab=[], elixir_grab=[], de_grab=[], trophies=[])

        diffed.rename(columns={"elixir_escapade": "elixir_grab", "heroic_heist": "de_grab"}, inplace=True)
        diffed["trophies"] = resampled["trophies"]  # Undo trophies

        return PlayerActivity(
            labels=diffed.index.strftime("%Y-%m-%d %H:%M:%S").tolist(),
            attack_wins=diffed["attack_wins"].tolist(),
            donations=diffed["donations"].tolist(),
            gold_grab=diffed["gold_grab"].tolist(),
            elixir_grab=diffed["elixir_grab"].tolist(),
            de_grab=diffed["de_grab"].tolist(),
            trophies=diffed["trophies"].tolist(),
        )

    def resolve_league(self, info):
        return PlayerLeague(**self.league) if hasattr(self, "league") else None

    def resolve_clan(self, info):
        return self.most_recent_clan()

    def resolve_war_stats(self, info):
        return PlayerWarStats(**self.war_stats())


class ClanDelta(graphene.ObjectType):
    avg_attack_wins = graphene.Float()
    avg_de_grab = graphene.Float()
    avg_donations = graphene.Float()
    avg_donations_received = graphene.Float()
    avg_elixir_grab = graphene.Float()
    avg_gold_grab = graphene.Float()
    avg_versus_wins = graphene.Float()
    avg_war_stars = graphene.Float()
    avg_games_xp = graphene.Float()
    avg_cwl_stars = graphene.Float()

    avg_donations_percentile = graphene.Float()
    avg_war_stars_percentile = graphene.Float()
    avg_attack_wins_percentile = graphene.Float()
    avg_versus_wins_percentile = graphene.Float()
    avg_games_xp_percentile = graphene.Float()
    avg_cwl_stars_percentile = graphene.Float()

    total_attack_wins = graphene.Int()
    total_bh_trophies = graphene.Int()
    total_de_grab = graphene.Int()
    total_donations = graphene.Float()
    total_elixir_grab = graphene.Float()
    total_gold_grab = graphene.Float()
    total_trophies = graphene.Float()
    total_versus_wins = graphene.Float()
    total_games_xp = graphene.Float()
    total_cwl_stars = graphene.Float()


class SimilarClanDelta(graphene.ObjectType):
    avg_de_grab = graphene.Float()
    avg_elixir_grab = graphene.Float()
    avg_gold_grab = graphene.Float()


class ClanActivity(graphene.ObjectType):
    labels = graphene.List(graphene.String)
    trophies = graphene.List(graphene.Float)
    members = graphene.List(graphene.Float)


class IdNamePair(graphene.ObjectType):
    id = graphene.Int()
    name = graphene.String()


class ClanLabel(graphene.ObjectType):
    id = graphene.Int()
    name = graphene.String()
    iconUrls = graphene.Field(BadgeUrls)

    def resolve_iconUrls(self, info):
        return BadgeUrls(**self.iconUrls)


class War(graphene.ObjectType):
    endTime = graphene.Float()
    startTime = graphene.Float()
    aggregated = GenericScalar()
    state = graphene.String()
    opponent = graphene.Field(ShortClan)

    def resolve_startTime(parent, info):
        return parent.startTime.timestamp() * 1000

    def resolve_endTime(parent, info):
        return parent.endTime.timestamp() * 1000

    def resolve_opponent(parent, info):
        slug = tag_to_slug(parent.opponent["tag"])
        return dict(name=parent.opponent["name"], tag=parent.opponent["tag"], badgeUrls=parent.opponent["badgeUrls"], slug=slug)

    def resolve_aggregated(parent, info):
        df = parent.to_df()
        df = df.drop(
            columns=[
                "attack1.attackerTag",
                "attack1.defenderTag",
                "attack2.attackerTag",
                "attack2.defenderTag",
                "bestOpponentAttack.attackerTag",
                "bestOpponentAttack.defenderTag",
            ],
            errors="ignore",
        )
        df.columns = df.columns.str.replace(".", "__", regex=False)
        return df.fillna("na").reset_index().to_dict(orient="records")


class CWLGroup(graphene.ObjectType):
    state = graphene.String()
    season = graphene.String()
    clans = GenericScalar()
    aggregated = GenericScalar()

    def resolve_aggregated(self, info):
        try:
            df = self.aggregate_stars_and_destruction(self.clan)
            return df.fillna("na").reset_index().to_dict(orient="records")
        except:
            logger.error("Failed to aggregate clan data for {}".format(self.clan), exc_info=True)
            return None


class ClanMembers(graphene.ObjectType):
    header = GenericScalar()
    most_recent = GenericScalar()
    delta = GenericScalar()

    def resolve_header(parent, info):
        return parent.header()

    def resolve_most_recent(parent, info):
        return parent.most_recent().to_dict(orient="records")

    def resolve_delta(parent, info):
        return parent.delta().to_dict(orient="index")


class Clan(graphene.ObjectType):
    name = graphene.String()
    slug = graphene.String()
    tag = graphene.String()
    description = graphene.String()
    badge_urls = graphene.Field(BadgeUrls)
    clanPoints = graphene.Int()
    clanLevel = graphene.Int()
    clanVersusPoints = graphene.Int()
    members = graphene.Int()
    updated_on = graphene.Float()
    labels = graphene.List(ClanLabel)

    computed = graphene.Field(ClanDelta)
    day_delta = graphene.Field(ClanDelta)
    week_delta = graphene.Field(ClanDelta)
    month_delta = graphene.Field(ClanDelta)
    delta = graphene.Field(ClanDelta, days=graphene.Int(required=True))

    player_matrix = GenericScalar(days=graphene.Int(required=False))
    players = graphene.List(Player)
    activity = graphene.Field(ClanActivity)
    similar = graphene.Field(SimilarClanDelta, days=graphene.Int(required=True))
    player_status = GenericScalar()
    xlsx_export = graphene.String(days=graphene.Int(required=True))
    trophy_history = GenericScalar()

    warLeague = graphene.Field(IdNamePair)
    isWarLogPublic = graphene.Boolean()
    requiredTrophies = graphene.Int()
    warFrequency = graphene.String()
    warLosses = graphene.Int()
    warTies = graphene.Int()
    warWinStreak = graphene.Int()
    warWins = graphene.Int()
    war_win_ratio = graphene.Float()
    war_total = graphene.Int()

    comparable_members = graphene.Field(ClanMembers, delta_days=graphene.Int(required=True))

    recent_cwl_group = graphene.Field(CWLGroup, update_wars=graphene.Boolean(required=False))
    wars = graphene.List(War)

    def resolve_delta(self, info, days):
        previous_clan = self.historical_near_days_ago(days)
        return self.historical_near_now().clan_delta(previous_clan)

    def resolve_badge_urls(self, info):
        return BadgeUrls(**self.badgeUrls)

    def resolve_labels(self, info):
        return [ClanLabel(**l) for l in self.labels]

    def resolve_updated_on(self, info):
        return self.updated_on.timestamp() * 1000

    def resolve_player_matrix(self, info, days=0):
        return self.historical_near_days_ago(days).to_matrix()

    def resolve_recent_cwl_group(self, info, update_wars=False):
        wars = self.cwl_wars()
        if wars:
            cwl_war = wars[0]
            cwl_war.clan = self
            return cwl_war
        else:
            return None

    def resolve_wars(self, info):
        return self.wars()

    def resolve_comparable_members(self, info, delta_days):
        return self.comparable_members(delta_days)

    def resolve_players(self, info):
        df = self.historical_near_now().to_df(formatted=False).reset_index()
        df = df[["name", "tag", "town_hall_level", "exp_level", "trophies", "builder_hall_level", "defense_wins", "attack_wins", "donations"]].rename(
            columns={
                "town_hall_level": "townHallLevel",
                "exp_level": "expLevel",
                "builder_hall_level": "builderHallLevel",
                "defense_wins": "defenseWins",
                "attack_wins": "attackWins",
            }
        )
        return [Player(**p) for p in df.to_dict("index").values()]

    def resolve_similar(self, info, days):
        key = {1: "day_delta", 7: "week_delta"}[days]
        cluster_label = self.cluster_label
        gold = model.Clan.objects(cluster_label=cluster_label).average(f"{key}.avg_gold_grab")
        elixir = model.Clan.objects(cluster_label=cluster_label).average(f"{key}.avg_elixir_grab")
        de = model.Clan.objects(cluster_label=cluster_label).average(f"{key}.avg_de_grab")
        return SimilarClanDelta(avg_de_grab=de, avg_gold_grab=elixir, avg_elixir_grab=gold)

    def resolve_activity(self, info):
        df = self.to_historical_df()[["members", "clanPoints"]].resample("D").mean().dropna()
        df.index.name = "labels"
        df = df.reset_index().rename(columns={"clanPoints": "trophies"})
        df["labels"] = df["labels"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00Z")
        return ClanActivity(**df.to_dict("list"))

    def resolve_player_status(self, info):
        return self.player_activity()

    def resolve_xlsx_export(self, info, days):
        historical = self.historical_near_days_ago(days)

        stream = BytesIO()
        writer = pd.ExcelWriter(stream, engine="xlsxwriter", options={"strings_to_urls": False, "strings_to_formulas": False})
        historical.to_df(formatted=True).to_excel(writer, sheet_name=self.tag)
        writer.close()
        return "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + base64.b64encode(stream.getvalue()).decode()

    def resolve_trophy_history(self, info):
        return self.trophy_history()

    def resolve_warLeague(self, info):
        return IdNamePair(**self.warLeague)


class Query(graphene.ObjectType):
    player = graphene.Field(Player, tag=graphene.String(required=True))
    clan = graphene.Field(Clan, tag=graphene.String(required=True), refresh=graphene.Int(required=False), update_wars=graphene.Boolean(required=False))
    search_clan = graphene.List(ShortClan, query=graphene.String(required=True))

    def resolve_clan(self, info, tag, refresh=False, update_wars=False):
        if refresh:
            clan = model.Clan.find_by_tag(tag)
            clan.update(inc__page_views=1)
            delta = datetime.now() - clan.updated_on
            if timedelta(minutes=refresh) < delta:
                model.Clan.fetch_and_update(tag)

        clan = model.Clan.find_by_tag(tag)
        if update_wars:
            clan.update_wars()

        return clan

    def resolve_player(self, info, tag):
        return model.Player.find_by_tag(tag)

    def resolve_search_clan(self, info, query):
        try:
            clan = api.find_clan_by_tag(query)
            results = [model.Clan(**clan)]
        except api.ClanNotFound:
            results = [model.Clan(**c) for c in api.search_by_name(query, limit=6)]

        results = sorted(results, key=lambda c: c.members, reverse=True)

        tags = [c.tag for c in results]
        existing_clans = list(model.Clan.objects(tag__in=tags))
        slugs = {c.tag: c.slug for c in existing_clans}

        for c in results:
            c.slug = slugs.get(c.tag)

        return results
