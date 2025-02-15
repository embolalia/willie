"""Core Sopel plugin that handles IRC protocol functions.

This plugin allows the bot to run without user-facing functionality:

* it handles client capability negotiation
* it handles client auth (both nick auth and server auth)
* it handles connection registration (RPL_WELCOME, RPL_LUSERCLIENT), dealing
  with error cases such as nick already in use
* it tracks known channels & users (join, quit, nick change and other events)
* it manages blocked (ignored) users

This is written as a plugin to make it easier to extend to support more
responses to standard IRC codes without having to shove them all into the
dispatch function in :class:`sopel.bot.Sopel` and making it easier to maintain.
"""
# Copyright 2008-2011, Sean B. Palmer (inamidst.com) and Michael Yanovich
# (yanovich.net)
# Copyright © 2012, Elad Alfassa <elad@fedoraproject.org>
# Copyright 2012-2015, Elsie Powell embolalia.com
# Copyright 2019, Florian Strzelecki <florian.strzelecki@gmail.com>
#
# Licensed under the Eiffel Forum License 2.
from __future__ import annotations

import base64
import collections
import copy
from datetime import datetime, timedelta, timezone
import functools
import logging
import re
import time
from typing import Callable, Optional, TYPE_CHECKING

from sopel import config, plugin
from sopel.irc import isupport, utils
from sopel.tools import events, jobs, SopelMemory, target

if TYPE_CHECKING:
    from sopel.bot import Sopel, SopelWrapper
    from sopel.tools import Identifier
    from sopel.trigger import Trigger


LOGGER = logging.getLogger(__name__)

WHOX_QUERY = '%nuachrtf'
"""List of WHOX flags coretasks requests."""
WHOX_QUERYTYPE = '999'
"""WHOX querytype to indicate requests/responses from coretasks.

Other plugins should use a different querytype.
"""

MODE_PREFIX_PRIVILEGES = {
    "v": plugin.VOICE,
    "h": plugin.HALFOP,
    "o": plugin.OP,
    "a": plugin.ADMIN,
    "q": plugin.OWNER,
    "y": plugin.OPER,
    "Y": plugin.OPER,
}


def _handle_account_and_extjoin_capabilities(
    cap_req: tuple[str, ...], bot: SopelWrapper, acknowledged: bool,
) -> plugin.CapabilityNegotiation:
    if acknowledged:
        return plugin.CapabilityNegotiation.DONE

    name = ', '.join(cap_req)
    owner_account = bot.settings.core.owner_account
    admin_accounts = bot.settings.core.admin_accounts

    LOGGER.info(
        'Server does not support "%s". '
        'User account validation unavailable or limited.',
        name,
    )
    if owner_account or admin_accounts:
        LOGGER.warning(
            'Owner or admin accounts are configured, but "%s" is not '
            'supported by the server. This may cause unexpected behavior.',
            name,
        )

    return plugin.CapabilityNegotiation.DONE


def _handle_sasl_capability(
    cap_req: tuple[str, ...], bot: SopelWrapper, acknowledged: bool,
) -> plugin.CapabilityNegotiation:
    # Manage CAP REQ :sasl
    auth_method = bot.settings.core.auth_method
    server_auth_method = bot.settings.core.server_auth_method
    is_required = 'sasl' in (auth_method, server_auth_method)

    if not is_required:
        # not required: we are fine, available or not
        return plugin.CapabilityNegotiation.DONE
    elif not acknowledged:
        # required but not available: error, we must stop here
        LOGGER.error(
            'SASL capability is not enabled; '
            'cannot authenticate with SASL.',
        )
        return plugin.CapabilityNegotiation.ERROR

    # Check SASL configuration (password is required for PLAIN/SCRAM)
    password, mech = _get_sasl_pass_and_mech(bot)
    if mech != "EXTERNAL" and not password:
        raise config.ConfigurationError(
            'SASL authentication required but no password available; '
            'please check your configuration file.',
        )

    cap_info = bot.capabilities.get_capability_info('sasl')
    cap_params = cap_info.params

    available_mechs = cap_params.split(',') if cap_params else []

    if available_mechs and mech not in available_mechs:
        # Raise an error if configured to use an unsupported SASL mechanism,
        # but only if the server actually advertised supported mechanisms,
        # i.e. this network supports SASL 3.2

        # SASL 3.1 failure is handled (when possible)
        # by the sasl_mechs() function

        # See https://github.com/sopel-irc/sopel/issues/1780 for background
        raise config.ConfigurationError(
            'SASL mechanism "{mech}" is not advertised by this server; '
            'available mechanisms are: {available}.'.format(
                mech=mech,
                available=', '.join(available_mechs),
            )
        )

    bot.write(('AUTHENTICATE', mech))

    # If we want to do SASL, we have to wait before we can send CAP END. So if
    # we are, wait on 903 (SASL successful) to send it.
    return plugin.CapabilityNegotiation.CONTINUE


CAP_ECHO_MESSAGE = plugin.capability('echo-message')
CAP_MULTI_PREFIX = plugin.capability('multi-prefix')
CAP_AWAY_NOTIFY = plugin.capability('away-notify')
CAP_CHGHOST = plugin.capability('chghost')
CAP_CAP_NOTIFY = plugin.capability('cap-notify')
CAP_SERVER_TIME = plugin.capability('server-time')
CAP_USERHOST_IN_NAMES = plugin.capability('userhost-in-names')
CAP_MESSAGE_TAGS = plugin.capability('message-tags')
CAP_ACCOUNT_NOTIFY = plugin.capability(
    'account-notify', handler=_handle_account_and_extjoin_capabilities)
CAP_EXTENDED_JOIN = plugin.capability(
    'extended-join', handler=_handle_account_and_extjoin_capabilities)
CAP_ACCOUNT_TAG = plugin.capability(
    'account-tag', handler=_handle_account_and_extjoin_capabilities)
CAP_SASL = plugin.capability('sasl', handler=_handle_sasl_capability)


def setup(bot: Sopel) -> None:
    """Set up the coretasks plugin.

    The setup phase is used to activate the throttle feature to prevent a flood
    of JOIN commands when there are too many channels to join.
    """
    bot.memory['retry_join'] = SopelMemory()
    bot.memory['join_events_queue'] = collections.deque()

    # Manage JOIN flood protection
    if bot.settings.core.throttle_join:
        wait_interval = max(bot.settings.core.throttle_wait, 1)
        job = jobs.Job(
            [wait_interval],
            plugin='coretasks',
            label='throttle_join',
            handler=_join_event_processing,
            threaded=True,
            doc=None,
        )
        bot.scheduler.register(job)


def shutdown(bot):
    """Clean up coretasks-related values in the bot's memory."""
    bot.memory['retry_join'] = SopelMemory()
    try:
        bot.memory['join_events_queue'].clear()
    except KeyError:
        pass


