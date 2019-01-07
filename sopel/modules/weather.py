# coding=utf-8
# Copyright 2008, Sean B. Palmer, inamidst.com
# Copyright 2012, Elsie Powell, embolalia.com
# Copyright 2019, Nobel geht die Welt zugrunde
# Licensed under the Eiffel Forum License 2.
from __future__ import unicode_literals, absolute_import, print_function, division

from sopel.module import commands, example, NOLIMIT
from sopel.modules.units import c_to_f

import requests


def woeid_search(query):
    """
    Find the first Where On Earth ID for the given query. Result is the etree
    node for the result, so that location data can still be retrieved. Returns
    None if there is no result, or the woeid field is empty.
    """
    query = query.replace(" ", "+")
    body = requests.get('https://www.metaweather.com/api/location/search/?query=' + query)
    results = body.json()
    if results is None or results == []:
        return None
    return results[0]["woeid"]


def get_cover(parsed):
    try:
        condition = parsed["consolidated_weather"][0]["weather_state_name"]
    except KeyError:
        return 'unknown'
    text = condition
    # code = int(condition['code'])
    # TODO parse code to get those little icon thingies.
    return text


def get_temp(parsed):
    try:
        condition = parsed["consolidated_weather"][0]["the_temp"]
        temp = int(condition)
    except (KeyError, ValueError):
        return 'unknown'
    return (u'%d\u00B0C (%d\u00B0F)' % (temp, c_to_f(temp)))


def get_humidity(parsed):
    try:
        humidity = parsed["consolidated_weather"][0]["humidity"]
    except (KeyError, ValueError):
        return 'unknown'
    return "Humidity: %s%%" % humidity


def get_wind(parsed):
    try:
        wind_data = parsed["consolidated_weather"][0]["wind_speed"]
        wind_direction = parsed["consolidated_weather"][0]["wind_direction"]
        kph = float(wind_data)
        m_s = float(round(kph / 3.6, 1))
        speed = int(round(kph / 1.852, 0))
        degrees = int(wind_direction)
    except (KeyError, ValueError):
        return 'unknown'

    if speed < 1:
        description = 'Calm'
    elif speed < 4:
        description = 'Light air'
    elif speed < 7:
        description = 'Light breeze'
    elif speed < 11:
        description = 'Gentle breeze'
    elif speed < 16:
        description = 'Moderate breeze'
    elif speed < 22:
        description = 'Fresh breeze'
    elif speed < 28:
        description = 'Strong breeze'
    elif speed < 34:
        description = 'Near gale'
    elif speed < 41:
        description = 'Gale'
    elif speed < 48:
        description = 'Strong gale'
    elif speed < 56:
        description = 'Storm'
    elif speed < 64:
        description = 'Violent storm'
    else:
        description = 'Hurricane'

    if (degrees <= 22.5) or (degrees > 337.5):
        degrees = u'\u2193'
    elif (degrees > 22.5) and (degrees <= 67.5):
        degrees = u'\u2199'
    elif (degrees > 67.5) and (degrees <= 112.5):
        degrees = u'\u2190'
    elif (degrees > 112.5) and (degrees <= 157.5):
        degrees = u'\u2196'
    elif (degrees > 157.5) and (degrees <= 202.5):
        degrees = u'\u2191'
    elif (degrees > 202.5) and (degrees <= 247.5):
        degrees = u'\u2197'
    elif (degrees > 247.5) and (degrees <= 292.5):
        degrees = u'\u2192'
    elif (degrees > 292.5) and (degrees <= 337.5):
        degrees = u'\u2198'

    return description + ' ' + str(m_s) + 'm/s (' + degrees + ')'


def get_tomorrow_high(parsed):
    try:
        tomorrow_high = int(parsed["consolidated_weather"][1]["max_temp"])
    except (KeyError, ValueError):
        return 'unknown'
    return ('High: %d\u00B0C (%d\u00B0F)' % (tomorrow_high, c_to_f(tomorrow_high)))


