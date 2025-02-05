"""
xkcd.py - Sopel xkcd Plugin
Copyright 2010, Michael Yanovich (yanovich.net), and Morgan Goose
Copyright 2012, Lior Ramati
Copyright 2013, Elsie Powell (embolalia.com)
Licensed under the Eiffel Forum License 2.

https://sopel.chat
"""
from __future__ import annotations

from json import JSONDecodeError
import logging
import random
import re

import requests

from sopel import plugin


LOGGER = logging.getLogger(__name__)
PLUGIN_OUTPUT_PREFIX = '[xkcd] '

# used with permission of site owner
# https://twitter.com/Dmdboi/status/1589202274999767041
SEARCHXKCD_API = 'https://gq67pznq1k.execute-api.eu-west-1.amazonaws.com/search'


class SearchXkcdError(Exception):
    """Generic exception to raise if there was a problem contacting the API."""


class SearchFailedError(SearchXkcdError):
    """Couldn't reach the search endpoint."""


class ResponseFormatError(SearchXkcdError):
    """Response format couldn't be parsed."""


class NoResultsError(SearchXkcdError):
    """Response could be parsed, but it was empty."""


def get_info(number=None):
    if number:
        url = 'https://xkcd.com/{}/info.0.json'.format(number)
    else:
        url = 'https://xkcd.com/info.0.json'
    data = requests.get(url).json()
    data['url'] = 'https://xkcd.com/' + str(data['num'])
    return data


def searchxkcd_search(query):
    parameters = {
        'q': query,
        'page': 0,
    }
    try:
        response = requests.post(SEARCHXKCD_API, params=parameters)
    except requests.exceptions.ConnectionError as e:
        LOGGER.debug("Unable to reach searchxkcd API: %s", e)
        raise SearchFailedError(str(e))
    except Exception as e:
        LOGGER.debug("Unexpected error calling searchxkcd API: %s", e)
        raise SearchXkcdError(str(e))

    try:
        hits = response.json()['results']['hits']
        if not hits:
            raise NoResultsError
        first = hits[0]['objectID']
    except (JSONDecodeError, LookupError):
        msg = "Data format from searchxkcd API could not be understood."
        LOGGER.debug(msg)
        raise ResponseFormatError(msg)

    return first


@plugin.command('xkcd')
@plugin.example(".xkcd 1782", user_help=True)
@plugin.example(".xkcd", user_help=True)
@plugin.output_prefix(PLUGIN_OUTPUT_PREFIX)
def xkcd(bot, trigger):
    """Finds an xkcd comic strip.

    Takes one of 3 inputs:

      * If no input is provided it will return a random comic
      * If numeric input is provided it will return that comic, or the
        nth-latest comic if the number is negative
      * If non-numeric input is provided it will return the first search result
        for those keywords from searchxkcd.com

    """
    # get latest comic, for random selection and validating numeric input
    latest = get_info()
    max_int = latest['num']

    # if no input is given (pre - lior's edits code)
    if not trigger.group(2):  # get random comic
        random.seed()
        requested = get_info(random.randint(1, max_int + 1))
    else:
        query = trigger.group(2).strip()
        numbered = re.match(r"^(#|\+|-)?(\d+)$", query)

        if numbered:
            query = int(numbered.group(2))
            if numbered.group(1) == "-":
                query = -query
            return numbered_result(bot, query, latest)
        else:
            # Non-number: search the web.
            if (query.lower() == "latest" or query.lower() == "newest"):
                requested = latest
            else:
                try:
                    number = searchxkcd_search(query)
                except NoResultsError:
                    bot.reply("Sorry, I couldn't find any comics for that query.")
                    return
                except (ResponseFormatError, SearchFailedError, SearchXkcdError):
                    bot.reply(
                        "A technical problem prevented me from searching. "
                        "Please ask my owner to check my logs.")

                requested = get_info(number)

    say_result(bot, requested)


def numbered_result(bot, query, latest, commanded=True):
    max_int = latest['num']
    if query > max_int:
        bot.reply(("Sorry, comic #{} hasn't been posted yet. "
                   "The last comic was #{}").format(query, max_int))
        return
    elif query <= -max_int:
        bot.reply(("Sorry, but there were only {} comics "
                   "released yet so far").format(max_int))
        return
    elif abs(query) == 0:
        requested = latest
    elif query == 404 or max_int + query == 404:
        bot.say("404 - Not Found")  # don't error on that one
        return
    elif query > 0:
        requested = get_info(query)
    else:
        # Negative: go back that many from current
        requested = get_info(max_int + query)

    say_result(bot, requested, commanded)


def say_result(bot, result, commanded=True):
    parts = [
        result['title'],
        'Alt-text: ' + result['alt'],
    ]

    if commanded:
        parts.append(result['url'])

    bot.say(' | '.join(parts))


@plugin.url(r'xkcd.com/(\d+)')
@plugin.output_prefix(PLUGIN_OUTPUT_PREFIX)
def get_url(bot, trigger, match):
    latest = get_info()
    numbered_result(bot, int(match.group(1)), latest, commanded=False)


@plugin.url(r'https?://xkcd\.com/?$')
@plugin.output_prefix(PLUGIN_OUTPUT_PREFIX)
def xkcd_main_page(bot, trigger, match):
    latest = get_info()
    numbered_result(bot, 0, latest, commanded=False)