def _join_event_processing(bot):
    """Process a batch of JOIN event from the ``join_events_queue`` queue.

    Every time this function is executed, it processes at most
    ``throttle_join`` JOIN events. For each JOIN, it sends a WHO request to
    know more about the channel. This will prevent an excess of flood when
    there are too many channels to join at once.
    """
    batch_size = max(bot.settings.core.throttle_join, 1)
    for _ in range(batch_size):
        try:
            channel = bot.memory['join_events_queue'].popleft()
        except IndexError:
            break
        LOGGER.debug("Sending MODE and WHO after channel JOIN: %s", channel)
        bot.write(["MODE", channel])
        _send_who(bot, channel)


def auth_after_register(bot):
    """Do NickServ/AuthServ auth.

    :param bot: a connected Sopel instance
    :type bot: :class:`sopel.bot.Sopel`

    This function can be used, **after** the bot is connected, to handle one of
    these auth methods:

    * ``nickserv``: send a private message to the NickServ service
    * ``authserv``: send an ``AUTHSERV`` command
    * ``Q``: send an ``AUTH`` command
    * ``userserv``: send a private message to the UserServ service

    .. important::

        If ``core.auth_method`` is set, then ``core.nick_auth_method`` will be
        ignored. If none is set, then this function does nothing.

    """
    if bot.config.core.auth_method:
        auth_method = bot.config.core.auth_method
        auth_username = bot.config.core.auth_username
        auth_password = bot.config.core.auth_password
        auth_target = bot.config.core.auth_target
    elif bot.config.core.nick_auth_method:
        auth_method = bot.config.core.nick_auth_method
        auth_username = (bot.config.core.nick_auth_username or
                         bot.config.core.nick)
        auth_password = bot.config.core.nick_auth_password
        auth_target = bot.config.core.nick_auth_target
    else:
        return

    # nickserv-based auth method needs to check for current nick
    if auth_method == 'nickserv':
        if bot.nick != bot.make_identifier(bot.settings.core.nick):
            LOGGER.warning("Sending nickserv GHOST command.")
            bot.say(
                'GHOST %s %s' % (bot.settings.core.nick, auth_password),
                auth_target or 'NickServ')
        else:
            bot.say('IDENTIFY %s' % auth_password, auth_target or 'NickServ')

    # other methods use account instead of nick
    elif auth_method == 'authserv':
        bot.write(('AUTHSERV', 'auth', auth_username, auth_password))
    elif auth_method == 'Q':
        bot.write(('AUTH', auth_username, auth_password))
    elif auth_method == 'userserv':
        bot.say("LOGIN %s %s" % (auth_username, auth_password),
                auth_target or 'UserServ')


def _execute_perform(bot):
    """Execute commands specified to perform on IRC server connect.

    This function executes the list of commands that can be found in the
    ``core.commands_on_connect`` setting. It automatically replaces any
    ``$nickname`` placeholder in the command with the bot's configured nick.
    """
    if not bot.connection_registered:
        # How did you even get this command, bot?
        raise Exception('Bot must be connected to server to perform commands.')

    commands = bot.config.core.commands_on_connect
    count = len(commands)

    if not count:
        LOGGER.info("No custom command to execute.")
        return

    LOGGER.info("Executing %d custom commands.", count)
    for i, command in enumerate(commands, 1):
        command = command.replace('$nickname', bot.config.core.nick)
        LOGGER.debug("Executing custom command [%d/%d]: %s", i, count, command)
        bot.write((command,))


@plugin.event(events.ERR_NICKNAMEINUSE)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def on_nickname_in_use(bot, trigger):
    """Change the bot's nick when the current one is already in use.

    This can be triggered when the bot disconnects then reconnects before the
    server can notice a client timeout. Other reasons include mischief,
    trolling, and obviously, PEBKAC.

    This will change the current nick by adding a trailing ``_``. If the bot
    sees that a user with its configured nick disconnects (see ``QUIT`` event
    handling), the bot will try to regain it.
    """
    LOGGER.error(
        "Nickname already in use! (Nick: %s; Sender: %s; Args: %r)",
        trigger.nick,
        trigger.sender,
        trigger.args,
    )
    bot.change_current_nick(bot.nick + '_')


@plugin.require_privmsg("This command only works as a private message.")
@plugin.require_admin("This command requires admin privileges.")
@plugin.commands('execute')
def execute_perform(bot, trigger):
    """Execute commands specified to perform on IRC server connect.

    This allows a bot owner or admin to force the execution of commands
    that are automatically performed when the bot connects.
    """
    _execute_perform(bot)


@plugin.event(events.RPL_WELCOME, events.RPL_LUSERCLIENT)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def startup(bot, trigger):
    """Do tasks related to connecting to the network.

    ``001 RPL_WELCOME`` is from RFC2812 and is the first message that is sent
    after the connection has been registered on the network.

    ``251 RPL_LUSERCLIENT`` is a mandatory message that is sent after the
    client connects to the server in RFC1459. RFC2812 does not require it and
    all networks might not send it. We support both.

    If ``sopel.irc.AbstractBot.connection_registered`` is set, this function
    does nothing and returns immediately. Otherwise, the flag is set and the
    function proceeds normally to:

    1. trigger auth method
    2. set bot's ``MODE`` (from ``core.modes``)
    3. join channels (or queue them to join later)
    4. check for security when the ``account-tag`` capability is enabled
    5. execute custom commands
    """
    if bot.connection_registered:
        return

    LOGGER.info(
        'Enabled client capabilities: %s',
        ', '.join(bot.capabilities.enabled),
    )

    # nick shenanigans are serious business, but fortunately RPL_WELCOME
    # includes the actual nick used by the server after truncation, removal
    # of invalid characters, etc. so we can check for such shenanigans
    if trigger.event == events.RPL_WELCOME:
        if bot.nick != trigger.args[0]:
            # setting modes below is just one of the things that won't work
            # as expected if the conditions for running this block are met
            privmsg = (
                "Hi, I'm your bot, %s. The IRC server didn't assign me the "
                "nick you configured. This can cause problems for me, and "
                "make me do weird things. You'll probably want to stop me, "
                "figure out why my nick isn't acceptable, and fix that before "
                "starting me again." % bot.nick
            )
            debug_msg = (
                "RPL_WELCOME indicated the server did not accept the bot's "
                "configured nickname. Requested '%s'; got '%s'. This can "
                "cause unexpected behavior. Please modify the configuration "
                "and restart the bot." % (bot.nick, trigger.args[0])
            )
            LOGGER.critical(debug_msg)
            bot.say(privmsg, bot.config.core.owner)

    # set flag
    bot._connection_registered.set()

    # handle auth method
    auth_after_register(bot)

    # set bot's MODE
    modes = bot.config.core.modes
    if modes:
        if not modes.startswith(('+', '-')):
            # Assume "+" by default.
            modes = '+' + modes
        bot.write(('MODE', bot.nick, modes))

    # warn for insecure auth method if necessary
    if (
        not bot.config.core.owner_account and
        bot.capabilities.is_enabled('account-tag') and
        '@' not in bot.config.core.owner
    ):
        msg = (
            "This network supports using network services to identify you as "
            "my owner, rather than just matching your nickname. This is much "
            "more secure. If you'd like to do this, make sure you're logged in "
            "and reply with \"{}useserviceauth\""
        ).format(bot.config.core.help_prefix)
        bot.say(msg, bot.config.core.owner)

    # execute custom commands
    _execute_perform(bot)


