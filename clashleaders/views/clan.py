from flask import render_template
from mongoengine import DoesNotExist

from clashleaders import app, cache
from clashleaders.model import Clan, Status
from clashleaders.text.clan_description_processor import transform_description


@app.context_processor
def inject_most_popular():
    status = Status.get_instance()
    return dict(status=status,
                most_popular=status.popular_clans,
                popular_countries=status.top_countries,
                reddit_clans=status.reddit_clans
                )


@app.route("/clan/<slug>")
def clan_detail_page(slug):
    try:
        clan = Clan.find_by_slug(slug)
        description = transform_description(clan.description)
        start_count, similar_clans = clan.similar_clans()
        initial_state = dict(
            name=clan.name,
            tag=clan.tag,
            updatedOn=clan.updated_on.timestamp() * 1000,
            historicData=clan.historical_near_days_ago(7).to_matrix(),
            recentData=clan.historical_near_now().to_matrix(),
            playerStatus={},
            oldestDays=clan.days_of_history()
        )
    except DoesNotExist:
        return render_template('error.html'), 404
    else:
        return render_template('clan.html',
                               clan=clan,
                               trophy_distribution=clan_trophies(clan),
                               initial_state=initial_state,
                               description=description,
                               similar_clans=similar_clans,
                               similar_clans_start_count=start_count)


@cache.memoize(600)
def clan_trophies(clan):
    df = clan.to_historical_df()[['members', 'clanPoints']].resample('D').mean().dropna()
    df = df.reset_index().rename(columns={'created_on': 'labels'})
    df['labels'] = df['labels'].dt.strftime('%Y-%m-%dT%H:%M:%S+00:00Z')
    return df.to_dict('l')
