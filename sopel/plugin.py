"""This contains decorators and other tools for creating Sopel plugins."""
# Copyright 2013, Ari Koivula, <ari@koivu.la>
# Copyright © 2013, Elad Alfassa <elad@fedoraproject.org>
# Copyright 2013, Lior Ramati <firerogue517@gmail.com>
# Copyright 2019, deathbybandaid, deathbybandaid.net
# Copyright 2019, dgw, technobabbl.es
# Copyright 2019, Florian Strzelecki <florian.strzelecki@gmail.com>
# Licensed under the Eiffel Forum License 2.

from __future__ import annotations

import enum
import functools
import logging
import re
from typing import (
    Callable,
    Literal,
    Optional,
    Pattern,
    Protocol,
    TYPE_CHECKING,
    Union,
)

# import and expose privileges as shortcut
from sopel.privileges import AccessLevel

VOICE = AccessLevel.VOICE
HALFOP = AccessLevel.HALFOP
OP = AccessLevel.OP
ADMIN = AccessLevel.ADMIN
OWNER = AccessLevel.OWNER
OPER = AccessLevel.OPER


if TYPE_CHECKING:
    from collections.abc import Iterable
    from sopel.bot import SopelWrapper

__all__ = [
    # constants
    'NOLIMIT', 'VOICE', 'HALFOP', 'OP', 'ADMIN', 'OWNER', 'OPER',
    # decorators
    'action_command',
    'action_commands',
    'allow_bots',
    'capability',
    'CapabilityNegotiation',
    'command',
    'commands',
    'ctcp',
    'echo',
    'event',
    'example',
    'find',
    'find_lazy',
    'interval',
    'label',
    'nickname_command',
    'nickname_commands',
    'output_prefix',
    'priority',
    'rate',
    'rate_user',
    'rate_channel',
    'rate_global',
    'require_account',
    'require_admin',
    'require_bot_privilege',
    'require_chanmsg',
    'require_owner',
    'require_privilege',
    'require_privmsg',
    'rule',
    'rule_lazy',
    'search',
    'search_lazy',
    'thread',
    'unblockable',
    'url',
    'url_lazy',
]


LOGGER = logging.getLogger(__name__)


NOLIMIT = 1
"""Return value for ``callable``\\s, which suppresses rate limiting.

Returning this value means the triggering user will not be prevented from
triggering the same callable again within the rate limit. This can be used,
for example, to allow a user to retry a failed command immediately.

.. versionadded:: 4.0
"""


class CapabilityNegotiation(enum.Enum):
    """Capability Negotiation status."""

    DONE = enum.auto()
    """The capability negotiation can end.

    This must be returned by a capability request handler to signify to the bot
    that the capability has been properly negotiated and negotiation can end if
    all other conditions are met.
    """

    CONTINUE = enum.auto()
    """The capability negotiation must continue.

    This must be returned by a capability request handler to signify to the bot
    that the capability requires further processing (e.g. SASL
    authentication) and negotiation must not end yet.

    The plugin author MUST signal the bot once the negotiation is done.
    """

    ERROR = enum.auto()
    """The capability negotiation callback was improperly executed.

    If a capability request's handler returns this status, or if it raises an
    exception, the bot will mark the request as errored. A handler can use this
    return value to inform the bot that something wrong happened, without being
    an error in the code itself.
    """


class CapabilityHandler(Protocol):
    """:class:`~typing.Protocol` definition for capability handler.

    When a plugin requests a capability, it can define a callback handler for
    that request using :class:`capability` as a decorator. That handler will be
    called upon Sopel receiving either an ``ACK`` (capability enabled) or a
    ``NAK`` (capability denied) CAP message.

    Example::

        from sopel import plugin
        from sopel.bot import SopelWrapper

        @plugin.capability('example/cap-name')
        def capability_handler(
            cap_req: tuple[str, ...],
            bot: SopelWrapper,
            acknowledged: bool,
        ) -> plugin.CapabilityNegotiation:
            if acknowledged:
                # do something if acknowledged
                # i.e.
                # activate a plugin's feature
                pass
            else:
                # do something else if not
                # i.e. use a fallback mechanism
                # or deactivate a plugin's feature if needed
                pass

            # always return if Sopel can send "CAP END" (DONE)
            # or if the plugin must notify the bot for that later (CONTINUE)
            return plugin.CapabilityNegotiation.DONE

    .. note::

        This protocol class should be used for type checking and documentation
        purposes only.

    """
    def __call__(
        self,
        cap_req: tuple[str, ...],
        bot: SopelWrapper,
        acknowledged: bool,
    ) -> CapabilityNegotiation:
        """A capability handler must be a callable with this signature.

        :param cap_req: the capability request, as a tuple of string
        :param bot: the bot instance
        :param acknowledged: that flag that tells if the capability is enabled
                             or denied
        :return: the return value indicates if the capability negotiation is
                 complete for this request or not
        """


class capability:
    """Decorate a function to request a capability and handle the result.

    :param name: name of the capability to negotiate with the server; this
                 positional argument can be used multiple times to form a
                 single ``CAP REQ``
    :param handler: optional keyword argument, acknowledgement handler

    The Client Capability Negotiation is a feature of IRCv3 that exposes a
    mechanism for a server to advertise a list of features and for clients to
    request them when they are available.

    This decorator will register a capability request, allowing the bot to
    request capabilities if they are available. You can request more than one
    at a time, which will make for one single request.

    The handler must follow the :class:`CapabilityHandler` protocol.

    .. note::

        Due to how Capability Negotiation works, a request will be acknowledged
        or denied all at once. This means that this may succeed::

            @plugin.capability('away-notify')

        But this may not::

            @plugin.capability('away-notify', 'example/incompatible-cap')

        Even though the ``away-notify`` capability is available and can be
        enabled, the second ``CAP REQ`` will be denied because the server won't
        acknowledge a request that contains an incompatible capability.

        In that case, if you don't need both at the same time, you should use
        two different handlers::

            @plugin.capability('away-notify')
            def cap_away_notify(cap_req, bot, ack):
                # handle away-notify acknowledgement

            @plugin.capability('example/incompatible-cap')
            def cap_example_incompatible_cap(cap_req, bot, ack):
                # handle example/incompatible-cap acknowledgement
                # or, most probably, lack thereof

        This will allow the server to acknowledge or deny each capability
        independently.

    .. warning::

        A function cannot be decorated more than once by this decorator, as
        the result is an instance of :class:`capability`.

        If you want to handle a ``CAP`` message without requesting the
        capability, you should use the :func:`event` decorator instead.

    .. warning::

        The list of ``cap_req`` is limited in size to prevent the bot from
        separating the ``CAP REQ`` in multiple lines as the bot does not know
        how to call back the capability handler upon receiving the multi-line
        ``ACK * REQ``.

    .. seealso::

        The IRCv3 specification on `Client Capability Negotiation`__.

    .. __: https://ircv3.net/specs/extensions/capability-negotiation
    """
    def __init__(
        self,
        *cap_req: str,
        handler: Optional[CapabilityHandler] = None,
    ) -> None:
        cap_req_text = ' '.join(cap_req)
        if len(cap_req_text.encode('utf-8')) > 500:
            # "CAP * ACK " is 10 bytes, leaving 500 bytes for the capabilities.
            # Sopel cannot allow multi-line requests, as it won't know how to
            # deal properly with multi-line ACK.
            # The spec says a client SHOULD send multiple requests; however
            # the spec also says that a server will ACK or NAK a whole request
            # at once. So technically, multiple REQs are not the same as a
            # single REQ.
            raise ValueError('Capability request too long: %s' % cap_req_text)

        self._cap_req: tuple[str, ...] = tuple(sorted(cap_req))
        self._handler: Optional[CapabilityHandler] = handler

    def __str__(self) -> str:
        caps = ", ".join(repr(cap) for cap in self._cap_req)
        handler = ""
        if self._handler and hasattr(self._handler, "__name__"):
            handler = " ({}())".format(self._handler.__name__)
        return "<capability {}{}>".format(caps, handler)

    @property
    def cap_req(self) -> tuple[str, ...]:
        """Capability request as a sorted tuple.

        This is the capability request that will be sent to the server as is.
        A request is acknowledged or denied for all the capabilities it
        contains, so the request ``(example/cap1, example/cap2)`` is not the
        same as two requests, one for ``example/cap1`` and the other for
        ``example/cap2``. This makes each request unique.
        """
        return self._cap_req

    def callback(
        self,
        bot: SopelWrapper,
        acknowledged: bool,
    ) -> tuple[bool, Optional[CapabilityNegotiation]]:
        """Execute the acknowlegement callback of a capability request.

        :param bot: a Sopel instance
        :param acknowledged: tell if the capability request is acknowledged
                             (``True``) or deny (``False``)
        :return: a 2-value tuple that contains if the request is done and the
                 result of the handler (if any)

        It executes the handler when the capability request receives an
        acknowledgement (either positive or negative), and returns the result.
        The handler's return value is used to know if the capability
        request is done, or if the bot must wait for resolution from the plugin
        that requested the capability.

        This method returns a 2-value tuple:

        * the first value tells if the negotiation is done for this request
        * the second is the handler's return value (if any)

        If no handler is registered, this automatically returns
        ``(True, None)``, as the negotiation is considered done (without any
        result).

        This doesn't prevent the handler from raising an exception.
        """
        result: Optional[CapabilityNegotiation] = None
        if self._handler is not None:
            result = self._handler(self.cap_req, bot, acknowledged)
            LOGGER.debug(
                'Cap request "%s" got "%s", '
                'executed successfuly with status: %s',
                ' '.join(self.cap_req),
                'ACK' if acknowledged else 'NAK',
                result.name,
            )
        return (result is None or result == CapabilityNegotiation.DONE, result)

    def __call__(
        self,
        handler: CapabilityHandler,
    ) -> capability:
        """Register a capability negotiation callback."""
        if self._handler is not None:
            raise RuntimeError("Cannot re-use capability decorator")
        self._handler = handler
        return self