@plugin.event(events.RPL_ISUPPORT)
@plugin.thread(False)
@plugin.unblockable
@plugin.rule('are supported by this server')
@plugin.priority('medium')
def handle_isupport(bot, trigger):
    """Handle ``RPL_ISUPPORT`` events."""
    # remember if certain actionable tokens are known to be supported,
    # before parsing RPL_ISUPPORT
    botmode_support = 'BOT' in bot.isupport
    namesx_support = 'NAMESX' in bot.isupport
    uhnames_support = 'UHNAMES' in bot.isupport
    casemapping_support = 'CASEMAPPING' in bot.isupport
    chantypes_support = 'CHANTYPES' in bot.isupport

    # parse ISUPPORT message from server
    parameters = {}
    for arg in trigger.args:
        try:
            key, value = isupport.parse_parameter(arg)
            parameters[key] = value
        except ValueError:
            # ignore malformed parameter: log a warning and continue
            LOGGER.warning("Unable to parse ISUPPORT parameter: %r", arg)

    bot._isupport = bot._isupport.apply(**parameters)

    # update bot's mode parser
    if 'CHANMODES' in bot.isupport:
        bot.modeparser.chanmodes = bot.isupport.CHANMODES

    if 'PREFIX' in bot.isupport:
        bot.modeparser.privileges = set(bot.isupport.PREFIX.keys())

    # rebuild nick when CASEMAPPING and/or CHANTYPES are set
    if any((
        # was CASEMAPPING support status updated?
        not casemapping_support and 'CASEMAPPING' in bot.isupport,
        # was CHANTYPES support status updated?
        not chantypes_support and 'CHANTYPES' in bot.isupport,
    )):
        # these parameters change how the bot makes Identifiers
        # since bot.nick is an Identifier, it must be rebuilt
        bot.rebuild_nick()

    # was BOT mode support status updated?
    if not botmode_support and 'BOT' in bot.isupport:
        # yes it was! set our mode unless the config overrides it
        botmode = bot.isupport['BOT']
        modes_setting = bot.config.core.modes

        if not modes_setting or botmode not in bot.config.core.modes:
            bot.write(('MODE', bot.nick, '+' + botmode))

    # was NAMESX support status updated?
    if not namesx_support and 'NAMESX' in bot.isupport:
        # yes it was!
        if not bot.capabilities.is_enabled('multi-prefix'):
            # and the multi-prefix capability is not enabled
            # so we can ask the server to use the NAMESX feature
            bot.write(('PROTOCTL', 'NAMESX'))

    # was UHNAMES support status updated?
    if not uhnames_support and 'UHNAMES' in bot.isupport:
        # yes it was!
        if not bot.capabilities.is_enabled('userhost-in-names'):
            # and the userhost-in-names capability is not enabled
            # so we should ask for UHNAMES instead
            bot.write(('PROTOCTL', 'UHNAMES'))


@plugin.event(events.RPL_ENDOFMOTD, events.ERR_NOMOTD)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def join_channels(bot, trigger):
    # join channels
    channels = bot.config.core.channels
    if not channels:
        LOGGER.info("No initial channels to JOIN.")

    elif bot.config.core.throttle_join:
        throttle_rate = int(bot.config.core.throttle_join)
        throttle_wait = max(bot.config.core.throttle_wait, 1)
        channels_joined = 0

        LOGGER.info(
            "Joining %d channels (with JOIN throttle ON); "
            "this may take a moment.",
            len(channels))

        for channel in channels:
            channels_joined += 1
            if not channels_joined % throttle_rate:
                LOGGER.debug(
                    "Waiting %ds before next JOIN batch.",
                    throttle_wait)
                time.sleep(throttle_wait)
            bot.join(channel)
    else:
        LOGGER.info(
            "Joining %d channels (with JOIN throttle OFF); "
            "this may take a moment.",
            len(channels))

        for channel in bot.config.core.channels:
            bot.join(channel)


@plugin.event(events.RPL_MYINFO)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def parse_reply_myinfo(bot, trigger):
    """Handle ``RPL_MYINFO`` events."""
    # keep <client> <servername> <version> only
    # the trailing parameters (mode types) should be read from ISUPPORT
    bot._myinfo = utils.MyInfo(*trigger.args[0:3])

    LOGGER.info(
        "Received RPL_MYINFO from server: %s, %s, %s",
        bot._myinfo.client,
        bot._myinfo.servername,
        bot._myinfo.version,
    )


@plugin.require_privmsg()
@plugin.require_owner()
@plugin.commands('useserviceauth')
def enable_service_auth(bot, trigger):
    """Set owner's account from an authenticated owner.

    This command can be used to automatically configure ``core.owner_account``
    when the owner is known and has a registered account, but the bot doesn't
    have ``core.owner_account`` configured.

    This doesn't work if the ``account-tag`` capability is not available.
    """
    if bot.config.core.owner_account:
        return
    if not bot.capabilities.is_enabled('account-tag'):
        bot.say('This server does not fully support services auth, so this '
                'command is not available.')
        return
    if not trigger.account:
        bot.say('You must be logged in to network services before using this '
                'command.')
        return
    bot.config.core.owner_account = trigger.account
    bot.config.save()
    bot.say('Success! I will now use network services to identify you as my '
            'owner.')
    LOGGER.info(
        "User %s set %s as owner account.",
        trigger.nick,
        trigger.account,
    )


@plugin.event(events.ERR_NOCHANMODES)
@plugin.priority('medium')
def retry_join(bot, trigger):
    """Give NickServ enough time to identify on a +R channel.

    Give NickServ enough time to identify, and retry rejoining an
    identified-only (+R) channel. Maximum of ten rejoin attempts.
    """
    channel = trigger.args[1]
    if channel in bot.memory['retry_join'].keys():
        bot.memory['retry_join'][channel] += 1
        if bot.memory['retry_join'][channel] > 10:
            LOGGER.warning("Failed to join %s after 10 attempts.", channel)
            return
        LOGGER.info(
            "Rejoining channel %r failed, will retry in 6s.",
            str(channel))
        time.sleep(6)
    else:
        bot.memory['retry_join'][channel] = 0

    attempt = bot.memory['retry_join'][channel] + 1
    LOGGER.info(
        "Trying to rejoin channel %r (attempt %d/10)",
        str(channel), attempt)
    bot.join(channel)