def get_tomorrow_low(parsed):
    try:
        tomorrow_low = int(parsed["consolidated_weather"][1]["min_temp"])
    except (KeyError, ValueError):
        return 'unknown'
    return ('Low: %d\u00B0C (%d\u00B0F)' % (tomorrow_low, c_to_f(tomorrow_low)))


def get_tomorrow_cover(parsed):
    try:
        tomorrow_cover = parsed["consolidated_weather"][1]["weather_state_name"]
    except KeyError:
        return 'unknown'
    tomorrow_text = tomorrow_cover
    # code = int(condition['code'])
    # TODO parse code to get those little icon thingies.
    return ('Tomorrow: %s,' % (tomorrow_text))


def say_info(bot, trigger, mode):
    if mode not in ['weather', 'forecast']:  # Unnecessary safeguard, but whatever
        return bot.say("Sorry, I got confused. Please report this error to {owner}."
                       .format(owner=bot.config.core.owner))
    # most of the logic is common to both modes
    location = trigger.group(2)
    woeid = ''
    if not location:
        woeid = bot.db.get_nick_value(trigger.nick, 'woeid')
        if not woeid:
            return bot.reply("I don't know where you live. "
                             "Give me a location, like {pfx}{command} London, "
                             "or tell me where you live by saying {pfx}setlocation "
                             "London, for example.".format(command=trigger.group(1),
                                pfx=bot.config.core.help_prefix))
    else:
        location = location.strip()
        woeid = bot.db.get_nick_value(location, 'woeid')
        if woeid is None:
            first_result = woeid_search(location)
            if first_result is not None:
                woeid = first_result

    if not woeid:
        return bot.reply("I don't know where that is.")

    query = woeid
    body = requests.get('https://www.metaweather.com/api/location/' + str(query))
    results = body.json()
    if results is None:
        return bot.reply("No forecast available. Try a more specific location.")
    location = results["title"]

    # Mode-specific behavior, finally!
    if mode == 'weather':
        cover = get_cover(results)
        temp = get_temp(results)
        humidity = get_humidity(results)
        wind = get_wind(results)
        return bot.say(u'%s: %s, %s, %s, %s' % (location, cover, temp, humidity, wind))
    if mode == 'forecast':
        tomorrow_high = get_tomorrow_high(results)
        tomorrow_low = get_tomorrow_low(results)
        tomorrow_text = get_tomorrow_cover(results)
        return bot.say(u'%s: %s %s %s' % (location, tomorrow_text, tomorrow_high, tomorrow_low))

    return  # Another unnecessary safeguard, mostly to prevent linters complaining


@commands('weather', 'wea')
@example('.weather London')
def weather_command(bot, trigger):
    """.weather location - Show the weather at the given location."""
    say_info(bot, trigger, 'weather')


@commands('forecast')
@example('.forecast Montreal, QC')
def forecast_command(bot, trigger):
    """.forecast location - Show the weather forecast for tomorrow at the given location."""
    say_info(bot, trigger, 'forecast')


@commands('setlocation', 'setwoeid')
@example('.setlocation Columbus, OH')
def update_woeid(bot, trigger):
    """Set your default weather location."""
    if not trigger.group(2):
        bot.reply('Give me a location, like "Washington, DC" or "London".')
        return NOLIMIT

    first_result = woeid_search(trigger.group(2))
    if first_result is None:
        return bot.reply("I don't know where that is.")

    woeid = first_result.get('woeid')

    bot.db.set_nick_value(trigger.nick, 'woeid', woeid)

    neighborhood = first_result.get('locality2') or ''
    if neighborhood:
        neighborhood = neighborhood.get('#text') + ', '
    city = first_result.get('locality1') or ''
    # This is to catch cases like 'Bawlf, Alberta' where the location is
    # thought to be a "LocalAdmin" rather than a "Town"
    if city:
        city = city.get('#text')
    else:
        city = first_result.get('name')
    state = first_result.get('admin1').get('#text') or ''
    country = first_result.get('country').get('#text') or ''
    bot.reply('I now have you at WOEID %s (%s%s, %s, %s)' %
              (woeid, neighborhood, city, state, country))