def unblockable(
    function: Optional[Callable] = None,
) -> Callable:
    """Decorate a function to exempt it from Sopel's ignore system.

    For example, this can be used to ensure that important events such as
    ``JOIN`` are always recorded even if the user's nickname or hostname is
    :ref:`ignored <Ignoring Users>`::

        from sopel import plugin

        @plugin.event('JOIN')
        @plugin.unblockable
        def on_join_callable(bot, trigger):
            # do something when a user JOINs a channel
            # a blocked nickname or hostname *will* trigger this
            pass

    .. seealso::

        Sopel's :meth:`~sopel.bot.Sopel.dispatch` method.

    """
    def add_attribute(function):
        function.unblockable = True
        return function

    # hack to allow both @unblockable and @unblockable() to work
    if callable(function):
        return add_attribute(function)
    return add_attribute


def interval(*intervals: Union[int, float]) -> Callable:
    """Decorate a function to be called by the bot every *n* seconds.

    :param intervals: one or more duration(s), in seconds

    This decorator can be used multiple times for multiple intervals, or
    multiple intervals can be given in multiple arguments. The first time the
    function will be called is *n* seconds after the bot was started.

    Plugin functions decorated by ``interval`` must only take
    :class:`bot <sopel.bot.Sopel>` as their argument; they do not get a ``trigger``.
    The ``bot`` argument will not have a context, so functions like
    ``bot.say()`` will not have a default destination.

    There is no guarantee that the bot is connected to a server or in any
    channels when the function is called, so care must be taken.

    Example::

        from sopel import plugin

        @plugin.interval(5)
        def spam_every_5s(bot):
            if "#here" in bot.channels:
                bot.say("It has been five seconds!", "#here")

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, "interval"):
            function.interval = []
        for arg in intervals:
            if arg not in function.interval:
                function.interval.append(arg)
        return function

    return add_attribute


def rule(*patterns: Union[str, Pattern]) -> Callable:
    """Decorate a function to be called when a line matches the given pattern.

    :param patterns: one or more regular expression(s)

    Each argument is a regular expression which will trigger the function::

        @rule('hello', 'how')
            # will trigger once on "how are you?"
            # will trigger once on "hello, what's up?"

    This decorator can be used multiple times to add more rules::

        @rule('how')
        @rule('hello')
            # will trigger once on "how are you?"
            # will trigger once on "hello, what's up?"

    If the Sopel instance is in a channel, or sent a ``PRIVMSG``, where a
    string matching this expression is said, the function will execute. Note
    that captured groups here will be retrievable through the
    :class:`~sopel.trigger.Trigger` object later.

    Inside the regular expression, some special directives can be used.
    ``$nick`` will be replaced with the nick of the bot and ``,`` or ``:``, and
    ``$nickname`` will be replaced with the nick of the bot.

    .. versionchanged:: 7.0

        The :func:`rule` decorator can be called with multiple positional
        arguments, each used to add a rule. This is equivalent to decorating
        the same function multiple times with this decorator.

    .. note::

        The regex rule will match only once per line, starting at the beginning
        of the line only.

        To match for each time an expression is found, use the :func:`find`
        decorator instead. To match only once from anywhere in the line,
        use the :func:`search` decorator instead.

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, "rule"):
            function.rule = []
        for value in patterns:
            if value not in function.rule:
                function.rule.append(value)
        return function

    return add_attribute


def rule_lazy(*loaders: Callable) -> Callable:
    """Decorate a callable as a rule with lazy loading.

    :param loaders: one or more functions to generate a list of **compiled**
                    regexes to match URLs

    Each ``loader`` function must accept a ``settings`` parameter and return a
    list (or tuple) of **compiled** regular expressions::

        import re

        def loader(settings):
            return [re.compile(r'<your_rule_pattern>')]

    It will be called by Sopel when the bot parses the plugin to register rules
    to get its regexes. The ``settings`` argument will be the bot's
    :class:`sopel.config.Config` object.

    If any of the ``loader`` functions raises a
    :exc:`~sopel.plugins.exceptions.PluginError` exception, the rule will be
    ignored; it will not fail the plugin's loading.

    The decorated function will behave like any other :func:`callable`::

        from sopel import plugin

        @plugin.rule_lazy(loader)
        def my_rule_handler(bot, trigger):
            bot.say('Rule triggered by: %s' % trigger.group(0))

    .. versionadded:: 7.1

    .. seealso::

        When more than one loader is provided, they will be chained together
        with the :func:`sopel.tools.chain_loaders` function.

    """
    def decorator(function):
        function._sopel_callable = True
        if not hasattr(function, 'rule_lazy_loaders'):
            function.rule_lazy_loaders = []
        function.rule_lazy_loaders.extend(loaders)
        return function
    return decorator