@plugin.rule('(.*)')
@plugin.event(events.RPL_NAMREPLY)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def handle_names(bot, trigger):
    """Handle NAMES responses.

    This function keeps track of users' privileges when Sopel joins channels.
    """
    # TODO specific to one channel type. See issue 281.
    channels = re.search(r'(#\S*)', trigger.raw)
    if not channels:
        return
    channel = bot.make_identifier(channels.group(1))
    if channel not in bot.channels:
        bot.channels[channel] = target.Channel(
            channel,
            identifier_factory=bot.make_identifier,
        )

    # This could probably be made flexible in the future, but I don't think
    # it'd be worth it.
    # If this ever needs to be updated, remember to change the mode handling in
    # the WHO-handler functions below, too.
    mapping = {
        "+": plugin.VOICE,
        "%": plugin.HALFOP,
        "@": plugin.OP,
        "&": plugin.ADMIN,
        "~": plugin.OWNER,
        "!": plugin.OPER,
    }

    uhnames = 'UHNAMES' in bot.isupport
    userhost_in_names = bot.capabilities.is_enabled('userhost-in-names')

    names = trigger.split()
    for name in names:
        username = hostname = None

        if uhnames or userhost_in_names:
            try:
                name, mask = name.rsplit('!', 1)
                username, hostname = mask.split('@', 1)
            except ValueError:
                # server advertised either UHNAMES or userhost-in-names, but
                # isn't sending the hostmask with all listed nicks
                # It's probably ZNC. https://github.com/znc/znc/issues/1224
                LOGGER.debug(
                    '%s is enabled, but still got RPL_NAMREPLY item without a hostmask. '
                    'IRC server/bouncer is not spec compliant.',
                    'UHNAMES' if uhnames else 'userhost-in-names')

        priv = 0
        for prefix, value in mapping.items():
            if prefix in name:
                priv = priv | value

        nick = bot.make_identifier(name.lstrip(''.join(mapping.keys())))
        user = bot.users.get(nick)
        if user is None:
            # The username/hostname will be included in a NAMES reply only if
            # userhost-in-names is available. We can use them if present.
            # Fortunately, the user should already exist in bot.users by the
            # time this code runs, so this is 99.9% ass-covering.
            user = target.User(nick, username, hostname)
            bot.users[nick] = user
        bot.channels[channel].add_user(user, privs=priv)


@plugin.rule('(.*)')
@plugin.event('MODE')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_modes(bot, trigger):
    """Track changes from received MODE commands."""
    _parse_modes(bot, trigger.args)


@plugin.priority('high')
@plugin.event(events.RPL_CHANNELMODEIS)
@plugin.thread(False)
@plugin.unblockable
def initial_modes(bot, trigger):
    """Populate channel modes from response to MODE request sent after JOIN."""
    _parse_modes(bot, trigger.args[1:], clear=True)


def _parse_modes(bot, args, clear=False):
    """Parse MODE message and apply changes to internal state.

    Sopel, by default, doesn't know how to parse other types than A, B, C, and
    D, and only a preset of privileges.

    .. seealso::

        Parsing mode messages can be tricky and complicated to understand. In
        any case it is better to read the IRC specifications about channel
        modes at https://modern.ircdocs.horse/#channel-mode

    """
    channel_name = bot.make_identifier(args[0])
    if channel_name.is_nick():
        # We don't do anything with user modes
        LOGGER.debug("Ignoring user modes: %r", args)
        return

    channel = bot.channels[channel_name]

    # Unreal 3 sometimes sends an extraneous trailing space. If we're short an
    # arg, we'll find out later.
    if args[-1] == "":
        args.pop()
    # If any args are still empty, that's something we may not be prepared for,
    # but let's continue anyway hoping they're trailing / not important.
    if len(args) < 2 or not all(args):
        LOGGER.debug(
            "The server sent a possibly malformed MODE message: %r", args)

    # parse the modestring with the parameters
    modeinfo = bot.modeparser.parse(args[1], tuple(args[2:]))

    # set, unset, or update channel's modes based on the mode type
    # modeinfo.modes contains only the valid parsed modes
    # coretask can handle type A, B, C, and D only
    modes = {} if clear else copy.deepcopy(channel.modes)
    for letter, mode, is_added, param in modeinfo.modes:
        if letter == 'A':
            # type A is a multi-value mode and always requires a parameter
            if mode not in modes:
                modes[mode] = set()
            if is_added:
                modes[mode].add(param)
            elif param in modes[mode]:
                modes[mode].remove(param)
                # remove mode if empty
                if not modes[mode]:
                    modes.pop(mode)
        elif letter == 'B':
            # type B is a single-value mode and always requires a parameter
            if is_added:
                modes[mode] = param
            elif mode in modes:
                modes.pop(mode)
        elif letter == 'C':
            # type C is a single-value mode and requires a parameter when added
            if is_added:
                modes[mode] = param
            elif mode in modes:
                modes.pop(mode)
        elif letter == 'D':
            # type D is a flag (True or False) and doesn't have a parameter
            if is_added:
                modes[mode] = True
            elif mode in modes:
                modes.pop(mode)

    # atomic change of channel's modes
    channel.modes = modes

    # update user privileges in channel
    # modeinfo.privileges contains only the valid parsed privileges
    for privilege, is_added, param in modeinfo.privileges:
        # User privs modes, always have a param
        nick = bot.make_identifier(param)
        priv = channel.privileges.get(nick, 0)
        value = MODE_PREFIX_PRIVILEGES[privilege]
        if is_added:
            priv = priv | value
        else:
            priv = priv & ~value
        channel.privileges[nick] = priv

    # log ignored modes (modes Sopel doesn't know how to handle)
    if modeinfo.ignored_modes:
        LOGGER.warning(
            "Unknown MODE message, sending WHO. Message was: %r",
            args,
        )
        # send a WHO message to ensure we didn't miss anything
        _send_who(bot, channel_name)

    # log leftover parameters (too many arguments)
    if modeinfo.leftover_params:
        LOGGER.warning(
            "Too many arguments received for MODE: args=%r chanmodes=%r",
            args,
            bot.modeparser.chanmodes,
        )

    LOGGER.info("Updated mode for channel: %s", channel.name)
    LOGGER.debug("Channel %r mode: %r", str(channel.name), channel.modes)


