from flask import render_template, send_file, request, jsonify
from mongoengine import DoesNotExist

from clashstats import app, cache
from clashstats.clash import excel, api
from clashstats.clash.calculation import update_calculations
from clashstats.clash.transformer import transform_players, to_short_clan
from clashstats.model import Clan, ClanPreCalculated


@app.route("/search.json")
def search():
    query = request.args.get('q')
    clans = ClanPreCalculated.objects.search_text(f"\"{query}\"") or ClanPreCalculated.objects.search_text(query)

    if not clans:
        try:
            clans = [Clan(**api.find_clan_by_tag(query))]
        except api.ClanNotFound:
            clans = [Clan(**c) for c in api.search_by_name(query)['items']]

    return jsonify([to_short_clan(c)._asdict() for c in clans])


@app.route("/clan/<tag>.json")
def clan_detail_json(tag):
    try:
        api.find_clan_by_tag(tag)
    except api.ClanNotFound:
        return render_template('error.html'), 404
    else:
        days_ago = request.args.get('daysAgo')
        clan = clan_from_days_ago(days_ago, tag)
        return jsonify(transform_players(clan.players))


@app.route("/clan/<tag>.xlsx")
def clan_detail_xlsx(tag):
    try:
        api.find_clan_by_tag(tag)
    except api.ClanNotFound:
        return render_template('error.html'), 404
    else:
        days_ago = request.args.get('daysAgo')
        clan = clan_from_days_ago(days_ago, tag)
        return send_file(excel.to_stream(clan), attachment_filename=f"{clan.tag}.xlsx", as_attachment=True)


@app.route("/clan/<slug>")
def clan_detail_page(slug):
    try:
        clan = ClanPreCalculated.find_by_slug(slug)
    except DoesNotExist:
        return render_template('error.html'), 404
    else:
        return render_template('clan.html', clan=clan)


@app.route("/clan/<tag>/short.json")
@cache.cached(timeout=1000)
def clan_meta(tag):
    try:
        clan = ClanPreCalculated.find_by_tag(tag)
    except DoesNotExist:
        clan = update_calculations(Clan.fetch_and_save(tag))

    data = {
        'tag': clan.tag,
        'slug': clan.slug,
        'name': clan.name,
        'description': clan.description,
        'clanPoints': clan.clanPoints,
        'clanVersusPoints': clan.clanVersusPoints,
        'members': clan.members,
        'badgeUrls': clan.badgeUrls,
    }

    return jsonify(data)


def clan_from_days_ago(days_ago, tag):
    if days_ago:
        return Clan.from_now_with_tag(tag, days=int(days_ago)).first() or Clan.fetch_and_save(tag)
    else:
        return Clan.fetch_and_save(tag)