def find(*patterns: Union[str, Pattern]) -> Callable:
    """Decorate a function to be called for each time a pattern is found in a line.

    :param patterns: one or more regular expression(s)

    Each argument is a regular expression which will trigger the function::

        @find('hello', 'here')
            # will trigger once on "hello you"
            # will trigger twice on "hello here"
            # will trigger once on "I'm right here!"

    This decorator can be used multiple times to add more rules::

        @find('here')
        @find('hello')
            # will trigger once on "hello you"
            # will trigger twice on "hello here"
            # will trigger once on "I'm right here!"

    If the Sopel instance is in a channel, or sent a ``PRIVMSG``, the function
    will execute for each time a received message matches an expression. Each
    match will also contain the position of the instance it found.

    Inside the regular expression, some special directives can be used.
    ``$nick`` will be replaced with the nick of the bot and ``,`` or ``:``, and
    ``$nickname`` will be replaced with the nick of the bot::

        @find('$nickname')
            # will trigger for each time the bot's nick is in a trigger

    .. versionadded:: 7.1

    .. note::

        The regex rule will match once for each non-overlapping match, from left
        to right, and the function will execute for each of these matches.

        To match only once from anywhere in the line, use the :func:`search`
        decorator instead. To match only once from the start of the line,
        use the :func:`rule` decorator instead.

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, "find_rules"):
            function.find_rules = []
        for value in patterns:
            if value not in function.find_rules:
                function.find_rules.append(value)
        return function

    return add_attribute


def find_lazy(*loaders: Callable) -> Callable:
    """Decorate a callable as a find rule with lazy loading.

    :param loaders: one or more functions to generate a list of **compiled**
                    regexes to match patterns in a line

    Each ``loader`` function must accept a ``settings`` parameter and return a
    list (or tuple) of **compiled** regular expressions::

        import re

        def loader(settings):
            return [re.compile(r'<your_rule_pattern>')]

    It will be called by Sopel when the bot parses the plugin to register the
    find rules to get its regexes. The ``settings`` argument will be the bot's
    :class:`sopel.config.Config` object.

    If any of the ``loader`` functions raises a
    :exc:`~sopel.plugins.exceptions.PluginError` exception, the find rule will
    be ignored; it will not fail the plugin's loading.

    The decorated function will behave like any other :func:`callable`::

        from sopel import plugin

        @plugin.find_lazy(loader)
        def my_find_rule_handler(bot, trigger):
            bot.say('Rule triggered by: %s' % trigger.group(0))

    .. versionadded:: 7.1

    .. seealso::

        When more than one loader is provided, they will be chained together
        with the :func:`sopel.tools.chain_loaders` function.

    """
    def decorator(function):
        function._sopel_callable = True
        if not hasattr(function, 'find_rules_lazy_loaders'):
            function.find_rules_lazy_loaders = []
        function.find_rules_lazy_loaders.extend(loaders)
        return function
    return decorator


def search(*patterns: Union[str, Pattern]) -> Callable:
    """Decorate a function to be called when a pattern matches anywhere in a line.

    :param patterns: one or more regular expression(s)

    Each argument is a regular expression which will trigger the function::

        @search('hello', 'here')
            # will trigger once on "hello you"
            # will trigger twice on "hello here"
            # will trigger once on "I'm right here!"

    This decorator can be used multiple times to add more search rules::

        @search('here')
        @search('hello')
            # will trigger once on "hello you"
            # will trigger twice on "hello here" (once per expression)
            # will trigger once on "I'm right here!"

    If the Sopel instance is in a channel, or sent a PRIVMSG, where a part
    of a string matching this expression is said, the function will execute.
    Note that captured groups here will be retrievable through the
    :class:`~sopel.trigger.Trigger` object later. The match will also contain
    the position of the first instance found.

    Inside the regular expression, some special directives can be used.
    ``$nick`` will be replaced with the nick of the bot and ``,`` or ``:``, and
    ``$nickname`` will be replaced with the nick of the bot::

        @search('$nickname')
            # will trigger once when the bot's nick is in a trigger

    .. versionadded:: 7.1

    .. note::

        The regex rule will match for the first instance only, starting from
        the left of the line, and the function will execute only once per
        regular expression.

        To match for each time an expression is found, use the :func:`find`
        decorator instead. To match only once from the start of the line,
        use the :func:`rule` decorator instead.

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, "search_rules"):
            function.search_rules = []
        for value in patterns:
            if value not in function.search_rules:
                function.search_rules.append(value)
        return function

    return add_attribute


def search_lazy(*loaders: Callable) -> Callable:
    """Decorate a callable as a search rule with lazy loading.

    :param loaders: one or more functions to generate a list of **compiled**
                    regexes to match patterns in a line

    Each ``loader`` function must accept a ``settings`` parameter and return a
    list (or tuple) of **compiled** regular expressions::

        import re

        def loader(settings):
            return [re.compile(r'<your_rule_pattern>')]

    It will be called by Sopel when the bot parses the plugin to register the
    search rules to get its regexes. The ``settings`` argument will be the
    bot's :class:`sopel.config.Config` object.

    If any of the ``loader`` functions raises a
    :exc:`~sopel.plugins.exceptions.PluginError` exception, the find rule will
    be ignored; it will not fail the plugin's loading.

    The decorated function will behave like any other :func:`callable`::

        from sopel import plugin

        @plugin.search_lazy(loader)
        def my_search_rule_handler(bot, trigger):
            bot.say('Rule triggered by: %s' % trigger.group(0))

    .. versionadded:: 7.1

    .. seealso::

        When more than one loader is provided, they will be chained together
        with the :func:`sopel.tools.chain_loaders` function.

    """
    def decorator(function):
        function._sopel_callable = True
        if not hasattr(function, 'search_rules_lazy_loaders'):
            function.search_rules_lazy_loaders = []
        function.search_rules_lazy_loaders.extend(loaders)
        return function
    return decorator


def thread(value: bool) -> Callable:
    """Decorate a function to specify if it should be run in a separate thread.

    :param value: if ``True``, the function is called in a separate thread;
                  otherwise, from the bot's main thread

    Functions run in a separate thread (as is the default) will not prevent the
    bot from executing other functions at the same time. Functions not run in a
    separate thread may be started while other functions are still running, but
    additional functions will not start until it is completed.
    """
    threaded = bool(value)

    def add_attribute(function):
        function.thread = threaded
        return function

    return add_attribute


def allow_bots(
    function: Optional[Callable] = None,
) -> Callable:
    """Decorate a function to specify that it should receive events from bots.

    On networks implementing the `Bot Mode specification`__, messages and
    other events from other clients that have identified themselves as bots
    will be tagged as such, and Sopel will ignore them by default. This
    decorator allows a function to opt into receiving these events.

    .. __: https://ircv3.net/specs/extensions/bot-mode
    """
    def add_attribute(function):
        function.allow_bots = True
        return function

    # hack to allow both @allow_bots and @allow_bots() to work
    if callable(function):
        return add_attribute(function)
    return add_attribute


def echo(
    function: Optional[Callable] = None,
) -> Callable:
    """Decorate a function to specify that it should receive echo messages.

    This decorator can be used to listen in on the messages that Sopel is
    sending and react accordingly.

    .. important::

        The decorated callable will receive *all* matching messages that Sopel
        sends, including output from the same callable. Take care to avoid
        creating feedback loops when using this feature.

    """
    def add_attribute(function):
        function.echo = True
        return function

    # hack to allow both @echo and @echo() to work
    if callable(function):
        return add_attribute(function)
    return add_attribute