@plugin.event('NICK')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_nicks(bot, trigger):
    """Track nickname changes and maintain our chanops list accordingly."""
    old = trigger.nick
    new = bot.make_identifier(trigger)

    # Give debug message, and PM the owner, if the bot's own nick changes.
    if old == bot.nick and new != bot.nick:
        # Is this the original nick being regained?
        # e.g. by ZNC's keepnick module running in front of Sopel
        if old != bot.config.core.nick and new == bot.config.core.nick:
            LOGGER.info(
                "Regained configured nick. Restarting is still recommended.")
        else:
            privmsg = (
                "Hi, I'm your bot, %s. Something has made my nick change. This "
                "can cause some problems for me, and make me do weird things. "
                "You'll probably want to restart me, and figure out what made "
                "that happen so you can stop it happening again. (Usually, it "
                "means you tried to give me a nick that's protected by NickServ.)"
            ) % bot.config.core.nick
            debug_msg = (
                "Nick changed by server. This can cause unexpected behavior. "
                "Please restart the bot."
            )
            LOGGER.critical(debug_msg)
            bot.say(privmsg, bot.config.core.owner)

        # Always update bot.nick anyway so Sopel doesn't lose its self-identity.
        # This should cut down the number of "weird things" that happen while
        # the active nick doesn't match the config, but it's not a substitute
        # for regaining the expected nickname.
        LOGGER.info("Updating bot.nick property with server-changed nick.")
        bot._nick = new
        return

    for channel in bot.channels.values():
        channel.rename_user(old, new)
    if old in bot.users:
        bot.users[new] = bot.users.pop(old)

    LOGGER.info("User named %r is now known as %r.", str(old), str(new))


@plugin.rule('(.*)')
@plugin.event('PART')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_part(bot, trigger):
    """Track users leaving channels."""
    nick = trigger.nick
    channel = trigger.sender
    _remove_from_channel(bot, nick, channel)
    LOGGER.info("User %r left a channel: %s", str(nick), channel)


@plugin.event('KICK')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_kick(bot, trigger):
    """Track users kicked from channels."""
    nick = bot.make_identifier(trigger.args[1])
    channel = trigger.sender
    _remove_from_channel(bot, nick, channel)
    LOGGER.info(
        "User %r got kicked by %r from a channel: %s",
        str(nick),
        str(trigger.nick),
        channel,
    )


def _remove_from_channel(bot, nick, channel):
    if nick == bot.nick:
        bot.channels.pop(channel, None)

        lost_users = []
        for nick_, user in bot.users.items():
            user.channels.pop(channel, None)
            if not user.channels:
                lost_users.append(nick_)
        for nick_ in lost_users:
            bot.users.pop(nick_, None)
    else:
        user = bot.users.get(nick)
        if user and channel in user.channels:
            bot.channels[channel].clear_user(nick)
            if not user.channels:
                bot.users.pop(nick, None)


def _send_who(bot, mask):
    if 'WHOX' in bot.isupport:
        # WHOX syntax, see http://faerion.sourceforge.net/doc/irc/whox.var
        # Needed for accounts in WHO replies. The `WHOX_QUERYTYPE` parameter
        # for WHO is used to identify the reply from the server and confirm
        # that it has the requested format. WHO replies with different
        # querytypes in the response were initiated elsewhere and will be
        # ignored.
        bot.write(['WHO', mask, '{},{}'.format(WHOX_QUERY, WHOX_QUERYTYPE)])
    else:
        # We might be on an old network, but we still care about keeping our
        # user list updated
        bot.write(['WHO', mask])

    target_id = bot.make_identifier(mask)
    if not target_id.is_nick():
        bot.channels[target_id].last_who = datetime.now(timezone.utc)


@plugin.interval(30)
def _periodic_send_who(bot):
    """Periodically send a WHO request to keep user information up-to-date."""
    if bot.capabilities.is_enabled('away-notify'):
        # WHO not needed to update 'away' status
        return

    # Loop through the channels to find the one that has the longest time since the last WHO
    # request, and issue a WHO request only if the last request for the channel was more than
    # 120 seconds ago.
    who_trigger_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    selected_channel = None
    for channel_name, channel in bot.channels.items():
        if channel.last_who is None:
            # WHO was never sent yet to this channel: stop here
            selected_channel = channel_name
            break
        if channel.last_who < who_trigger_time:
            # this channel's last who request is the most outdated one at the moment
            selected_channel = channel_name
            who_trigger_time = channel.last_who

    if selected_channel is not None:
        # selected_channel's last who is either none or the oldest valid
        LOGGER.debug("Sending WHO for channel: %s", selected_channel)
        _send_who(bot, selected_channel)


@plugin.event('JOIN')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_join(bot, trigger):
    """Track users joining channels.

    When a user joins a channel, the bot will send (or queue) a ``WHO`` command
    to know more about said user (privileges, modes, etc.).
    """
    channel = trigger.sender
    new_channel = channel not in bot.channels
    self_join = trigger.nick == bot.nick
    new_user = trigger.nick not in bot.users

    # is it a new channel?
    if new_channel:
        bot.channels[channel] = target.Channel(
            channel,
            identifier_factory=bot.make_identifier,
        )

    # did *we* just join?
    if self_join:
        LOGGER.info("Channel joined: %s", channel)
        bot.channels[channel].join_time = trigger.time
        if bot.settings.core.throttle_join:
            LOGGER.debug("JOIN event added to queue for channel: %s", channel)
            bot.memory['join_events_queue'].append(channel)
        else:
            LOGGER.debug("Send MODE and direct WHO for channel: %s", channel)
            bot.write(["MODE", channel])
            _send_who(bot, channel)
    else:
        LOGGER.info(
            "Channel %r joined by user: %s",
            str(channel), trigger.nick)

    # set initial values
    if new_user:
        user = target.User(trigger.nick, trigger.user, trigger.host)
        bot.users[trigger.nick] = user
    else:
        user = bot.users.get(trigger.nick)
    bot.channels[channel].add_user(user)

    if len(trigger.args) > 1 and trigger.args[1] != '*' and (
        bot.capabilities.is_enabled('account-notify') and
        bot.capabilities.is_enabled('extended-join')
    ):
        user.account = trigger.args[1]

    if new_user and not new_channel:
        # send WHO to populate new user's realname etc.
        _send_who(bot, trigger.nick)


@plugin.event('QUIT')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_quit(bot, trigger):
    """Track when users quit channels."""
    for channel in bot.channels.values():
        channel.clear_user(trigger.nick)
    bot.users.pop(trigger.nick, None)

    LOGGER.info("User quit: %s", trigger.nick)

    configured_nick = bot.make_identifier(bot.settings.core.nick)
    if trigger.nick == configured_nick and trigger.nick != bot.nick:
        # old nick is now available, let's change nick again
        bot.change_current_nick(bot.settings.core.nick)
        auth_after_register(bot)


