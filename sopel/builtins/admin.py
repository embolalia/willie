"""
admin.py - Sopel Admin Plugin
Copyright 2010-2011, Sean B. Palmer (inamidst.com) and Michael Yanovich
(yanovich.net)
Copyright © 2012, Elad Alfassa, <elad@fedoraproject.org>
Copyright 2013, Ari Koivula <ari@koivu.la>
Copyright 2019, Florian Strzelecki, https://github.com/Exirel
Licensed under the Eiffel Forum License 2.

https://sopel.chat
"""
from __future__ import annotations

import logging

from sopel import plugin
from sopel.config import types

LOGGER = logging.getLogger(__name__)

ERROR_JOIN_NO_CHANNEL = 'Which channel should I join?'
"""Error message when channel is missing from command arguments."""
ERROR_PART_NO_CHANNEL = 'Which channel should I quit?'
"""Error message when channel is missing from command arguments."""
ERROR_NOTHING_TO_SAY = 'I need a channel and a message to talk.'
"""Error message when channel and/or message are missing."""
ERROR_NOTHING_TO_RAW = 'I need an IRC message to send.'
"""Error message when no raw IRC message was given."""


class AdminSection(types.StaticSection):
    hold_ground = types.BooleanAttribute('hold_ground', default=False)
    """Auto re-join on kick"""
    auto_accept_invite = types.BooleanAttribute('auto_accept_invite', default=True)
    """Auto-join channels when invited"""


def configure(config):
    """
    | name | example | purpose |
    | ---- | ------- | ------- |
    | hold\\_ground | False | Auto-rejoin the channel after being kicked. |
    | auto\\_accept\\_invite | True | Auto-join channels when invited. |
    """
    config.define_section('admin', AdminSection)
    config.admin.configure_setting('hold_ground',
                                   "Automatically re-join after being kicked?")
    config.admin.configure_setting('auto_accept_invite',
                                   'Automatically join channels when invited?')


def setup(bot):
    bot.config.define_section('admin', AdminSection)


class InvalidSection(Exception):
    def __init__(self, section):
        super().__init__(self, 'Section [{}] does not exist.'.format(section))
        self.section = section


class InvalidSectionOption(Exception):
    def __init__(self, section, option):
        super().__init__(self, 'Section [{}] does not have option \'{}\'.'.format(section, option))
        self.section = section
        self.option = option


def _get_config_channels(channels):
    """List"""
    for channel_info in channels:
        if ' ' in channel_info:
            yield channel_info.split(' ', 1)
        else:
            yield (channel_info, None)


def _set_config_channels(bot, channels):
    bot.config.core.channels = [
        ' '.join([part for part in items if part])
        for items in channels.items()
    ]
    bot.config.save()


def _join(bot, channel, key=None, save=True):
    if not channel:
        return

    if not key:
        bot.join(channel)
    else:
        bot.join(channel, key)

    if save:
        channels = dict(_get_config_channels(bot.config.core.channels))
        # save only if channel is new or key has been changed
        if channel not in channels or channels[channel] != key:
            channels[channel] = key
            _set_config_channels(bot, channels)
            LOGGER.info('Added "%s" to core.channels.', channel)


