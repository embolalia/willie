# -*- coding: utf8 -*-
"""
spellcheck.py - Willie spell check Module
Copyright © 2012, Elad Alfassa, <elad@fedoraproject.org>
Copyright © 2012-2013, Lior Ramati
Licensed under the Eiffel Forum License 2.

http://willie.dftba.net

This module relies on pyenchant, on Fedora and Red Hat based system, it can be found in the package python-enchant
"""
import enchant
from willie.module import commands, example


@commands('spellcheck', 'spell')
@example('.spellcheck stuff')
def spellcheck(bot, trigger):
    """
    Says whether the given word is spelled correctly, and gives suggestions if
    it's not.
    """
    if not trigger.group(2):
        return
    word = trigger.group(2).rstrip()
    if " " in word:
        bot.say("One word at a time, please")
        return
    dictionary = enchant.Dict("en_US")
    dictionary_uk = enchant.Dict("en_GB")
    # I don't want to make anyone angry, so I check both American and British English.
    if dictionary_uk.check(word):
        if dictionary.check(word):
            bot.say(word + " is spelled correctly")
        else:
            bot.say(word + " is spelled correctly (British)")
    elif dictionary.check(word):
        bot.say(word + " is spelled correctly (American)")
    else:
        msg = word + " is not spelled correctly. Maybe you want one of these spellings:"
        sugWords = {}
        for suggested_word in dictionary.suggest(word):
            sugWords[suggested_word] = 'US'
        for suggested_word in dictionary_uk.suggest(word):
            sugWords.setdefault(suggested_word, '') += 'GB'
        for suggested_word, dicts in sugWords.iteritems():  # removes duplicates
            msg = msg + " '" + suggested_word + ("' (%s)," % dicts if len(dicts) is 2 else "',") # if/else indicates which dictionary if the spelling is only valid in one
        bot.say(msg[:-1]) # remove trailing ','