def _receive_cap_ls_reply(bot: SopelWrapper, trigger: Trigger) -> None:
    if not bot.capabilities.handle_ls(bot, trigger):
        # multi-line, we must wait for more
        return

    if not bot.request_capabilities():
        # Negotiation end because there is nothing to request
        LOGGER.info('No capability negotiation.')
        bot.write(('CAP', 'END'))


def _handle_cap_acknowledgement(
    bot: SopelWrapper,
    cap_req: tuple[str, ...],
    results: list[tuple[bool, Optional[plugin.CapabilityNegotiation]]],
    was_completed: bool,
) -> None:
    if any(
        callback_result[1] == plugin.CapabilityNegotiation.ERROR
        for callback_result in results
    ):
        # error: a plugin needs something and the bot cannot function properly
        LOGGER.error(
            'Capability negotiation failed for request: "%s"',
            ' '.join(cap_req),
        )
        bot.write(('CAP', 'END'))  # close negotiation now
        bot.quit('Error negotiating capabilities.')

    if not was_completed and bot.cap_requests.is_complete:
        # success: negotiation is complete and wasn't already
        LOGGER.info('Capability negotiation ended successfuly.')
        bot.write(('CAP', 'END'))  # close negotiation now


def _receive_cap_ack(bot: SopelWrapper, trigger: Trigger) -> None:
    was_completed = bot.cap_requests.is_complete
    cap_ack: tuple[str, ...] = bot.capabilities.handle_ack(bot, trigger)

    try:
        result: Optional[
            list[tuple[bool, Optional[plugin.CapabilityNegotiation]]]
        ] = bot.cap_requests.acknowledge(bot, cap_ack)
    except config.ConfigurationError as error:
        LOGGER.error(
            'Configuration error on ACK capability "%s": %s',
            ', '.join(cap_ack),
            error,
        )
        bot.write(('CAP', 'END'))  # close negotiation now
        bot.quit('Configuration error.')
        return None
    except Exception as error:
        LOGGER.exception(
            'Error on ACK capability "%s": %s',
            ', '.join(cap_ack),
            error,
        )
        bot.write(('CAP', 'END'))  # close negotiation now
        bot.quit('Error negotiating capabilities.')
        return None

    if result is None:
        # a plugin may have requested the capability without using the proper
        # interface: ignore
        return None

    _handle_cap_acknowledgement(bot, cap_ack, result, was_completed)


def _receive_cap_nak(bot: SopelWrapper, trigger: Trigger) -> None:
    was_completed = bot.cap_requests.is_complete
    cap_ack = bot.capabilities.handle_nak(bot, trigger)

    try:
        result: Optional[
            list[tuple[bool, Optional[plugin.CapabilityNegotiation]]]
        ] = bot.cap_requests.deny(bot, cap_ack)
    except config.ConfigurationError as error:
        LOGGER.error(
            'Configuration error on NAK capability "%s": %s',
            ', '.join(cap_ack),
            error,
        )
        bot.write(('CAP', 'END'))  # close negotiation now
        bot.quit('Configuration error.')
        return None
    except Exception as error:
        LOGGER.exception(
            'Error on NAK capability "%s": %s',
            ', '.join(cap_ack),
            error,
        )
        bot.write(('CAP', 'END'))  # close negotiation now
        bot.quit('Error negotiating capabilities.')
        return None

    if result is None:
        # a plugin may have requested the capability without using the proper
        # interface: ignore
        return None

    _handle_cap_acknowledgement(bot, cap_ack, result, was_completed)


def _receive_cap_new(bot: SopelWrapper, trigger: Trigger) -> None:
    cap_new = bot.capabilities.handle_new(bot, trigger)
    LOGGER.info('Capability is now available: %s', ', '.join(cap_new))
    # TODO: try to request what wasn't requested before


def _receive_cap_del(bot: SopelWrapper, trigger: Trigger) -> None:
    cap_del = bot.capabilities.handle_del(bot, trigger)
    LOGGER.info('Capability is now unavailable: %s', ', '.join(cap_del))
    # TODO: what to do when a CAP is removed? NAK callbacks?


CAP_HANDLERS: dict[str, Callable[[SopelWrapper, Trigger], None]] = {
    'LS': _receive_cap_ls_reply,  # Server is listing capabilities
    'ACK': _receive_cap_ack,  # Server is acknowledging a capability
    'NAK': _receive_cap_nak,  # Server is denying a capability
    'NEW': _receive_cap_new,  # Server is adding new capability
    'DEL': _receive_cap_del,  # Server is removing a capability
}


@plugin.event('CAP')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def receive_cap_list(bot: SopelWrapper, trigger: Trigger) -> None:
    """Handle client capability negotiation."""
    subcommand = trigger.args[1]
    if subcommand in CAP_HANDLERS:
        handler = CAP_HANDLERS[subcommand]
        handler(bot, trigger)
    else:
        LOGGER.info('Unknown CAP subcommand received: %s', subcommand)


def send_authenticate(bot, token):
    """Send ``AUTHENTICATE`` command to server with the given ``token``.

    :param bot: instance of IRC bot that must authenticate
    :param str token: authentication token

    In case the ``token`` is more than 400 bytes, we need to split it and send
    as many ``AUTHENTICATE`` commands as needed. If the last chunk is 400 bytes
    long, we must also send a last empty command (`AUTHENTICATE +` is for empty
    line), so the server knows we are done with ``AUTHENTICATE``.

    .. seealso::

        https://ircv3.net/specs/extensions/sasl-3.1.html#the-authenticate-command

    """
    # payload is a base64 encoded token
    payload = base64.b64encode(token.encode('utf-8'))

    # split the payload into chunks of at most 400 bytes
    chunk_size = 400
    for i in range(0, len(payload), chunk_size):
        offset = i + chunk_size
        chunk = payload[i:offset]
        bot.write(('AUTHENTICATE', chunk))

    # send empty (+) AUTHENTICATE when payload's length is a multiple of 400
    if len(payload) % chunk_size == 0:
        bot.write(('AUTHENTICATE', '+'))


