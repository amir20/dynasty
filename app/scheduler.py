import logging
import time

import os
import schedule
from mongoengine import connect
from raven import Client
from datetime import datetime, timedelta
from clash.calculation import update_calculations
from model import *

client = Client(os.getenv('SENTRY_DSN'))

logging.basicConfig(level=logging.INFO)

connect(db='clashstats', host=os.getenv('DB_HOST'), connect=False)

logger = logging.getLogger(__name__)
logging.getLogger("clash.api").setLevel(logging.WARNING)

all_tags = set(Clan.objects.distinct('tag'))


def update_clans():
    already_done = set(Clan.from_now(hours=12).distinct('tag'))
    all_tags.update(already_done)
    tags_to_fetch = list(all_tags - already_done)

    total = len(tags_to_fetch)
    tags_to_fetch = tags_to_fetch[:50]

    logger.info(f"Fetching {len(tags_to_fetch)} of total {total} eligible items.")

    for tag in tags_to_fetch:
        try:
            logger.info(f"Updating clan {tag}.")
            clan = Clan.fetch_and_save(tag)
            update_calculations(clan)
        except Exception:
            logger.exception(f"Error while fetching clan {tag}.")
            client.captureException()

    logger.debug(f"Done fetching clans.")

    ratio_indexed = 100 * (len(Clan.from_now(hours=12).distinct('tag')) / len(all_tags))
    total_clans = len(all_tags)
    Status.objects.update_one(
        set__ratio_indexed=ratio_indexed,
        set__total_clans=total_clans,
        set__last_updated=datetime.now,
        upsert=True
    )


def update_clan_calculations():
    hour_ago = datetime.now() - timedelta(hours=1)
    recent_tags = set(Clan.from_now(hours=1).distinct('tag'))
    calculated_tags = set(ClanPreCalculated.objects(last_updated__gte=hour_ago).distinct('tag'))
    available_clan_tags = recent_tags - calculated_tags

    logger.info(f"Updating {len(available_clan_tags)} clan calculations.")
    for tag in available_clan_tags:
        try:
            logger.info(f"Updating calculations for {tag}.")
            clan = Clan.objects(tag=tag).first()
            update_calculations(clan)
        except Exception:
            logger.exception(f"Error during updating clan calculation for {tag}.")
            client.captureException()


def delete_old_clans():
    deleted = Clan.older_than(days=45).delete()
    logger.info(f"Deleted {deleted} clans that are older than 45 days.")


schedule.every().minutes.do(update_clans)
schedule.every().minutes.do(update_clan_calculations)
schedule.every().day.at("12:01").do(delete_old_clans)

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(1)