def command(*command_list: str) -> Callable:
    """Decorate a function to set one or more commands that should trigger it.

    :param command_list: one or more command name(s) to match

    This decorator can be used to add multiple commands to one callable in a
    single line. The resulting match object will have the command as the first
    group; the rest of the line, excluding leading whitespace, as the second
    group; and parameters 1 through 4, separated by whitespace, as groups 3-6.

    Example::

        @command("hello")
            # If the command prefix is "\\.", this would trigger on lines
            # starting with ".hello".

        @command('j', 'join')
            # If the command prefix is "\\.", this would trigger on lines
            # starting with either ".j" or ".join".

    You can use a space in the command name to implement subcommands::

        @command('main sub1', 'main sub2')
            # For ".main sub1", trigger.group(1) will return "main sub1"
            # For ".main sub2", trigger.group(1) will return "main sub2"

    But in that case, be careful with the order of the names: if a more generic
    pattern is defined first, it will have priority over less generic patterns.
    So for instance, to have ``.main`` and ``.main sub`` working properly, you
    need to declare them like this::

        @command('main sub', 'main')
            # This command will react properly to ".main sub" and ".main"

    Then, you can check ``trigger.group(1)`` to know if it was used as
    ``main sub`` or just ``main`` in your callable. If you declare them in the
    wrong order, ``.main`` will have priority and you won't be able to take
    advantage of that.

    Another option is to declare command with subcommands only, like this::

        @command('main sub1')
            # this command will be triggered on .main sub1

        @command('main sub2')
            # this other command will be triggered on .main sub2

    In that case, ``.main`` won't trigger anything, and you won't have to
    inspect the trigger's groups to know which subcommand is triggered.

    .. note::

        If you use this decorator multiple times, remember that the decorators
        are invoked in the reverse order of appearance::

            # These two decorators...
            @command('hi')
            @command('hello')

            # ...are equivalent to this single decorator
            @command('hello', 'hi')

        See also the `Function Definitions`__ chapter from the Python
        documentation for more information about functions and decorators.

        .. __: https://docs.python.org/3/reference/compound_stmts.html#function-definitions

    .. note::

        The command name will be escaped for use in a regular expression.
        As such it is not possible to use something like ``.command\\d+`` to
        catch something like ``.command1`` or ``.command2``.

        You have several options at your disposal to replace a regex in the
        command name:

        * use a command alias
        * parse the arguments with your own regex within your plugin callable
        * use a :func:`rule` instead

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, "commands"):
            function.commands = []
        for command in command_list:
            if command not in function.commands:
                function.commands.append(command)
        return function
    return add_attribute


commands = command
"""Alias to :func:`command`."""


def nickname_command(*command_list: str) -> Callable:
    """Decorate a function to trigger on lines starting with "$nickname: command".

    :param command_list: one or more command name(s) to match

    This decorator can be used to add multiple commands to one callable in a
    single line. The resulting match object will have the command as the first
    group; the rest of the line, excluding leading whitespace, as the second
    group; and parameters 1 through 4, separated by whitespace, as groups 3-6.

    Example::

        @nickname_command("hello!")
            # Would trigger on "$nickname: hello!", "$nickname,   hello!",
            # "$nickname hello!", "$nickname hello! parameter1" and
            # "$nickname hello! p1 p2 p3 p4 p5 p6 p7 p8 p9".

    .. note::

        The command name will be escaped to be used in a regex command. As such
        it is not possible to use something like ``command\\d+`` to catch
        something like ``Bot: command1`` or ``Bot: command2``.

        You have several options at your disposal to replace a regex in the
        command name:

        * use a command alias
        * parse the arguments with your own regex within your plugin callable
        * use a :func:`rule`

        The :func:`rule` can be used with a ``$nick`` variable::

            @rule(r'$nick .*')
                # Would trigger on anything starting with "$nickname[:,]? ",
                # and would never have any additional parameters, as the
                # command would match the rest of the line.

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, 'nickname_commands'):
            function.nickname_commands = []
        for cmd in command_list:
            if cmd not in function.nickname_commands:
                function.nickname_commands.append(cmd)
        return function
    return add_attribute


nickname_commands = nickname_command
"""Alias to :func:`nickname_command`."""