@plugin.event('AUTHENTICATE')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def auth_proceed(bot, trigger):
    """Handle client-initiated SASL auth.

    If the chosen mechanism is client-first, the server sends an empty
    response (``AUTHENTICATE +``). In that case, Sopel will handle SASL auth
    that uses a token.

    .. important::

        If ``core.auth_method`` is set, then ``core.server_auth_method`` will
        be ignored. If none is set, then this function does nothing.

    """
    if bot.config.core.auth_method == 'sasl':
        mech = bot.config.core.auth_target or 'PLAIN'
    elif bot.config.core.server_auth_method == 'sasl':
        mech = bot.config.core.server_auth_sasl_mech or 'PLAIN'
    else:
        return

    if mech == 'EXTERNAL':
        if trigger.args[0] != '+':
            # not an expected response from the server; abort SASL
            token = '*'
        else:
            token = '+'

        bot.write(('AUTHENTICATE', token))
        return

    if bot.config.core.auth_method == 'sasl':
        sasl_username = bot.config.core.auth_username
        sasl_password = bot.config.core.auth_password
    elif bot.config.core.server_auth_method == 'sasl':
        sasl_username = bot.config.core.server_auth_username
        sasl_password = bot.config.core.server_auth_password
    else:
        # How did we get here? I am not good with computer
        return

    sasl_username = sasl_username or bot.nick

    if mech == 'PLAIN':
        if trigger.args[0] == '+':
            sasl_token = _make_sasl_plain_token(sasl_username, sasl_password)
            LOGGER.info("Sending SASL Auth token.")
            send_authenticate(bot, sasl_token)
            return
        else:
            # Not an expected response from the server
            LOGGER.warning(
                'Aborting SASL: unexpected server reply "%s"', trigger,
            )
            # Send `authenticate-abort` command
            # See https://ircv3.net/specs/extensions/sasl-3.1#the-authenticate-command
            bot.write(('AUTHENTICATE', '*'))
            return

    # TODO: Implement SCRAM challenges


def _make_sasl_plain_token(account, password):
    return '\x00'.join((account, account, password))


@plugin.event(events.RPL_SASLSUCCESS)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def sasl_success(bot: SopelWrapper, trigger: Trigger) -> None:
    """Resume capability negotiation on successful SASL auth."""
    LOGGER.info("Successful SASL Auth.")
    bot.resume_capability_negotiation(CAP_SASL.cap_req, 'coretasks')


@plugin.event(events.ERR_SASLFAIL)
@plugin.event(events.ERR_SASLTOOLONG)
@plugin.event(events.ERR_SASLABORTED)
@plugin.event(events.ERR_NICKLOCKED)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def sasl_fail(bot, trigger):
    """SASL Auth Failed: log the error and quit."""
    LOGGER.error(
        "SASL Auth Failed; check your configuration: %s",
        str(trigger))
    # negotiation done
    bot.resume_capability_negotiation(CAP_SASL.cap_req, 'coretasks')
    # quit
    bot.quit('SASL Auth Failed')


@plugin.event(events.RPL_SASLMECHS)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('low')
def sasl_mechs(bot, trigger):
    # Presumably we're only here if we said we actually *want* sasl, but still
    # check anyway in case the server glitched.
    password, mech = _get_sasl_pass_and_mech(bot)
    if not password:
        # negotiation done
        bot.resume_capability_negotiation(CAP_SASL.cap_req, 'coretasks')
        return

    supported_mechs = trigger.args[1].split(',')
    if mech not in supported_mechs:
        """
        How we get here:

        1. Sopel connects to a network advertising SASL 3.1
        2. SASL 3.1 doesn't advertise supported mechanisms up front, so Sopel
           blindly goes ahead with whatever SASL config it's set to use
        3. The server doesn't support the mechanism Sopel used, and is a good
           IRC citizen, so it sends this optional numeric, 908 RPL_SASLMECHS

        Note that misconfigured SASL 3.1 will just silently fail when connected
        to an IRC server NOT implementing the optional 908 reply.

        A network with SASL 3.2 should theoretically never get this far because
        Sopel should catch the unadvertised mechanism in CAP_SASL.

        See https://github.com/sopel-irc/sopel/issues/1780 for background
        """
        LOGGER.error(
            "Configured SASL mechanism '%s' is not advertised by this server. "
            "Advertised values: %s",
            mech,
            ', '.join(supported_mechs),
        )
        bot.resume_capability_negotiation(CAP_SASL.cap_req, 'coretasks')
        bot.quit('Wrong SASL configuration.')
    else:
        LOGGER.info(
            "Selected SASL mechanism is %s, advertised: %s",
            mech,
            ', '.join(supported_mechs),
        )


def _get_sasl_pass_and_mech(bot):
    password = None
    mech = None

    if bot.config.core.auth_method == 'sasl':
        password = bot.config.core.auth_password
        mech = bot.config.core.auth_target
    elif bot.config.core.server_auth_method == 'sasl':
        password = bot.config.core.server_auth_password
        mech = bot.config.core.server_auth_sasl_mech

    mech = 'PLAIN' if mech is None else mech.upper()

    return password, mech


# Live blocklist editing


@plugin.commands('blocks')
@plugin.example(r'.blocks del nick falsep0sitive', user_help=True)
@plugin.example(r'.blocks add host some\.malicious\.network', user_help=True)
@plugin.example(r'.blocks add nick sp(a|4)mb(o|0)t\d*', user_help=True)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('low')
@plugin.require_admin
def blocks(bot, trigger):
    """Manage Sopel's blocking features.

    Full argspec: `list [nick|host]` or `[add|del] [nick|host] pattern`
    """
    STRINGS = {
        "success_del": "Successfully deleted block: %s",
        "success_add": "Successfully added block: %s",
        "no_nick": "No matching nick block found for: %s",
        "no_host": "No matching host block found for: %s",
        "invalid": "Invalid format for %s a block. Try: .blocks add (nick|host) sopel",
        "invalid_display": "Invalid input for displaying blocks.",
        "nonelisted": "No %s listed in the blocklist.",
        'huh': "I could not figure out what you wanted to do.",
    }

    hosts = set(s for s in bot.config.core.host_blocks if s != '')
    nicks = set(bot.make_identifier(nick)
                for nick in bot.config.core.nick_blocks
                if nick != '')
    text = trigger.group().split()

    if len(text) == 3 and text[1] == "list":
        if text[2] == "host":
            if len(hosts) > 0:
                blocked = ', '.join(str(host) for host in hosts)
                bot.say("Blocked hosts: {}".format(blocked))
            else:
                bot.reply(STRINGS['nonelisted'] % ('hosts'))
        elif text[2] == "nick":
            if len(nicks) > 0:
                blocked = ', '.join(str(nick) for nick in nicks)
                bot.say("Blocked nicks: {}".format(blocked))
            else:
                bot.reply(STRINGS['nonelisted'] % ('nicks'))
        else:
            bot.reply(STRINGS['invalid_display'])

    elif len(text) == 4 and text[1] == "add":
        if text[2] == "nick":
            nicks.add(text[3])
            bot.config.core.nick_blocks = nicks
            bot.config.save()
        elif text[2] == "host":
            hosts.add(text[3].lower())
            bot.config.core.host_blocks = list(hosts)
            bot.config.save()
        else:
            bot.reply(STRINGS['invalid'] % ("adding"))
            return

        bot.reply(STRINGS['success_add'] % (text[3]))

    elif len(text) == 4 and text[1] == "del":
        if text[2] == "nick":
            nick = bot.make_identifier(text[3])
            if nick not in nicks:
                bot.reply(STRINGS['no_nick'] % (text[3]))
                return
            nicks.remove(nick)
            bot.config.core.nick_blocks = [str(n) for n in nicks]
            bot.config.save()
            bot.reply(STRINGS['success_del'] % (text[3]))
        elif text[2] == "host":
            host = text[3].lower()
            if host not in hosts:
                bot.reply(STRINGS['no_host'] % (text[3]))
                return
            hosts.remove(host)
            bot.config.core.host_blocks = [str(m) for m in hosts]
            bot.config.save()
            bot.reply(STRINGS['success_del'] % (text[3]))
        else:
            bot.reply(STRINGS['invalid'] % ("deleting"))
            return
    else:
        bot.reply(STRINGS['huh'])