def _part(bot, channel, msg=None, save=True):
    bot.part(channel, msg or None)

    if save:
        channels = dict(_get_config_channels(bot.config.core.channels))
        if channel in channels:
            del channels[channel]
            _set_config_channels(bot, channels)
            LOGGER.info('Removed "%s" from core.channels.', channel)


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('join')
@plugin.priority('low')
@plugin.example('.join #example key', user_help=True)
@plugin.example('.join #example', user_help=True)
def join(bot, trigger):
    """Join the specified channel. This is an admin-only command."""
    channel, key = trigger.group(3), trigger.group(4)
    if not channel:
        bot.reply(ERROR_JOIN_NO_CHANNEL)
        return

    _join(bot, channel, key)


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('tmpjoin')
@plugin.priority('low')
@plugin.example('.tmpjoin #example key', user_help=True)
@plugin.example('.tmpjoin #example', user_help=True)
def temporary_join(bot, trigger):
    """Like ``join``, without saving. This is an admin-only command.

    Unlike the ``join`` command, ``tmpjoin`` won't remember the channel upon
    restarting the bot.
    """
    channel, key = trigger.group(3), trigger.group(4)
    if not channel:
        bot.reply(ERROR_JOIN_NO_CHANNEL)
        return

    _join(bot, channel, key, save=False)


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('part')
@plugin.priority('low')
@plugin.example('.part #example')
def part(bot, trigger):
    """Part the specified channel. This is an admin-only command."""
    channel, _sep, part_msg = trigger.group(2).partition(' ')
    if not channel:
        bot.reply(ERROR_PART_NO_CHANNEL)
        return

    _part(bot, channel, part_msg)


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('tmppart')
@plugin.priority('low')
@plugin.example('.tmppart #example')
def temporary_part(bot, trigger):
    """Like ``part``, without saving. This is an admin-only command.

    Unlike the ``part`` command, ``tmppart`` will rejoin the channel upon
    restarting the bot.
    """
    channel, _sep, part_msg = trigger.group(2).partition(' ')
    if not channel:
        bot.reply(ERROR_PART_NO_CHANNEL)
        return

    _part(bot, channel, part_msg, save=False)


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('chanlist', 'channels')
@plugin.priority('low')
def channel_list(bot, trigger):
    """Show channels Sopel is in."""
    channels = ', '.join(sorted(bot.channels.keys()))

    # conservative assumption about how much room we have in the line to make
    # sure `max_messages` won't actually truncate anything
    bot.say(channels, max_messages=1 + len(channels) // 400)


@plugin.require_privmsg
@plugin.require_owner
@plugin.command('restart')
@plugin.priority('low')
def restart(bot, trigger):
    """Restart the bot. This is an owner-only command."""
    quit_message = trigger.group(2)
    default_message = 'Restarting on command from %s.' % trigger.nick
    if not quit_message:
        quit_message = default_message

    LOGGER.info(default_message)
    bot.restart(quit_message)


@plugin.require_privmsg
@plugin.require_owner
@plugin.command('quit')
@plugin.priority('low')
def quit(bot, trigger):
    """Quit from the server. This is an owner-only command."""
    quit_message = trigger.group(2)
    default_message = 'Quitting on command from %s.' % trigger.nick
    if not quit_message:
        quit_message = default_message

    LOGGER.info(default_message)
    bot.quit(quit_message)


@plugin.require_privmsg
@plugin.require_owner
@plugin.command('raw')
@plugin.priority('low')
@plugin.example('.raw PRIVMSG NickServ :CERT ADD')
def raw(bot, trigger):
    """
    Send a raw IRC message. Can only be done in privmsg by the bot owner.
    This is mostly useful for debugging.
    """
    if trigger.group(2) is None:
        bot.reply(ERROR_NOTHING_TO_RAW)
        return

    bot.write([trigger.group(2)])


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('say', 'msg')
@plugin.priority('low')
@plugin.example('.say #YourPants Does anyone else smell neurotoxin?')
def say(bot, trigger):
    """
    Send a message to a given channel or nick. Can only be done in privmsg by
    an admin.
    """
    if trigger.group(2) is None:
        bot.reply(ERROR_NOTHING_TO_SAY)
        return

    channel, _sep, message = trigger.group(2).partition(' ')
    message = message.strip()
    if not channel or not message:
        bot.reply(ERROR_NOTHING_TO_SAY)
        return

    bot.say(message, channel)


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('me')
@plugin.priority('low')
def me(bot, trigger):
    """
    Send an ACTION (/me) to a given channel or nick. Can only be done in
    privmsg by an admin.
    """
    if trigger.group(2) is None:
        bot.reply(ERROR_NOTHING_TO_SAY)
        return

    channel, _sep, action = trigger.group(2).partition(' ')
    action = action.strip()
    if not channel or not action:
        bot.reply(ERROR_NOTHING_TO_SAY)
        return

    bot.action(action, channel)


@plugin.event('INVITE')
@plugin.priority('low')
def invite_join(bot, trigger):
    """Join a channel Sopel is invited to, if the inviter is an admin."""
    nick = trigger.args[0]
    channel = trigger.args[1]

    if nick != bot.nick:
        # this handler only cares if the invitee was the bot
        return

    if trigger.admin:
        LOGGER.info(
            'Got invited to "%s" by an admin.', channel)
        bot.join(channel)
    elif bot.config.admin.auto_accept_invite:
        LOGGER.info(
            'Got invited to "%s"; admin.auto_accept_invite is on', channel)
        bot.join(channel)
    else:
        LOGGER.info(
            'Got invited to "%s"; admin.auto_accept_invite is off.', channel)


@plugin.event('KICK')
@plugin.priority('low')
def hold_ground(bot, trigger):
    """
    This function monitors all kicks across all channels Sopel is in. If it
    detects that it is the one kicked it'll automatically join that channel.

    WARNING: This may not be needed and could cause problems if Sopel becomes
    annoying. Please use this with caution.
    """
    if bot.nick != trigger.args[1]:
        # not the bot; ignore
        return

    channel = trigger.sender
    if bot.config.admin.hold_ground:
        LOGGER.info('Got kicked from "%s"; admin.hold_ground is on.', channel)
        bot.join(channel)
    else:
        LOGGER.info('Got kicked from "%s"; admin.hold_ground is off.', channel)


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('mode')
@plugin.priority('low')
def mode(bot, trigger):
    """Set a user mode on Sopel. Can only be done in privmsg by an admin."""
    mode = trigger.group(3)
    if not mode:
        bot.reply('What mode should I set?')

    bot.write(('MODE', bot.nick, mode))


def parse_section_option_value(config, trigger):
    """Parse trigger for set/unset to get relevant config elements.

    :param config: Sopel's config
    :param trigger: IRC line trigger
    :return: A tuple with ``(section, section_name, static_sec, option, value)``
    :raises InvalidSection: section does not exist
    :raises InvalidSectionOption: option does not exist for section

    The ``value`` is optional and can be returned as ``None`` if omitted from command.
    """
    match = trigger.group(3)
    if match is None:
        raise ValueError  # Invalid command

    # Get section and option from first argument.
    arg1 = match.split('.')
    if len(arg1) == 1:
        section_name, option = "core", arg1[0]
    elif len(arg1) == 2:
        section_name, option = arg1
    else:
        raise ValueError  # invalid command format

    section = getattr(config, section_name, False)
    if not section:
        raise InvalidSection(section_name)
    static_sec = isinstance(section, types.StaticSection)

    if static_sec and not hasattr(section, option):
        raise InvalidSectionOption(section_name, option)  # Option not found in section

    if not static_sec and not config.parser.has_option(section_name, option):
        raise InvalidSectionOption(section_name, option)  # Option not found in section

    delim = trigger.group(2).find(' ')
    # Skip preceding whitespaces, if any.
    while delim > 0 and delim < len(trigger.group(2)) and trigger.group(2)[delim] == ' ':
        delim = delim + 1

    value = trigger.group(2)[delim:]
    if delim == -1 or delim == len(trigger.group(2)):
        value = None

    return (section, section_name, static_sec, option, value)


@plugin.require_privmsg("This command only works as a private message.")
@plugin.require_admin("This command requires admin privileges.")
@plugin.command('set')
@plugin.example('.set core.owner MyNick')
def set_config(bot, trigger):
    """See and modify values of Sopel's config object.

    Trigger args:
        arg1 - section and option, in the form "section.option"
        arg2 - value

    If there is no section, section will default to "core".
    If value is not provided, the current value will be displayed.
    """
    try:
        section, section_name, static_sec, option, value = parse_section_option_value(bot.config, trigger)
    except ValueError:
        bot.say('Usage: {}set section.option [value]'.format(bot.config.core.help_prefix))
        return
    except (InvalidSection, InvalidSectionOption) as exc:
        bot.say(exc.args[1])
        return

    # Get a descriptor class for the option if it's a static section
    descriptor = getattr(section.__class__, option) if static_sec else None

    # Display current value if no value is given
    if not value:
        value = getattr(section, option)

        if descriptor is not None:
            if getattr(descriptor, 'is_secret', False):
                # Keep secret option as secret
                value = "(secret value censored)"
        elif option.endswith("password") or option.endswith("pass"):
            # Fallback to guessing if secret, for backward compatiblity
            # TODO: consider a deprecation warning when loading settings
            value = "(password censored)"

        bot.say("%s.%s = %s (%s)" % (section_name, option, value, type(value).__name__))
        return

    # Owner-related settings cannot be modified interactively. Any changes to these
    # settings must be made directly in the config file.
    if section_name == 'core' and option in ['owner', 'owner_account']:
        bot.say("Changing '{}.{}' requires manually editing the configuration file."
                .format(section_name, option))
        return

    # Otherwise, set the value to one given
    if descriptor is not None:
        try:
            value = descriptor._parse(value, bot.config, section)
        except ValueError as exc:
            bot.say("Can't set attribute: " + str(exc))
            return
    setattr(section, option, value)
    LOGGER.info('%s.%s set successfully.', section_name, option)
    bot.say("OK. Set '{}.{}' successfully.".format(section_name, option))


@plugin.require_privmsg("This command only works as a private message.")
@plugin.require_admin("This command requires admin privileges.")
@plugin.command('unset')
@plugin.example('.unset core.owner')
def unset_config(bot, trigger):
    """Unset value of Sopel's config object.

    Unsetting a value will reset it to the default specified in the config
    definition.

    Trigger args:
        arg1 - section and option, in the form "section.option"

    If there is no section, section will default to "core".
    """
    try:
        section, section_name, static_sec, option, value = parse_section_option_value(bot.config, trigger)
    except ValueError:
        bot.say('Usage: {}unset section.option [value]'.format(bot.config.core.help_prefix))
        return
    except (InvalidSection, InvalidSectionOption) as exc:
        bot.say(exc.args[1])
        return

    if value:
        bot.say('Invalid command; no value should be provided to unset.')
        return

    try:
        setattr(section, option, None)
        LOGGER.info('%s.%s unset.', section_name, option)
        bot.say("Unset '{}.{}' successfully.".format(section_name, option))
    except ValueError:
        bot.say('Cannot unset {}.{}; it is a required option.'.format(section_name, option))


@plugin.require_privmsg
@plugin.require_admin
@plugin.command('save')
@plugin.example('.save')
def save_config(bot, trigger):
    """Save state of Sopel's config object to the configuration file."""
    bot.config.save()
    LOGGER.info('Configuration file saved.')
    bot.say('Configuration file saved.')