def action_command(*command_list: str) -> Callable:
    """Decorate a function to trigger on CTCP ACTION lines.

    :param command_list: one or more command name(s) to match

    This decorator can be used to add multiple commands to one callable in a
    single line. The resulting match object will have the command as the first
    group; the rest of the line, excluding leading whitespace, as the second
    group; and parameters 1 through 4, separated by whitespace, as groups 3-6.

    Example::

        @action_command("hello!")
            # Would trigger on "/me hello!"

    .. versionadded:: 7.0

    .. note::

        The command name will be escaped for use in a regular expression.
        As such it is not possible to use something like ``/me command\\d+``
        to catch something like ``/me command1`` or ``/me command2``.

        You have several options at your disposal to replace a regex in the
        command name:

        * use a command alias
        * parse the arguments with your own regex within your plugin callable
        * use a :func:`rule`

        The :func:`rule` must be used with the :func:`ctcp` decorator::

            @rule(r'hello!?')
            @ctcp('ACTION')
                # Would trigger on "/me hello!" and "/me hello"

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, 'action_commands'):
            function.action_commands = []
        for cmd in command_list:
            if cmd not in function.action_commands:
                function.action_commands.append(cmd)
        return function
    return add_attribute


action_commands = action_command
"""Alias to :func:`action_command`."""


def label(value: str) -> Callable:
    """Decorate a function to add a rule label.

    :param value: a label for the rule

    The rule label allows the documentation and the logging system to refer
    to this function by its label. A function can have one and only one label::

        @label('on_hello')
        @rule('hello')
            # will trigger on hello, and be labelled as "on_hello"

    .. note::

        By default, the "label" of a callable will be its function name, which
        can be confusing for end-users: the goal of the ``label`` decorator is
        to make generic rules as user-friendly as commands are, by giving them
        some name that isn't tied to an identifier in the source code.

    """
    def add_attribute(function):
        function.rule_label = value
        return function
    return add_attribute


def priority(value: Literal['low', 'medium', 'high']) -> Callable:
    """Decorate a function to be executed with higher or lower priority.

    :param value: one of ``high``, ``medium``, or ``low``

    The priority allows you some control over the order of callable execution,
    if your plugin needs it. If a callable does not specify its ``priority``,
    Sopel assumes ``medium``.
    """
    def add_attribute(function):
        function.priority = value
        return function
    return add_attribute


def event(*event_list: str) -> Callable:
    """Decorate a function to be triggered on specific IRC events.

    :param event_list: one or more event name(s) on which to trigger

    This is one of a number of events, such as 'JOIN', 'PART', 'QUIT', etc.
    (More details can be found in RFC 1459.) When the Sopel bot is sent one of
    these events, the function will execute. Note that the default
    :meth:`rule` (``.*``) will match *any* line of the correct event type(s).
    If any rule is explicitly specified, it overrides the default.

    .. seealso::

        :class:`sopel.tools.events` provides human-readable names for many of the
        numeric events, which may help your code be clearer.

    """
    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, "event"):
            function.event = []
        for name in event_list:
            if name not in function.event:
                function.event.append(name)
        return function
    return add_attribute


def ctcp(
    function: Union[Callable, Optional[str]] = None,
    *command_list: str,
) -> Callable:
    """Decorate a callable to trigger on CTCP commands (mostly, ``ACTION``).

    :param command_list: one or more CTCP command(s) on which to trigger

    There are `various CTCP commands`__ to handle with this decorator, such as
    ``ACTION``, ``CLIENTINFO``, ``TIME``, and ``VERSION``::

        from sopel import plugin

        @plugin.ctcp('TIME')
        @plugin.rule('.*')
        def ctcp_time(bot, trigger):
            bot.say('Sorry, not a clock.')

    This decorator also works without parentheses, in which case it will trigger
    on CTCP ``ACTION``::

        from sopel import plugin

        @plugin.ctcp
        @plugin.rule('.*')
        def ctcp_action(bot, trigger):
            bot.reply('Why would you do that?!')

    .. versionadded:: 7.1

        This is now ``ctcp`` instead of ``intent``, and it can be called
        without argument, in which case it will assume ``ACTION``.

    .. note::

        This used to be ``@intent``, for a long dead feature in the IRCv3 spec.
        It is now replaced by ``@ctcp``, which can be used without arguments.
        In that case, Sopel will assume it should trigger on ``ACTION``.

        As ``sopel.module`` will be removed in Sopel 9, so will ``@intent``.

    .. __: https://datatracker.ietf.org/doc/html/draft-oakley-irc-ctcp-02#appendix-A
    """
    default_commands = ('ACTION',) + command_list
    if function is None:
        return ctcp(*default_commands)  # called as ``@ctcp()``
    elif callable(function):
        # called as ``@ctcp`` or ``@ctcp(function)``
        # or even ``@ctcp(function, 'ACTION', ...)``
        return ctcp(*default_commands)(function)

    # function is not None, and it is not a callable
    # called as ``@ctcp('ACTION', ...)``
    ctcp_commands = (function,) + command_list

    def add_attribute(function):
        function._sopel_callable = True
        if not hasattr(function, "ctcp"):
            function.ctcp = []
        for name in ctcp_commands:
            if name not in function.ctcp:
                function.ctcp.append(name)
        return function
    return add_attribute


def rate(
    user: int = 0,
    channel: int = 0,
    server: int = 0,
    *,
    message: Optional[str] = None,
    include_admins: Optional[bool] = False,
) -> Callable:
    """Decorate a function to be rate-limited.

    :param user: seconds between permitted calls of this function by the same
                 user
    :param channel: seconds between permitted calls of this function in the
                    same channel, regardless of triggering user
    :param server: seconds between permitted calls of this function no matter
                   who triggered it or where
    :param message: optional keyword argument; default message sent as NOTICE
                    when a rate limit is reached
    :param include_admins: optional boolean to include admins in the rate limit
                           (default ``False``)

    How often a function can be triggered on a per-user basis, in a channel,
    or across the server (bot) can be controlled with this decorator. A value
    of ``0`` means no limit. If a function is given a rate of 20, that
    function may only be used once every 20 seconds in the scope corresponding
    to the parameter::

        from sopel import plugin

        @plugin.rate(10)
            # won't trigger if used more than once per 10s by a user

        @plugin.rate(10, 10)
            # won't trigger if used more than once per 10s by a user/channel

        @plugin.rate(10, 10, 2)
            # won't trigger if used more than once per 10s by a user/channel
            # and never more than once every 2s

    If a ``message`` is provided, it will be used as the default message sent
    as a ``NOTICE`` to the user who hit the rate limit::

        @rate(10, 10, 10, message='Hit the rate limit for this function.')
            # will send a NOTICE

    The message can contain placeholders which will be filled in:

    * ``nick``: the nick that hit the rate limit
    * ``channel``: the channel in which the rate limit was hit (will be
      ``'private-message'`` for private messages)
    * ``sender``: the sender (nick or channel) of the message which hit
      the rate limit
    * ``plugin``: the name of the plugin that hit the rate limit
    * ``label``: the label of the plugin handler that hit the rate limit
    * ``time_left``: the time remaining before the rate limit expires, as
      a string
    * ``time_left_sec``: the time remaining before the rate limit expires,
      expressed in number of seconds
    * ``rate_limit``: the rate limit, as a string
    * ``rate_limit_sec``: the rate limit, expressed in number of seconds
    * ``rate_limit_type``: the type of rate limit that was hit (one of
      ``user, group, global``)

    For example::

        @rate(10, 10, 2, message='Sorry {nick}, you hit the {rate_limit_type} rate limit!')

    .. versionchanged:: 8.0

        Optional keyword argument ``message`` was added in Sopel 8.

    .. note::

        Users on the admin list in Sopel's configuration are exempted from rate
        limits.

    .. seealso::

        You can control each rate limit separately, with their own custom
        message using :func:`rate_user`, :func:`rate_channel`, or
        :func:`rate_global`.

    """
    def add_attribute(function):
        if not hasattr(function, 'user_rate'):
            function.user_rate = user
        if not hasattr(function, 'channel_rate'):
            function.channel_rate = channel
        if not hasattr(function, 'global_rate'):
            function.global_rate = server
        function.default_rate_message = message
        function.rate_limit_admins = include_admins
        return function
    return add_attribute


def rate_user(
    rate: int,
    message: Optional[str] = None,
    include_admins: Optional[bool] = False,
) -> Callable:
    """Decorate a function to be rate-limited for a user.

    :param rate: seconds between permitted calls of this function by the same
                 user
    :param message: optional; message sent as NOTICE when a user hits the limit
    :param include_admins: optional boolean to include admins in the rate limit
                           (default ``False``)

    This decorator can be used alone or with the :func:`rate` decorator, as it
    will always take precedence::

        @rate(10, 10, 10)
        @rate_user(20, 'You hit your rate limit for this function.')
            # user limit will be set to 20, other to 10
            # will send a NOTICE only when a user hits their own limit
            # as other rate limits don't have any message set

    The message can contain the same placeholders supported by :func:`rate`::

        @rate_user(5, 'Sorry {nick}, you hit your {rate_limit_sec}s limit!')

    If you don't provide a message, the default message set by :func:`rate`
    (if any) will be used instead.

    .. versionadded:: 8.0

    .. note::

        Users on the admin list in Sopel's configuration are exempted from rate
        limits.

    """
    def add_attribute(function):
        function.user_rate = rate
        function.user_rate_message = message
        function.rate_limit_admins = include_admins
        return function
    return add_attribute


def rate_channel(
    rate: int,
    message: Optional[str] = None,
    include_admins: Optional[bool] = False,
) -> Callable:
    """Decorate a function to be rate-limited for a channel.

    :param rate: seconds between permitted calls of this function in the same
                 channel, regardless of triggering user
    :param message: optional; message sent as NOTICE when a user hits the limit
    :param include_admins: optional boolean to include admins in the rate limit
                           (default ``False``)

    This decorator can be used alone or with the :func:`rate` decorator, as it
    will always take precedence::

        @rate(10, 10, 10)
        @rate_channel(5, 'You hit the channel rate limit for this function.')
            # channel limit will be set to 5, other to 10
            # will send a NOTICE only when a user hits the channel limit
            # as other rate limits don't have any message set

    If you don't provide a message, the default message set by :func:`rate`
    (if any) will be used instead.

    The message can contain the same placeholders supported by :func:`rate`::

        @rate_channel(
            5,
            'Sorry {nick}, you hit the {rate_limit_sec}s limit for the {channel} channel!',
        )

    .. versionadded:: 8.0

    .. note::

        Users on the admin list in Sopel's configuration are exempted from rate
        limits.

    """
    def add_attribute(function):
        function.channel_rate = rate
        function.channel_rate_message = message
        function.rate_limit_admins = include_admins
        return function
    return add_attribute


def rate_global(
    rate: int,
    message: Optional[str] = None,
    include_admins: Optional[bool] = False,
) -> Callable:
    """Decorate a function to be rate-limited for the whole server.

    :param rate: seconds between permitted calls of this function no matter who
                 triggered it or where
    :param message: optional; message sent as NOTICE when a user hits the limit
    :param include_admins: optional boolean to include admins in the rate limit
                           (default ``False``)

    This decorator can be used alone or with the :func:`rate` decorator, as it
    will always take precedence.

    For example::

        @rate(10, 10, 10)
        @rate_global(5, 'You hit the global rate limit for this function.')
            # global limit will be set to 5, other to 10
            # will send a NOTICE only when a user hits the global limit
            # as other rate limits don't have any message set

    If you don't provide a message, the default message set by :func:`rate`
    (if any) will be used instead.

    The message can contain the same placeholders supported by :func:`rate`::

        @rate_global(5, 'Sorry {nick}, you hit the 5s limit!')

    .. versionadded:: 8.0

    .. note::

        Users on the admin list in Sopel's configuration are exempted from rate
        limits.

    """
    def add_attribute(function):
        function.global_rate = rate
        function.global_rate_message = message
        function.rate_limit_admins = include_admins
        return function
    return add_attribute


def require_privmsg(
    message: Union[Callable, Optional[str]] = None,
    reply: bool = False,
) -> Callable:
    """Decorate a function to only be triggerable from a private message.

    :param message: optional message said if triggered in a channel
    :param reply: use :meth:`~sopel.bot.Sopel.reply` instead of
                  :meth:`~sopel.bot.Sopel.say` when ``True``; defaults to
                  ``False``

    A decorated plugin callable will be triggered only by messages sent to the
    bot in private::

        from sopel import plugin

        @plugin.command('.shh')
        @plugin.require_privmsg('PM only command.')
        def confidential_command(bot, trigger):
            # trigger on private messages only

    If the decorated function is triggered by a channel message, the ``message``
    will be said if given. By default, it uses :meth:`bot.say()
    <.bot.Sopel.say>`, but when ``reply`` is ``True``, then it uses
    :meth:`bot.reply() <.bot.Sopel.reply>` instead.

    This decorator also works without parentheses, if you want its default (no
    arguments) behavior::

        from sopel import plugin

        @plugin.command('.shh')
        @plugin.require_privmsg
        def confidential_command(bot, trigger):
            # trigger on private messages only

    .. versionchanged:: 7.0
        Added the ``reply`` parameter.
    """
    def actual_decorator(function):
        @functools.wraps(function)
        def guarded(bot, trigger, *args, **kwargs):
            if trigger.is_privmsg:
                return function(bot, trigger, *args, **kwargs)
            else:
                if message and not callable(message):
                    if reply:
                        bot.reply(message)
                    else:
                        bot.say(message)
        return guarded

    # Hack to allow decorator without parens
    if callable(message):
        return actual_decorator(message)
    return actual_decorator


def require_chanmsg(
    message: Union[Callable, Optional[str]] = None,
    reply: bool = False,
) -> Callable:
    """Decorate a function to only be triggerable from a channel message.

    :param message: optional message said if triggered in private message
    :param reply: use :meth:`~.bot.Sopel.reply` instead of
                  :meth:`~.bot.Sopel.say` when ``True``; defaults to ``False``

    A decorated plugin callable will be triggered only by messages from a
    channel::

        from sopel import plugin

        @plugin.command('.mtopic')
        @plugin.require_chanmsg('Channel only command.')
        def manage_topic(bot, trigger):
            # trigger on channel messages only

    If the decorated function is triggered by a private message, the ``message``
    will be said if given. By default, it uses :meth:`bot.say()
    <.bot.Sopel.say>`, but when ``reply`` is ``True`` it uses
    :meth:`bot.reply() <.bot.Sopel.reply>` instead.

    This decorator also works without parentheses, if you want its default (no
    arguments) behavior::

        from sopel import plugin

        @plugin.command('.mtopic')
        @plugin.require_chanmsg
        def manage_topic(bot, trigger):
            # trigger on channel messages only

    .. versionchanged:: 7.0
        Added the ``reply`` parameter.
    """
    def actual_decorator(function):
        @functools.wraps(function)
        def guarded(bot, trigger, *args, **kwargs):
            if not trigger.is_privmsg:
                return function(bot, trigger, *args, **kwargs)
            else:
                if message and not callable(message):
                    if reply:
                        bot.reply(message)
                    else:
                        bot.say(message)
        return guarded

    # Hack to allow decorator without parens
    if callable(message):
        return actual_decorator(message)
    return actual_decorator


def require_account(
    message: Union[Callable, Optional[str]] = None,
    reply: bool = False,
) -> Callable:
    """Decorate a function to require services/NickServ authentication.

    :param message: optional message to say if a user without authentication
                    tries to trigger this function
    :param reply: use :meth:`~.bot.Sopel.reply` instead of
                  :meth:`~.bot.Sopel.say` when ``True``; defaults to ``False``

    A decorated plugin callable will be triggered only if the triggering user is
    logged into a network services account::

        from sopel import plugin

        @plugin.command('.regonly')
        @plugin.require_account('Registered users only.')
        def logged_in_command(bot, trigger):
            # trigger only if user is logged in to services

    If an unauthenticated user triggers the decorated function, the ``message``
    will be said if given. By default, it uses :meth:`bot.say()
    <.bot.Sopel.say>`, but when ``reply`` is ``True`` it uses :meth:`bot.reply()
    <.bot.Sopel.reply>` instead.

    This decorator also works without parentheses, if you want its default (no
    arguments) behavior::

        from sopel import plugin

        @plugin.command('.regonly')
        @plugin.require_account
        def logged_in_command(bot, trigger):
            # trigger only if user is logged in to services

    .. versionadded:: 7.0
    .. note::

        Only some networks support services authentication, and not all of
        those implement the standards required for clients like Sopel to
        determine authentication status. This decorator will block *all* use
        of functions it decorates on networks that lack the relevant features.

    .. seealso::

        The value of the :class:`trigger<.trigger.Trigger>`'s
        :attr:`account <.trigger.Trigger.account>` property determines whether
        this requirement is satisfied, and the property's documentation
        includes up-to-date details on what features a network must
        support to allow Sopel to fetch account information.

    """
    def actual_decorator(function):
        @functools.wraps(function)
        def guarded(bot, trigger, *args, **kwargs):
            if not trigger.account:
                if message and not callable(message):
                    if reply:
                        bot.reply(message)
                    else:
                        bot.say(message)
            else:
                return function(bot, trigger, *args, **kwargs)
        return guarded

    # Hack to allow decorator without parens
    if callable(message):
        return actual_decorator(message)

    return actual_decorator


def require_privilege(
    level: AccessLevel,
    message: Optional[str] = None,
    reply: bool = False,
) -> Callable:
    """Decorate a function to require at least the given channel permission.

    :param level: required privilege level to use this command
    :param message: optional message said to insufficiently privileged user
    :param reply: use :meth:`~.bot.Sopel.reply` instead of
                  :meth:`~.bot.Sopel.say` when ``True``; defaults to ``False``

    ``level`` can be one of the privilege level constants defined in this
    module. If the user does not have at least that privilege, the bot will say
    ``message`` if given. By default, it uses :meth:`bot.say()
    <.bot.Sopel.say>`, but when ``reply`` is ``True`` it uses :meth:`bot.reply()
    <.bot.Sopel.reply>` instead.

    Use of ``require_privilege()`` implies :func:`require_chanmsg`.

    .. versionchanged:: 7.0
        Added the ``reply`` parameter.

    .. versionchanged:: 8.0
        Decorated callables no longer run in response to private messages.
    """
    def actual_decorator(function):
        @functools.wraps(function)
        def guarded(bot, trigger, *args, **kwargs):
            # If this is a privmsg, do not trigger
            if trigger.is_privmsg:
                return
            channel_privs = bot.channels[trigger.sender].privileges
            allowed = channel_privs.get(trigger.nick, 0) >= level
            if not trigger.is_privmsg and not allowed:
                if message and not callable(message):
                    if reply:
                        bot.reply(message)
                    else:
                        bot.say(message)
            else:
                return function(bot, trigger, *args, **kwargs)
        return guarded
    return actual_decorator


def require_admin(
    message: Union[Callable, Optional[str]] = None,
    reply: bool = False,
) -> Callable:
    """Decorate a function to require the triggering user to be a bot admin.

    :param message: optional message said to non-admin user
    :param reply: use :meth:`~.bot.Sopel.reply` instead of
                  :meth:`~.bot.Sopel.say` when ``True``; defaults to ``False``

    A decorated plugin callable will be triggered only if the triggering user is
    an admin of the bot, according to its configuration::

        from sopel import plugin

        @plugin.command('.adminonly')
        @plugin.require_admin('Bot admin only command.')
        def admin_command(bot, trigger):
            # trigger only if user is a bot admin

    The bot's :attr:`~.config.core_section.CoreSection.owner` is also an admin.

    When the triggering user is not an admin, the command is not run, and the
    bot will say the ``message`` if given. By default, it uses :meth:`bot.say()
    <.bot.Sopel.say>`, but when ``reply`` is ``True`` it uses :meth:`bot.reply()
    <.bot.Sopel.reply>` instead.

    This decorator also works without parentheses, if you want its default (no
    arguments) behavior::

        from sopel import plugin

        @plugin.command('.adminonly')
        @plugin.require_admin
        def admin_command(bot, trigger):
            # trigger only if user is a bot admin

    .. versionchanged:: 7.0
        Added the ``reply`` parameter.
    """
    def actual_decorator(function):
        @functools.wraps(function)
        def guarded(bot, trigger, *args, **kwargs):
            if not trigger.admin:
                if message and not callable(message):
                    if reply:
                        bot.reply(message)
                    else:
                        bot.say(message)
            else:
                return function(bot, trigger, *args, **kwargs)
        return guarded

    # Hack to allow decorator without parens
    if callable(message):
        return actual_decorator(message)

    return actual_decorator


def require_owner(
    message: Union[Callable, Optional[str]] = None,
    reply: bool = False,
) -> Callable:
    """Decorate a function to require the triggering user to be the bot owner.

    :param message: optional message said to non-owner user
    :param reply: use :meth:`~.bot.Sopel.reply` instead of
                  :meth:`~.bot.Sopel.say` when ``True``; defaults to ``False``

    A decorated plugin callable will be triggered only if the triggering user is
    recognized as the bot's owner, according to its configuration::

        from sopel import plugin

        @plugin.command('.owneronly')
        @plugin.require_owner('Bot owner only command.')
        def owner_command(bot, trigger):
            # trigger only if user is the bot's owner

    When the triggering user is not the bot's owner, the command is not run,
    and the bot will say ``message`` if given. By default, it uses
    :meth:`bot.say() <.bot.Sopel.say>`, but when ``reply`` is ``True`` it uses
    :meth:`bot.reply() <.bot.Sopel.reply>` instead.

    This decorator also works without parentheses, if you want its default (no
    arguments) behavior::

        from sopel import plugin

        @plugin.command('.owneronly')
        @plugin.require_owner
        def owner_command(bot, trigger):
            # trigger only if user is the bot's owner

    .. versionchanged:: 7.0
        Added the ``reply`` parameter.
    """
    def actual_decorator(function):
        @functools.wraps(function)
        def guarded(bot, trigger, *args, **kwargs):
            if not trigger.owner:
                if message and not callable(message):
                    if reply:
                        bot.reply(message)
                    else:
                        bot.say(message)
            else:
                return function(bot, trigger, *args, **kwargs)
        return guarded

    # Hack to allow decorator without parens
    if callable(message):
        return actual_decorator(message)
    return actual_decorator


def require_bot_privilege(
    level: AccessLevel,
    message: Optional[str] = None,
    reply: bool = False,
) -> Callable:
    """Decorate a function to require a minimum channel privilege for the bot.

    :param level: minimum channel privilege the bot needs for this function
    :param message: optional message said if the bot's channel privilege level
                    is insufficient
    :param reply: use :meth:`~.bot.Sopel.reply` instead of
                  :meth:`~.bot.Sopel.say` when ``True``; defaults to ``False``

    ``level`` can be one of the privilege level constants defined in this
    module. If the bot does not have the privilege, the bot will say
    ``message`` if given. By default, it uses :meth:`bot.say()
    <.bot.Sopel.say>`, but when ``reply`` is ``True`` it uses :meth:`bot.reply()
    <.bot.Sopel.reply>` instead.

    Use of ``require_bot_privilege()`` implies :func:`require_chanmsg`.

    .. versionadded:: 7.1
    .. versionchanged:: 8.0
        Decorated callables no longer run in response to private messages.
    """
    def actual_decorator(function):
        @functools.wraps(function)
        def guarded(bot, trigger, *args, **kwargs):
            # If this is a privmsg, do not trigger
            if trigger.is_privmsg:
                return

            if not bot.has_channel_privilege(trigger.sender, level):
                if message and not callable(message):
                    if reply:
                        bot.reply(message)
                    else:
                        bot.say(message)
            else:
                return function(bot, trigger, *args, **kwargs)
        return guarded
    return actual_decorator


def url(*url_rules: str) -> Callable:
    """Decorate a function to handle URLs.

    :param url_rules: one or more regex pattern(s) to match URLs

    This decorator takes a regex string that will be matched against URLs in a
    message. The function it decorates is like any other callable::

        from sopel import plugin

        @plugin.url(r'https://example.com/bugs/([a-z0-9]+)')
        @plugin.url(r'https://short.com/([a-z0-9]+)')
        def handle_example_bugs(bot, trigger):
            bot.reply('Found bug ID #%s' % trigger.group(1))

    The ``bot`` is an instance of :class:`~sopel.bot.SopelWrapper`, and
    ``trigger`` is the usual :class:`~sopel.trigger.Trigger` object.

    Under the hood, when Sopel collects the decorated handler it uses an
    instance of :class:`sopel.plugins.rules.URLCallback` to register it to its
    :attr:`rules manager <sopel.bot.Sopel.rules>` and its
    :meth:`~sopel.plugins.rules.Manager.register_url_callback` method.

    .. versionchanged:: 7.0

        The same function can be decorated multiple times with :func:`url`
        to register different URL patterns.

    .. versionchanged:: 7.0

        More than one pattern can be provided as positional argument at once.

    .. versionchanged:: 7.1

        The ``match`` parameter is obsolete and can be omitted. When present
        however, it represents the same match as the ``trigger`` argument.

        This behavior will be kept for backward compatibility and will be
        removed in Sopel 9.

    .. seealso::

        To detect URLs, Sopel uses a matching pattern built from a list of URL
        schemes, configured by
        :attr:`~sopel.config.core_section.CoreSection.auto_url_schemes`.

    """
    def actual_decorator(function):
        function._sopel_callable = True
        if not hasattr(function, 'url_regex'):
            function.url_regex = []
        for url_rule in url_rules:
            url_regex = re.compile(url_rule)
            if url_regex not in function.url_regex:
                function.url_regex.append(url_regex)
        return function
    return actual_decorator


def url_lazy(*loaders: Callable) -> Callable:
    """Decorate a function to handle URL, using lazy-loading for its regex.

    :param loaders: one or more functions to generate a list of **compiled**
                    regexes to match URLs.

    Each ``loader`` function must accept a ``settings`` parameter and return a
    list (or tuple) of **compiled** regular expressions::

        import re

        def loader(settings):
            return [re.compile(r'<your_url_pattern>')]

    It will be called by Sopel when the bot parses the plugin to register URL
    callbacks to get its regexes. The ``settings`` argument will be the bot's
    :class:`sopel.config.Config` object.

    If any of the ``loader`` functions raises a
    :exc:`~sopel.plugins.exceptions.PluginError` exception, the URL callback
    will be ignored; it will not fail the plugin's loading.

    The decorated function will behave like any other :func:`callable`::

        from sopel import plugin

        @plugin.url_lazy(loader)
        def my_url_handler(bot, trigger):
            bot.say('URL found: %s' % trigger.group(0))

    .. versionadded:: 7.1
    .. seealso::

        When more than one loader is provided, they will be chained together
        with the :func:`sopel.tools.chain_loaders` function.

    """
    def decorator(function):
        function._sopel_callable = True
        if not hasattr(function, 'url_lazy_loaders'):
            function.url_lazy_loaders = []
        function.url_lazy_loaders.extend(loaders)
        return function
    return decorator


class example:
    """Decorate a function with an example, and optionally test output.

    :param msg: the example command (required; see below)
    :param result: the command's expected output (optional; see below)
    :param privmsg: if ``True``, the example will be tested as if it was
                    received in a private message to the bot; otherwise,
                    in a channel (optional; default ``False``)
    :param admin: whether to treat the test message as having come from a
                  bot admin (optional; default ``False``)
    :param owner: whether to treat the test message as having come from
                  the bot's owner (optional; default ``False``)
    :param repeat: how many times to repeat the test; useful for commands
                   that return random results (optional; default ``1``)
    :param re: if ``True``, the ``result`` is interpreted as a regular
               expression and used to match the command's output
               (optional; see below)
    :param ignore: list of regular expression patterns to match ignored
                   output (optional; see below)
    :param user_help: whether this example should be included in
                      user-facing help output such as `.help command`
                      (optional; default ``False``; see below)
    :param online: if ``True``, |pytest|_ will mark this example as "online"
                   (optional; default ``False``; see below)
    :param vcr: if ``True``, this example's HTTP requests & responses will
                be recorded for later reuse (optional; default ``False``;
                see below)

    .. |pytest| replace:: ``pytest``
    .. _pytest: https://pypi.org/project/pytest/

    For compatibility with the built-in help plugin, ``msg`` must use the
    default :attr:`~sopel.config.core_section.CoreSection.help_prefix` if it
    is a prefixed command. Other command types should give example invocations
    that work with Sopel's default settings, especially if using the "example
    test" functionality to automatically generate a test(s) for the function.

    The presence of a ``result`` will generate tests automatically when Sopel's
    test suite is run, using ``msg`` as input. The exact behavior of the tests
    depends on the remaining optional ``example`` arguments.

    Passing ``re=True``, in particular, is useful for matching ``result``\\s
    that are random and/or dependent on an external API. This way, an example
    test can check the format of the result without caring about the exact data.

    Giving a list of ``ignore``d patterns is helpful for commands that may
    return intermittent errors (mostly calls to an external API that isn't
    necessarily stable), especially when coupled with the ``repeat`` parameter.

    By default, Sopel's help plugin will display only one example (the one
    closest to the function's `def` statement, due to how decorators work). You
    can override this choice or include multiple examples by passing
    ``user_help=True`` to one or more ``example`` decorator(s).

    Passing ``online=True`` makes that particular example skippable if Sopel's
    test suite is run in offline mode, which is mostly useful to make life
    easier for other developers working on Sopel without Internet access.

    Finally, ``vcr=True`` records the example's HTTP requests and responses for
    replaying during later test runs. It can be an alternative (or complement)
    to ``online``, and is especially useful for testing plugin code that calls
    on inconsistent or flaky remote APIs. The recorded "cassettes" of responses
    can be committed alongside the code for use by CI services, etc. (See
    `VCR.py <https://github.com/kevin1024/vcrpy>`_ & `pytest-vcr
    <https://github.com/ktosiek/pytest-vcr>`_)
    """
    def __init__(
        self,
        msg: str,
        result: Optional[Union[str, Iterable[str]]] = None,
        privmsg: bool = False,
        admin: bool = False,
        owner: bool = False,
        repeat: int = 1,
        re: bool = False,
        ignore: Optional[Union[str, Iterable[str]]] = None,
        user_help: bool = False,
        online: bool = False,
        vcr: bool = False,
    ):
        # Wrap result into a list for get_example_test
        self.result: Optional[list[str]] = None
        if isinstance(result, str):
            self.result = [result]
        elif result is not None:
            self.result = list(result)

        self.use_re = re
        self.msg = msg
        self.privmsg = privmsg
        self.admin = admin
        self.owner = owner
        self.repeat = repeat
        self.online = online
        self.vcr = vcr

        self.ignore: list[str] = []
        if isinstance(ignore, str):
            self.ignore = [ignore]
        elif ignore is not None:
            self.ignore = list(ignore)

        self.user_help = user_help

    def __call__(self, func):
        # mypy (as of v1.4) doesn't recognize the below check as adding an
        # "example" attribute to `func` if it's missing, so the `func`
        # argument isn't typed yet.
        # When we're ready to type-hint `loader`, we can make a TypeVar like
        # `Callable[[SopelWrapper, Trigger], Any]` (but with the attributes
        # the loader adds) for use in places like this.
        if not hasattr(func, "example"):
            func.example = []

        import sys

        # only inject test-related stuff if we're running tests
        # see https://stackoverflow.com/a/44595269/5991
        if 'pytest' in sys.modules and self.result:
            from sopel.tests import pytest_plugin

            # avoids doing `import pytest` and causing errors when
            # dev-dependencies aren't installed
            pytest = sys.modules['pytest']

            test = pytest_plugin.get_example_test(
                func, self.msg, self.result, self.privmsg, self.admin,
                self.owner, self.repeat, self.use_re, self.ignore
            )

            if self.online:
                test = pytest.mark.online(test)

            if self.vcr:
                test = pytest.mark.vcr(test)

            pytest_plugin.insert_into_module(
                test, func.__module__, func.__name__, 'test_example'
            )
            pytest_plugin.insert_into_module(
                pytest_plugin.get_disable_setup(),
                func.__module__,
                func.__name__,
                'disable_setup',
            )

        record = {
            "example": self.msg,
            "result": self.result,
            # flags
            "is_private_message": self.privmsg,
            "is_help": self.user_help,
            "is_pattern": self.use_re,
            "is_admin": self.admin,
            "is_owner": self.owner,
        }
        func.example.append(record)
        return func


def output_prefix(prefix: str) -> Callable:
    """Decorate a function to add a prefix on its output.

    :param prefix: the prefix to add (must include trailing whitespace if
                   desired; Sopel does not assume it should add anything)

    Prefix will be added to text sent through:

    * :meth:`bot.say <sopel.bot.SopelWrapper.say>`
    * :meth:`bot.notice <sopel.bot.SopelWrapper.notice>`

    """
    def add_attribute(function):
        function.output_prefix = prefix
        return function
    return add_attribute