@plugin.event('CHGHOST')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def recv_chghost(bot, trigger):
    """Track user/host changes."""
    if trigger.nick not in bot.users:
        bot.users[trigger.nick] = target.User(
            trigger.nick, trigger.user, trigger.host)

    try:
        new_user, new_host = trigger.args
    except ValueError:
        LOGGER.warning(
            "Ignoring CHGHOST command with %s arguments: %r",
            'extra' if len(trigger.args) > 2 else 'insufficient',
            trigger.args)
        return

    bot.users[trigger.nick].user = new_user
    bot.users[trigger.nick].host = new_host
    LOGGER.info(
        "Update user@host for nick %r: %s@%s",
        str(trigger.nick), new_user, new_host)


@plugin.event('ACCOUNT')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def account_notify(bot, trigger):
    """Track users' accounts."""
    if trigger.nick not in bot.users:
        bot.users[trigger.nick] = target.User(
            trigger.nick, trigger.user, trigger.host)
    account = trigger.args[0]
    if account == '*':
        account = None
    bot.users[trigger.nick].account = account
    LOGGER.info("Update account for nick %r: %s", str(trigger.nick), account)


@plugin.event(events.RPL_WHOSPCRPL)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def recv_whox(bot, trigger):
    """Track ``WHO`` responses when ``WHOX`` is enabled."""
    if len(trigger.args) < 2 or trigger.args[1] != WHOX_QUERYTYPE:
        # Ignored, some plugin probably called WHO
        LOGGER.debug("Ignoring WHO reply for channel '%s'; not queried by coretasks", trigger.args[1])
        return
    if len(trigger.args) != len(WHOX_QUERY):
        LOGGER.warning(
            "While populating `bot.accounts` a WHO response was malformed.")
        return
    _, _, channel, user, host, nick, status, account, realname = trigger.args
    botmode = bot.isupport.get('BOT')
    away = 'G' in status
    is_bot = (botmode in status) if botmode else None
    modes = ''.join([c for c in status if c in '~&@%+!'])
    _record_who(bot, channel, user, host, nick, realname, account, away, is_bot, modes)


def _record_who(
    bot: Sopel,
    channel: Identifier,
    user: str,
    host: str,
    nick: str,
    realname: Optional[str] = None,
    account: Optional[str] = None,
    away: Optional[bool] = None,
    is_bot: Optional[bool] = None,
    modes: Optional[str] = None,
) -> None:
    nick = bot.make_identifier(nick)
    channel = bot.make_identifier(channel)
    if nick not in bot.users:
        usr = target.User(nick, user, host)
        bot.users[nick] = usr
    else:
        usr = bot.users[nick]
        # check for & fill in sparse User added by handle_names()
        if usr.host is None and host:
            usr.host = host
        if usr.user is None and user:
            usr.user = user
    if realname:
        usr.realname = realname
    if account == '0':
        usr.account = None
    else:
        usr.account = account
    if away is not None:
        usr.away = away
    if is_bot is not None:
        usr.is_bot = is_bot
    priv = 0
    if modes:
        mapping = {
            "+": plugin.VOICE,
            "%": plugin.HALFOP,
            "@": plugin.OP,
            "&": plugin.ADMIN,
            "~": plugin.OWNER,
            "!": plugin.OPER,
        }
        for c in modes:
            priv = priv | mapping[c]
    if channel not in bot.channels:
        bot.channels[channel] = target.Channel(
            channel,
            identifier_factory=bot.make_identifier,
        )

    bot.channels[channel].add_user(usr, privs=priv)


@plugin.event(events.RPL_WHOREPLY)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def recv_who(bot, trigger):
    """Track ``WHO`` responses when ``WHOX`` is not enabled."""
    channel, user, host, _, nick, status = trigger.args[1:7]
    botmode = bot.isupport.get('BOT')
    realname = trigger.args[-1].partition(' ')[-1]
    away = 'G' in status
    is_bot = (botmode in status) if botmode else None
    modes = ''.join([c for c in status if c in '~&@%+!'])
    _record_who(
        bot, channel, user, host, nick, realname,
        away=away, is_bot=is_bot, modes=modes,
    )


@plugin.event('AWAY')
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_notify(bot, trigger):
    """Track users going away or coming back."""
    if trigger.nick not in bot.users:
        bot.users[trigger.nick] = target.User(
            trigger.nick, trigger.user, trigger.host)
    user = bot.users[trigger.nick]
    user.away = bool(trigger.args)
    state_change = 'went away' if user.away else 'came back'
    LOGGER.info("User %s: %s", state_change, trigger.nick)


@plugin.event('TOPIC')
@plugin.event(events.RPL_TOPIC)
@plugin.thread(False)
@plugin.unblockable
@plugin.priority('medium')
def track_topic(bot, trigger):
    """Track channels' topics."""
    if trigger.event != 'TOPIC':
        channel = trigger.args[1]
    else:
        channel = trigger.args[0]
    if channel not in bot.channels:
        return
    bot.channels[channel].topic = trigger.args[-1]
    LOGGER.info("Channel's topic updated: %s", channel)


@plugin.rule(r'(?u).*(.+://\S+).*')
def handle_url_callbacks(bot, trigger):
    """Dispatch callbacks on URLs

    For each URL found in the trigger, trigger the URL callback registered
    through the now deprecated :meth:`sopel.bot.Sopel.register_url_callback`.

    .. deprecated:: 8.1

        This is deprecated and will be removed in Sopel 9.0.

    """
    # find URLs in the trigger
    for url in trigger.urls:
        # find callbacks for said URL
        for pattern, function in bot._url_callbacks.items():
            match = pattern.search(url)
            # trigger callback defined by the `@url` decorator
            if match and hasattr(function, 'url_regex'):
                # bake the `match` argument in before passing the callback on
                @functools.wraps(function)
                def decorated(bot, trigger):
                    return function(bot, trigger, match=match)

                bot.call(decorated, bot, trigger)
