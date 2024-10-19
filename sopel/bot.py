# Copyright 2008, Sean B. Palmer, inamidst.com
# Copyright © 2012, Elad Alfassa <elad@fedoraproject.org>
# Copyright 2012-2015, Elsie Powell, http://embolalia.com
# Copyright 2019, Florian Strzelecki <florian.strzelecki@gmail.com>
#
# Licensed under the Eiffel Forum License 2.

from __future__ import annotations

from ast import literal_eval
import inspect
import itertools
import logging
import re
import threading
import time
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Optional,
    Sequence,
    TYPE_CHECKING,
    TypeVar,
    Union,
)

from sopel import db, irc, logger, plugin, plugins, tools
from sopel.irc import modes
from sopel.lifecycle import deprecated
from sopel.plugins import (
    capabilities as plugin_capabilities,
    jobs as plugin_jobs,
    rules as plugin_rules,
)
from sopel.tools import jobs as tools_jobs
from sopel.trigger import Trigger

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sopel.plugins.handlers import (
        AbstractPluginHandler, PluginMetaDescription,
    )
    from sopel.trigger import PreTrigger


__all__ = ['Sopel', 'SopelWrapper']

LOGGER = logging.getLogger(__name__)

AbstractRuleType = TypeVar('AbstractRuleType', bound=plugin_rules.AbstractRule)


class Sopel(irc.AbstractBot):
    def __init__(self, config, daemon=False):
        super().__init__(config)
        self._daemon = daemon  # Used for iPython. TODO something saner here
        self._running_triggers = []
        self._running_triggers_lock = threading.Lock()
        self._plugins: dict[str, Any] = {}
        self._rules_manager = plugin_rules.Manager()
        self._cap_requests_manager = plugin_capabilities.Manager()
        self._scheduler = plugin_jobs.Scheduler(self)

        self._url_callbacks = tools.SopelMemory()
        """Tracking of manually registered URL callbacks.

        Should be manipulated only by use of :meth:`register_url_callback` and
        :meth:`unregister_url_callback` methods, which are deprecated.

        Remove in Sopel 9, along with the above related methods.
        """

        self._times = {}
        """
        A dictionary mapping lowercased nicks to dictionaries which map
        function names to the time which they were last used by that nick.
        """

        self.modeparser = modes.ModeParser()
        """A mode parser used to parse ``MODE`` messages and modestrings."""

        self.channels = self.make_identifier_memory()
        """A map of the channels that Sopel is in.

        The keys are :class:`~sopel.tools.identifiers.Identifier`\\s of the
        channel names, and map to :class:`~sopel.tools.target.Channel` objects
        which contain the users in the channel and their permissions.
        """

        self.users = self.make_identifier_memory()
        """A map of the users that Sopel is aware of.

        The keys are :class:`~sopel.tools.identifiers.Identifier`\\s of the
        nicknames, and map to :class:`~sopel.tools.target.User` instances. In
        order for Sopel to be aware of a user, it must share at least one
        mutual channel.
        """

        self.db = db.SopelDB(config, identifier_factory=self.make_identifier)
        """The bot's database, as a :class:`sopel.db.SopelDB` instance."""

        self.memory = tools.SopelMemory()
        """
        A thread-safe dict for storage of runtime data to be shared between
        plugins. See :class:`sopel.tools.memories.SopelMemory`.
        """

        self.shutdown_methods = []
        """List of methods to call on shutdown."""

    @property
    def cap_requests(self) -> plugin_capabilities.Manager:
        """Capability Requests manager."""
        return self._cap_requests_manager

    @property
    def rules(self) -> plugin_rules.Manager:
        """Rules manager."""
        return self._rules_manager

    @property
    def scheduler(self) -> plugin_jobs.Scheduler:
        """Job Scheduler. See :func:`sopel.plugin.interval`."""
        return self._scheduler

    @property
    def command_groups(self) -> dict[str, list]:
        """A mapping of plugin names to lists of their commands.

        .. versionchanged:: 7.1
            This attribute is now generated on the fly from the registered list
            of commands and nickname commands.
        """
        # This was supposed to be deprecated, but the built-in help plugin needs it
        # TODO: create a new, better, doc interface to remove it
        plugin_commands = itertools.chain(
            self._rules_manager.get_all_commands(),
            self._rules_manager.get_all_nick_commands(),
        )
        result = {}

        for plugin_name, commands in plugin_commands:
            if plugin_name not in result:
                result[plugin_name] = list(sorted(commands.keys()))
            else:
                result[plugin_name].extend(commands.keys())
                result[plugin_name] = list(sorted(result[plugin_name]))

        return result

    @property
    def doc(self) -> dict[str, tuple]:
        """A dictionary of command names to their documentation.

        Each command is mapped to its docstring and any available examples, if
        declared in the plugin's code.

        .. versionchanged:: 3.2
            Use the first item in each callable's commands list as the key,
            instead of the function name as declared in the source code.

        .. versionchanged:: 7.1
            This attribute is now generated on the fly from the registered list
            of commands and nickname commands.
        """
        # TODO: create a new, better, doc interface to remove it
        plugin_commands = itertools.chain(
            self._rules_manager.get_all_commands(),
            self._rules_manager.get_all_nick_commands(),
        )
        commands = (
            (command, command.get_doc(), command.get_usages())
            for plugin_name, commands in plugin_commands
            for command in commands.values()
        )

        return dict(
            (name, (doc.splitlines(), [u['text'] for u in usages]))
            for command, doc, usages in commands
            for name in ((command.name,) + command.aliases)
        )

    @property
    def hostmask(self) -> Optional[str]:
        """The current hostmask for the bot :class:`~sopel.tools.target.User`.

        :return: the bot's current hostmask if the bot is connected and in
                 a least one channel; ``None`` otherwise
        """
        if not self.users or self.nick not in self.users:
            # bot must be connected and in at least one channel
            return None

        return self.users[self.nick].hostmask

    @property
    def plugins(self) -> Mapping[str, plugins.handlers.AbstractPluginHandler]:
        """A dict of the bot's currently loaded plugins.

        :return: an immutable map of plugin name to plugin object
        """
        return MappingProxyType(self._plugins)

    def has_channel_privilege(self, channel: str, privilege: int) -> bool:
        """Tell if the bot has a ``privilege`` level or above in a ``channel``.

        :param channel: a channel the bot is in
        :param privilege: privilege level to check
        :raise ValueError: when the channel is unknown

        This method checks the bot's privilege level in a channel, i.e. if it
        has this level or higher privileges::

            >>> bot.channels['#chan'].privileges[bot.nick] = plugin.OP
            >>> bot.has_channel_privilege('#chan', plugin.VOICE)
            True

        The ``channel`` argument can be either a :class:`str` or an
        :class:`~sopel.tools.identifiers.Identifier`, as long as Sopel joined
        said channel. If the channel is unknown, a :exc:`ValueError` will be
        raised.
        """
        if channel not in self.channels:
            raise ValueError('Unknown channel %s' % channel)

        return self.channels[channel].has_privilege(self.nick, privilege)

    # setup

    def setup(self) -> None:
        """Set up Sopel bot before it can run.

        The setup phase is in charge of:

        * setting up logging (configure Python's built-in :mod:`logging`)
        * setting up the bot's plugins (load, setup, and register)
        * starting the job scheduler
        """
        self.setup_logging()
        self.setup_plugins()
        self.post_setup()

    def setup_logging(self) -> None:
        """Set up logging based on config options."""
        logger.setup_logging(self.settings)
        base_format = self.settings.core.logging_format
        base_datefmt = self.settings.core.logging_datefmt

        # configure channel logging if required by configuration
        if self.settings.core.logging_channel:
            channel_level = self.settings.core.logging_channel_level
            channel_format = self.settings.core.logging_channel_format or base_format
            channel_datefmt = self.settings.core.logging_channel_datefmt or base_datefmt
            channel_params = {}
            if channel_format:
                channel_params['fmt'] = channel_format
            if channel_datefmt:
                channel_params['datefmt'] = channel_datefmt
            formatter = logger.ChannelOutputFormatter(**channel_params)
            handler = logger.IrcLoggingHandler(self, channel_level)
            handler.setFormatter(formatter)

            # set channel handler to `sopel` logger
            LOGGER = logging.getLogger('sopel')
            LOGGER.addHandler(handler)

    def setup_plugins(self) -> None:
        """Load plugins into the bot."""
        load_success = 0
        load_error = 0
        load_disabled = 0

        LOGGER.info("Loading plugins...")
        usable_plugins = plugins.get_usable_plugins(self.settings)
        for name, info in usable_plugins.items():
            plugin_handler, is_enabled = info
            if not is_enabled:
                load_disabled = load_disabled + 1
                continue

            try:
                plugin_handler.load()
            except Exception as e:
                load_error = load_error + 1
                LOGGER.exception("Error loading %s: %s", name, e)
            except SystemExit:
                load_error = load_error + 1
                LOGGER.exception(
                    "Error loading %s (plugin tried to exit)", name)
            else:
                try:
                    if plugin_handler.has_setup():
                        plugin_handler.setup(self)
                    plugin_handler.register(self)
                except Exception as e:
                    load_error = load_error + 1
                    LOGGER.exception("Error in %s setup: %s", name, e)
                else:
                    load_success = load_success + 1
                    LOGGER.info("Plugin loaded: %s", name)

        total = sum([load_success, load_error, load_disabled])
        if total and load_success:
            LOGGER.info(
                "Registered %d plugins, %d failed, %d disabled",
                (load_success - 1),
                load_error,
                load_disabled)
        else:
            LOGGER.warning("Warning: Couldn't load any plugins")

    # post setup

    def post_setup(self) -> None:
        """Perform post-setup actions.

        This method handles everything that should happen after all the plugins
        are loaded, and before the bot can connect to the IRC server.

        At the moment, this method checks for undefined configuration options,
        and starts the job scheduler.

        .. versionadded:: 7.1
        """
        settings = self.settings
        for section_name, section in settings.get_defined_sections():
            defined_options = {
                settings.parser.optionxform(opt)
                for opt, _ in inspect.getmembers(section)
                if not opt.startswith('_')
            }
            for option_name in settings.parser.options(section_name):
                if option_name not in defined_options:
                    LOGGER.warning(
                        "Config option `%s.%s` is not defined by its section "
                        "and may not be recognized by Sopel.",
                        section_name,
                        option_name,
                    )

        self._scheduler.start()

    # plugins management

    def store_plugin_handler(
        self,
        handler: AbstractPluginHandler,
    ) -> None:
        """Record a plugin ``handler``.

        :param handler: the plugin handler to record

        Recording a plugin handler associates only its name to :attr:`plugins`.
        To register a plugin handler's callables, jobs, etc., you should use
        its :meth:`~sopel.plugins.handlers.AbstractPluginHandler.register`
        method.

        .. versionadded:: 8.1
        """
        self._plugins[handler.name] = handler

    def remove_plugin_handler(self, name: str) -> None:
        """Remove a plugin handler from ``name``.

        :param name: plugin name to forget

        Removing a plugin handler removes only its name from :attr:``plugins``.
        To unregister a plugin handler's callables, jobs, etc. you should use
        its :meth:`~sopel.plugins.handlers.AbstractPluginHandler.unregister`
        method.

        .. versionadded:: 8.1
        """
        del self._plugins[name]

    def reload_plugin(self, name: str) -> None:
        """Reload a plugin.

        :param name: name of the plugin to reload
        :raise plugins.exceptions.PluginNotRegistered: when there is no
            ``name`` plugin registered

        This function runs the plugin's shutdown routine and unregisters the
        plugin from the bot. Then this function reloads the plugin, runs its
        setup routines, and registers it again.
        """
        if not self.has_plugin(name):
            raise plugins.exceptions.PluginNotRegistered(name)

        plugin_handler = self._plugins[name]

        # tear down
        plugin_handler.shutdown(self)
        plugin_handler.unregister(self)
        LOGGER.info("Unloaded plugin %s", name)

        # reload & setup
        plugin_handler.reload()
        plugin_handler.setup(self)
        plugin_handler.register(self)
        meta = plugin_handler.get_meta_description()
        LOGGER.info("Reloaded %s plugin %s from %s",
                    meta['type'], name, meta['source'])

    def reload_plugins(self) -> None:
        """Reload all registered plugins.

        First, this function runs all plugin shutdown routines and unregisters
        all plugins. Then it reloads all plugins, runs their setup routines, and
        registers them again.
        """
        registered = list(self._plugins.items())
        # tear down all plugins
        for name, handler in registered:
            handler.shutdown(self)
            handler.unregister(self)
            LOGGER.info("Unloaded plugin %s", name)

        # reload & setup all plugins
        for name, handler in registered:
            handler.reload()
            handler.setup(self)
            handler.register(self)
            meta = handler.get_meta_description()
            LOGGER.info("Reloaded %s plugin %s from %s",
                        meta['type'], name, meta['source'])

    # TODO: Remove in Sopel 9.0

    @deprecated(
        'Use direct access to add rules, jobs, etc.',
        version='8.1',
        removed_in='9.0',
    )
    def add_plugin(
        self,
        plugin: AbstractPluginHandler,
        callables: Sequence[Callable],
        jobs: Sequence[Callable],
        shutdowns: Sequence[Callable],
        urls: Sequence[Callable],
    ) -> None:
        """Add a loaded plugin to the bot's registry.

        :param plugin: loaded plugin to add
        :param callables: an iterable of callables from the ``plugin``
        :param jobs: an iterable of functions from the ``plugin`` that are
                     periodically invoked
        :param shutdowns: an iterable of functions from the ``plugin`` that
                          should be called on shutdown
        :param urls: an iterable of functions from the ``plugin`` to call when
                     matched against a URL

        .. deprecated:: 8.1

            This method is deprecated and replaced by direct call to register
            methods. It will be removed in Sopel 9.0.

        """
        self._plugins[plugin.name] = plugin
        self.register_callables(callables)
        self.register_jobs(jobs)
        self.register_shutdowns(shutdowns)
        self.register_urls(urls)

    @deprecated(
        'Use direct access to remove rules, jobs, etc.',
        version='8.1',
        removed_in='9.0',
    )
    def remove_plugin(
        self,
        plugin: AbstractPluginHandler,
        callables: Sequence[Callable],
        jobs: Sequence[Callable],
        shutdowns: Sequence[Callable],
        urls: Sequence[Callable],
    ) -> None:
        """Remove a loaded plugin from the bot's registry.

        :param plugin: loaded plugin to remove
        :param callables: an iterable of callables from the ``plugin``
        :param jobs: an iterable of functions from the ``plugin`` that are
                     periodically invoked
        :param shutdowns: an iterable of functions from the ``plugin`` that
                          should be called on shutdown
        :param urls: an iterable of functions from the ``plugin`` to call when
                     matched against a URL

        .. deprecated:: 8.1

            This method is deprecated and replaced by direct call to unregister
            methods. It will be removed in Sopel 9.0.

        """
        name = plugin.name
        if not self.has_plugin(name):
            raise plugins.exceptions.PluginNotRegistered(name)

        # remove plugin rules, jobs, shutdown functions, and url callbacks
        self._rules_manager.unregister_plugin(name)
        self._scheduler.unregister_plugin(name)
        self.unregister_shutdowns(shutdowns)

        # remove plugin from registry
        del self._plugins[name]

    def has_plugin(self, name: str) -> bool:
        """Check if the bot has registered a plugin of the specified name.

        :param str name: name of the plugin to check for
        :return: whether the bot has a plugin named ``name`` registered
        :rtype: bool
        """
        return name in self._plugins

    def get_plugin_meta(self, name: str) -> PluginMetaDescription:
        """Get info about a registered plugin by its name.

        :param str name: name of the plugin about which to get info
        :return: the plugin's metadata
                 (see :meth:`~.plugins.handlers.AbstractPluginHandler.get_meta_description`)
        :rtype: :class:`dict`
        :raise plugins.exceptions.PluginNotRegistered: when there is no
            ``name`` plugin registered
        """
        if not self.has_plugin(name):
            raise plugins.exceptions.PluginNotRegistered(name)

        return self._plugins[name].get_meta_description()

    # callable management

    def register_callables(self, callables: Iterable) -> None:
        match_any = re.compile(r'.*')
        settings = self.settings

        for callbl in callables:
            rules = getattr(callbl, 'rule', [])
            lazy_rules = getattr(callbl, 'rule_lazy_loaders', [])
            find_rules = getattr(callbl, 'find_rules', [])
            lazy_find_rules = getattr(callbl, 'find_rules_lazy_loaders', [])
            search_rules = getattr(callbl, 'search_rules', [])
            lazy_search_rules = getattr(callbl, 'search_rules_lazy_loaders', [])
            commands = getattr(callbl, 'commands', [])
            nick_commands = getattr(callbl, 'nickname_commands', [])
            action_commands = getattr(callbl, 'action_commands', [])
            is_rule = any([
                rules,
                lazy_rules,
                find_rules,
                lazy_find_rules,
                search_rules,
                lazy_search_rules,
            ])
            is_command = any([commands, nick_commands, action_commands])

            if rules:
                rule = plugin_rules.Rule.from_callable(settings, callbl)
                self._rules_manager.register(rule)

            if lazy_rules:
                try:
                    rule = plugin_rules.Rule.from_callable_lazy(
                        settings, callbl)
                    self._rules_manager.register(rule)
                except plugins.exceptions.PluginError as err:
                    LOGGER.error('Cannot register rule: %s', err)

            if find_rules:
                rule = plugin_rules.FindRule.from_callable(settings, callbl)
                self._rules_manager.register(rule)

            if lazy_find_rules:
                try:
                    rule = plugin_rules.FindRule.from_callable_lazy(
                        settings, callbl)
                    self._rules_manager.register(rule)
                except plugins.exceptions.PluginError as err:
                    LOGGER.error('Cannot register find rule: %s', err)

            if search_rules:
                rule = plugin_rules.SearchRule.from_callable(settings, callbl)
                self._rules_manager.register(rule)

            if lazy_search_rules:
                try:
                    rule = plugin_rules.SearchRule.from_callable_lazy(
                        settings, callbl)
                    self._rules_manager.register(rule)
                except plugins.exceptions.PluginError as err:
                    LOGGER.error('Cannot register search rule: %s', err)

            if commands:
                rule = plugin_rules.Command.from_callable(settings, callbl)
                self._rules_manager.register_command(rule)

            if nick_commands:
                rule = plugin_rules.NickCommand.from_callable(
                    settings, callbl)
                self._rules_manager.register_nick_command(rule)

            if action_commands:
                rule = plugin_rules.ActionCommand.from_callable(
                    settings, callbl)
                self._rules_manager.register_action_command(rule)

            if not is_command and not is_rule:
                callbl.rule = [match_any]
                self._rules_manager.register(
                    plugin_rules.Rule.from_callable(self.settings, callbl))

    def register_jobs(self, jobs: Iterable) -> None:
        for func in jobs:
            job = tools_jobs.Job.from_callable(self.settings, func)
            self._scheduler.register(job)

    def unregister_jobs(self, jobs: Iterable) -> None:
        for job in jobs:
            self._scheduler.remove_callable_job(job)

    def register_shutdowns(self, shutdowns: Iterable) -> None:
        # Append plugin's shutdown function to the bot's list of functions to
        # call on shutdown
        self.shutdown_methods = self.shutdown_methods + list(shutdowns)

    def unregister_shutdowns(self, shutdowns: Iterable[Callable]) -> None:
        self.shutdown_methods = [
            shutdown
            for shutdown in self.shutdown_methods
            if shutdown not in shutdowns
        ]

    def register_urls(self, urls: Iterable) -> None:
        for func in urls:
            url_regex = getattr(func, 'url_regex', [])
            url_lazy_loaders = getattr(func, 'url_lazy_loaders', None)

            if url_regex:
                rule = plugin_rules.URLCallback.from_callable(
                    self.settings, func)
                self._rules_manager.register_url_callback(rule)

            if url_lazy_loaders:
                try:
                    rule = plugin_rules.URLCallback.from_callable_lazy(
                        self.settings, func)
                    self._rules_manager.register_url_callback(rule)
                except plugins.exceptions.PluginError as err:
                    LOGGER.error("Cannot register URL callback: %s", err)

    def rate_limit_info(
        self,
        rule: AbstractRuleType,
        trigger: Trigger,
    ) -> tuple[bool, Optional[str]]:
        if trigger.admin or rule.is_unblockable():
            return False, None

        is_channel = trigger.sender and not trigger.sender.is_nick()
        channel = trigger.sender if is_channel else None

        at_time = trigger.time

        user_metrics = rule.get_user_metrics(trigger.nick)
        channel_metrics = rule.get_channel_metrics(channel)
        global_metrics = rule.get_global_metrics()

        if user_metrics.is_limited(at_time - rule.user_rate_limit):
            template = rule.user_rate_template
            rate_limit_type = "user"
            rate_limit = rule.user_rate_limit
            metrics = user_metrics
        elif is_channel and channel_metrics.is_limited(at_time - rule.channel_rate_limit):
            template = rule.channel_rate_template
            rate_limit_type = "channel"
            rate_limit = rule.channel_rate_limit
            metrics = channel_metrics
        elif global_metrics.is_limited(at_time - rule.global_rate_limit):
            template = rule.global_rate_template
            rate_limit_type = "global"
            rate_limit = rule.global_rate_limit
            metrics = global_metrics
        else:
            return False, None

        if not metrics.last_time:
            # you and I know that is_limited() will never return True if
            # last_time is None, but the type-checker doesn't
            return False, None

        next_time = metrics.last_time + rate_limit
        time_left = next_time - at_time

        message: Optional[str] = None

        if template:
            message = template.format(
                nick=trigger.nick,
                channel=channel or 'private message',
                sender=trigger.sender,
                plugin=rule.get_plugin_name(),
                label=rule.get_rule_label(),
                time_left=time_left,
                time_left_sec=time_left.total_seconds(),
                rate_limit=rate_limit,
                rate_limit_sec=rate_limit.total_seconds(),
                rate_limit_type=rate_limit_type,
            )

        return True, message

    # message dispatch

    def call_rule(
        self,
        rule: plugin_rules.AbstractRule,
        sopel: 'SopelWrapper',
        trigger: Trigger,
    ) -> None:
        nick = trigger.nick
        context = trigger.sender
        is_channel = context and not context.is_nick()

        limited, limit_msg = self.rate_limit_info(rule, trigger)
        if limit_msg:
            sopel.notice(limit_msg, destination=nick)
        if limited:
            return

        # channel config
        if is_channel and context in self.config:
            channel_config = self.config[context]
            plugin_name = rule.get_plugin_name()

            # disable listed plugins completely on provided channel
            if 'disable_plugins' in channel_config:
                disabled_plugins = channel_config.disable_plugins.split(',')

                if plugin_name == 'coretasks':
                    LOGGER.debug("disable_plugins refuses to skip a coretasks handler")
                elif '*' in disabled_plugins:
                    return
                elif plugin_name in disabled_plugins:
                    return

            # disable chosen methods from plugins
            if 'disable_commands' in channel_config:
                disabled_commands = literal_eval(channel_config.disable_commands)
                disabled_commands = disabled_commands.get(plugin_name, [])
                if rule.get_rule_label() in disabled_commands:
                    if plugin_name != 'coretasks':
                        return
                    LOGGER.debug("disable_commands refuses to skip a coretasks handler")

        try:
            rule.execute(sopel, trigger)
        except KeyboardInterrupt:
            raise
        except Exception as error:
            self.error(trigger, exception=error)

    def call(
        self,
        func: Any,
        sopel: 'SopelWrapper',
        trigger: Trigger,
    ) -> None:
        """Call a function, applying any rate limits or other restrictions.

        :param func: the function to call
        :type func: :term:`function`
        :param sopel: a SopelWrapper instance
        :type sopel: :class:`SopelWrapper`
        :param Trigger trigger: the Trigger object for the line from the server
                                that triggered this call
        """
        nick = trigger.nick
        current_time = time.time()
        if nick not in self._times:
            self._times[nick] = dict()
        if self.nick not in self._times:
            self._times[self.nick] = dict()
        if not trigger.is_privmsg and trigger.sender not in self._times:
            self._times[trigger.sender] = dict()

        if not trigger.admin and not func.unblockable:
            if func in self._times[nick]:
                usertimediff = current_time - self._times[nick][func]
                if func.user_rate > 0 and usertimediff < func.user_rate:
                    LOGGER.info(
                        "%s prevented from using %s in %s due to user limit: %d < %d",
                        trigger.nick, func.__name__, trigger.sender, usertimediff,
                        func.user_rate
                    )
                    return
            if func in self._times[self.nick]:
                globaltimediff = current_time - self._times[self.nick][func]
                if func.global_rate > 0 and globaltimediff < func.global_rate:
                    LOGGER.info(
                        "%s prevented from using %s in %s due to global limit: %d < %d",
                        trigger.nick, func.__name__, trigger.sender, globaltimediff,
                        func.global_rate
                    )
                    return

            if not trigger.is_privmsg and func in self._times[trigger.sender]:
                chantimediff = current_time - self._times[trigger.sender][func]
                if func.channel_rate > 0 and chantimediff < func.channel_rate:
                    LOGGER.info(
                        "%s prevented from using %s in %s due to channel limit: %d < %d",
                        trigger.nick, func.__name__, trigger.sender, chantimediff,
                        func.channel_rate
                    )
                    return

        # if channel has its own config section, check for excluded plugins/plugin methods,
        # but only if the source plugin is NOT coretasks, because we NEED those handlers.
        # Normal, whole-bot configuration will not let you disable coretasks either.
        if trigger.sender in self.config and func.plugin_name != 'coretasks':
            channel_config = self.config[trigger.sender]
            LOGGER.debug(
                "Evaluating configuration for %s.%s in channel %s",
                func.plugin_name, func.__name__, trigger.sender
            )

            # disable listed plugins completely on provided channel
            if 'disable_plugins' in channel_config:
                disabled_plugins = channel_config.disable_plugins.split(',')

                # if "*" is used, we are disabling all plugins on provided channel
                if '*' in disabled_plugins:
                    LOGGER.debug(
                        "All plugins disabled in %s; skipping execution of %s.%s",
                        trigger.sender, func.plugin_name, func.__name__
                    )
                    return
                if func.plugin_name in disabled_plugins:
                    LOGGER.debug(
                        "Plugin %s is disabled in %s; skipping execution of %s",
                        func.plugin_name, trigger.sender, func.__name__
                    )
                    return

            # disable chosen methods from plugins
            if 'disable_commands' in channel_config:
                disabled_commands = literal_eval(channel_config.disable_commands)

                if func.plugin_name in disabled_commands:
                    if func.__name__ in disabled_commands[func.plugin_name]:
                        LOGGER.debug(
                            "Skipping execution of %s.%s in %s: disabled_commands matched",
                            func.plugin_name, func.__name__, trigger.sender
                        )
                        return

        try:
            exit_code = func(sopel, trigger)
        except Exception as error:  # TODO: Be specific
            exit_code = None
            self.error(trigger, exception=error)

        if exit_code != plugin.NOLIMIT:
            self._times[nick][func] = current_time
            self._times[self.nick][func] = current_time
            if not trigger.is_privmsg:
                self._times[trigger.sender][func] = current_time

    def _is_pretrigger_blocked(
        self,
        pretrigger: PreTrigger,
    ) -> Union[tuple[bool, bool], tuple[None, None]]:
        if not (
            self.settings.core.nick_blocks
            or self.settings.core.host_blocks
        ):
            return (None, None)

        nick_blocked = self._nick_blocked(pretrigger.nick)
        host_blocked = self._host_blocked(pretrigger.host)
        return (nick_blocked, host_blocked)

    def dispatch(self, pretrigger: PreTrigger) -> None:
        """Dispatch a parsed message to any registered callables.

        :param pretrigger: a parsed message from the server
        :type pretrigger: :class:`~sopel.trigger.PreTrigger`

        The ``pretrigger`` (a parsed message) is used to find matching rules;
        it will retrieve them by order of priority, and execute them. It runs
        triggered rules in separate threads, unless they are marked otherwise.

        However, it won't run triggered blockable rules at all when they can't
        be executed for blocked nickname or hostname.

        .. seealso::

            The pattern matching is done by the
            :class:`Rules Manager<sopel.plugins.rules.Manager>`.

        """
        # list of commands running in separate threads for this dispatch
        running_triggers = []
        # nickname/hostname blocking
        nick_blocked, host_blocked = self._is_pretrigger_blocked(pretrigger)
        blocked = bool(nick_blocked or host_blocked)
        list_of_blocked_rules = set()
        # account info
        nick = pretrigger.nick
        user_obj = self.users.get(nick)
        account = user_obj.account if user_obj else None

        # skip processing replayed messages
        if "time" in pretrigger.tags and pretrigger.sender in self.channels:
            join_time = self.channels[pretrigger.sender].join_time
            if join_time is not None and pretrigger.time < join_time:
                return

        for rule, match in self._rules_manager.get_triggered_rules(self, pretrigger):
            trigger = Trigger(self.settings, pretrigger, match, account)

            is_unblockable = trigger.admin or rule.is_unblockable()
            if blocked and not is_unblockable:
                list_of_blocked_rules.add(str(rule))
                continue

            wrapper = SopelWrapper(
                self, trigger, output_prefix=rule.get_output_prefix())

            if rule.is_threaded():
                # run in a separate thread
                targs = (rule, wrapper, trigger)
                t = threading.Thread(target=self.call_rule, args=targs)
                plugin_name = rule.get_plugin_name()
                rule_label = rule.get_rule_label()
                t.name = '%s-%s-%s' % (t.name, plugin_name, rule_label)
                t.start()
                running_triggers.append(t)
            else:
                # direct call
                self.call_rule(rule, wrapper, trigger)

        # update currently running triggers
        self._update_running_triggers(running_triggers)

        if list_of_blocked_rules:
            if nick_blocked and host_blocked:
                block_type = 'both blocklists'
            elif nick_blocked:
                block_type = 'nick blocklist'
            else:
                block_type = 'host blocklist'
            LOGGER.debug(
                "%s prevented from using %s by %s.",
                pretrigger.nick,
                ', '.join(list_of_blocked_rules),
                block_type,
            )

    @property
    def running_triggers(self) -> list:
        """Current active threads for triggers.

        :return: the running thread(s) currently processing trigger(s)
        :rtype: :term:`iterable`

        This is for testing and debugging purposes only.
        """
        with self._running_triggers_lock:
            return [t for t in self._running_triggers if t.is_alive()]

    def _update_running_triggers(self, running_triggers: list) -> None:
        """Update list of running triggers.

        :param list running_triggers: newly started threads

        We want to keep track of running triggers, mostly for testing and
        debugging purposes. For instance, it'll help make sure, in tests, that
        a bot plugin has finished processing a trigger, by manually joining
        all running threads.

        This is kept private, as it's purely internal machinery and isn't
        meant to be manipulated by outside code.
        """
        # update bot's global running triggers
        with self._running_triggers_lock:
            running_triggers = running_triggers + self._running_triggers
            self._running_triggers = [
                t for t in running_triggers if t.is_alive()]

    # capability negotiation
    def request_capabilities(self) -> bool:
        """Request available capabilities and return if negotiation is on.

        :return: tell if the negotiation is active or not

        This takes the available capabilities and asks the request manager to
        request only these that are available.

        If none is available or if none is requested, the negotiation is not
        active and this returns ``False``. It is the responsibility of the
        caller to make sure it signals the IRC server to end the negotiation
        with a ``CAP END`` command.
        """
        available_capabilities = self._capabilities.available.keys()

        if not available_capabilities:
            LOGGER.debug('No client capability to negotiate.')
            return False

        LOGGER.info(
            "Client capability negotiation list: %s",
            ', '.join(available_capabilities),
        )

        self._cap_requests_manager.request_available(
            self, available_capabilities)

        return bool(self._cap_requests_manager.requested)

    def resume_capability_negotiation(
        self,
        cap_req: tuple[str, ...],
        plugin_name: str,
    ) -> None:
        """Resume capability negotiation and close when necessary.

        :param cap_req: a capability request
        :param plugin_name: plugin that requested the capability and wants to
                            resume capability negotiation

        This will resume a capability request through the bot's
        :attr:`capability requests manager<cap_requests>`, and if the
        negotiation wasn't completed before and is now complete, it will send
        a ``CAP END`` command.

        This method must be used by plugins that declare a capability request
        with a handler that returns
        :attr:`sopel.plugin.CapabilityNegotiation.CONTINUE` on acknowledgement
        in order for the bot to resume and eventually close negotiation.

        For example, this is useful for SASL auth which happens while
        negotiating capabilities.
        """
        was_completed, is_complete = self._cap_requests_manager.resume(
            cap_req, plugin_name,
        )
        if not was_completed and is_complete:
            LOGGER.info("End of client capability negotiation requests.")
            self.write(('CAP', 'END'))

    # event handlers

    def on_scheduler_error(
        self,
        scheduler: plugin_jobs.Scheduler,
        exc: BaseException,
    ) -> None:
        """Called when the Job Scheduler fails.

        :param scheduler: the job scheduler that errored
        :param exc: the raised exception

        .. seealso::

            :meth:`Sopel.error`
        """
        self.error(exception=exc)

    def on_job_error(
        self,
        scheduler: plugin_jobs.Scheduler,
        job: tools_jobs.Job,
        exc: BaseException,
    ) -> None:
        """Called when a job from the Job Scheduler fails.

        :param scheduler: the job scheduler responsible for the errored ``job``
        :param job: the Job that errored
        :param exc: the raised exception

        .. seealso::

            :meth:`Sopel.error`
        """
        self.error(exception=exc)

    def error(
        self,
        trigger: Optional[Trigger] = None,
        exception: Optional[BaseException] = None,
    ) -> None:
        """Called internally when a plugin causes an error.

        :param trigger: the IRC line that caused the error (if available)
        :param exception: the exception raised by the error (if available)
        """
        message = 'Unexpected error'
        if exception:
            detail = ' ({})'.format(exception) if str(exception) else ''
            message = 'Unexpected {}{}'.format(type(exception).__name__, detail)

        if trigger:
            message = '{} from {}. Message was: {}'.format(
                message, trigger.nick, trigger.group(0)
            )

        LOGGER.exception(message)

        if trigger and self.settings.core.reply_errors and trigger.sender is not None:
            self.say(message, trigger.sender)

    def _host_blocked(self, host: str) -> bool:
        """Check if a hostname is blocked.

        :param host: the hostname to check
        """
        bad_masks = self.config.core.host_blocks
        for bad_mask in bad_masks:
            bad_mask = bad_mask.strip()
            if not bad_mask:
                continue
            if (re.match(bad_mask + '$', host, re.IGNORECASE) or
                    bad_mask == host):
                return True
        return False

    def _nick_blocked(self, nick: str) -> bool:
        """Check if a nickname is blocked.

        :param nick: the nickname to check
        """
        bad_nicks = self.config.core.nick_blocks
        for bad_nick in bad_nicks:
            bad_nick = bad_nick.strip()
            if not bad_nick:
                continue
            if (re.match(bad_nick + '$', nick, re.IGNORECASE) or
                    self.make_identifier(bad_nick) == nick):
                return True
        return False

    def _shutdown(self) -> None:
        """Internal bot shutdown method."""
        LOGGER.info("Shutting down")
        # Proactively tell plugins (at least the ones that bother to check)
        self._connection_registered.clear()
        # Stop Job Scheduler
        LOGGER.info("Stopping the Job Scheduler.")
        self._scheduler.stop()

        try:
            self._scheduler.join(timeout=15)
        except RuntimeError:
            LOGGER.exception("Unable to stop the Job Scheduler.")
        else:
            LOGGER.info("Job Scheduler stopped.")

        self._scheduler.clear_jobs()

        # Shutdown plugins
        LOGGER.info(
            "Calling shutdown for %d plugins.", len(self.shutdown_methods))

        for shutdown_method in self.shutdown_methods:
            try:
                LOGGER.debug(
                    "Calling %s.%s",
                    shutdown_method.__module__,
                    shutdown_method.__name__)
                shutdown_method(self)
            except Exception as e:
                LOGGER.exception("Error calling shutdown method: %s", e)

        # Avoid calling shutdown methods if we already have.
        self.shutdown_methods = []

    # URL callbacks management

    @deprecated(
        reason='Issues with @url decorator have been fixed. Simply use that.',
        version='7.1',
        warning_in='8.0',
        removed_in='9.0',
    )
    def register_url_callback(self, pattern, callback):
        """Register a ``callback`` for URLs matching the regex ``pattern``.

        :param pattern: compiled regex pattern to register
        :type pattern: :ref:`re.Pattern <python:re-objects>`
        :param callback: callable object to handle matching URLs
        :type callback: :term:`function`

        .. versionadded:: 7.0

            This method replaces manual management of ``url_callbacks`` in
            Sopel's plugins, so instead of doing this in ``setup()``::

                if 'url_callbacks' not in bot.memory:
                    bot.memory['url_callbacks'] = tools.SopelMemory()

                regex = re.compile(r'http://example.com/path/.*')
                bot.memory['url_callbacks'][regex] = callback

            use this much more concise pattern::

                regex = re.compile(r'http://example.com/path/.*')
                bot.register_url_callback(regex, callback)

        It's recommended you completely avoid manual management of URL
        callbacks through the use of :func:`sopel.plugin.url`.

        .. deprecated:: 7.1

            Made obsolete by fixes to the behavior of
            :func:`sopel.plugin.url`. Will be removed in Sopel 9.

        .. versionchanged:: 8.0

            Stores registered callbacks in an internal property instead of
            ``bot.memory['url_callbacks']``.

        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        self._url_callbacks[pattern] = callback

    @deprecated(
        reason='Issues with @url decorator have been fixed. Simply use that.',
        version='7.1',
        warning_in='8.0',
        removed_in='9.0',
    )
    def unregister_url_callback(self, pattern, callback):
        """Unregister the callback for URLs matching the regex ``pattern``.

        :param pattern: compiled regex pattern to unregister callback
        :type pattern: :ref:`re.Pattern <python:re-objects>`
        :param callback: callable object to remove
        :type callback: :term:`function`

        .. versionadded:: 7.0

            This method replaces manual management of ``url_callbacks`` in
            Sopel's plugins, so instead of doing this in ``shutdown()``::

                regex = re.compile(r'http://example.com/path/.*')
                try:
                    del bot.memory['url_callbacks'][regex]
                except KeyError:
                    pass

            use this much more concise pattern::

                regex = re.compile(r'http://example.com/path/.*')
                bot.unregister_url_callback(regex, callback)

        It's recommended you completely avoid manual management of URL
        callbacks through the use of :func:`sopel.plugin.url`.

        .. deprecated:: 7.1

            Made obsolete by fixes to the behavior of
            :func:`sopel.plugin.url`. Will be removed in Sopel 9.

        .. versionchanged:: 8.0

            Deletes registered callbacks from an internal property instead of
            ``bot.memory['url_callbacks']``.

        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        try:
            del self._url_callbacks[pattern]
        except KeyError:
            pass

    @deprecated(
        reason=(
            'URL handling has been unified in the Rules system via the @url '
            'decorator. Use RuleManager.check_url_callbacks() if needed.'),
        version='8.0',
        warning_in='8.1',
        removed_in='9.0',
    )
    def search_url_callbacks(self, url):
        """Yield callbacks whose regex pattern matches the ``url``.

        :param str url: URL found in a trigger
        :return: yield 2-value tuples of ``(callback, match)``

        For each pattern that matches the ``url`` parameter, it yields a
        2-value tuple of ``(callable, match)`` for that pattern.

        The ``callable`` is the one registered with
        :meth:`register_url_callback`, and the ``match`` is the result of
        the regex pattern's ``search`` method.

        .. versionadded:: 7.0

        .. versionchanged:: 8.0

            Searches for registered callbacks in an internal property instead
            of ``bot.memory['url_callbacks']``.

        .. deprecated:: 8.0

            Made obsolete by fixes to the behavior of
            :func:`sopel.plugin.url`. Will be removed in Sopel 9.

        .. seealso::

            The Python documentation for the `re.search`__ function and
            the `match object`__.

        .. __: https://docs.python.org/3.11/library/re.html#re.search
        .. __: https://docs.python.org/3.11/library/re.html#match-objects

        """
        for regex, function in self._url_callbacks.items():
            match = regex.search(url)
            if match:
                yield function, match


class SopelWrapper:
    """Wrapper around a Sopel instance and a Trigger.

    :param sopel: Sopel instance
    :type sopel: :class:`~sopel.bot.Sopel`
    :param trigger: IRC Trigger line
    :type trigger: :class:`~sopel.trigger.Trigger`
    :param str output_prefix: prefix for messages sent through this wrapper
                              (e.g. plugin tag)

    This wrapper will be used to call Sopel's triggered commands and rules as
    their ``bot`` argument. It acts as a proxy, providing the ``trigger``'s
    ``sender`` (source channel or private message) as the default
    ``destination`` argument for overridden methods.

    .. deprecated:: 8.0

        ``SopelWrapper`` will be replaced with a ``contextvars`` based
        alternative. For more information, see :issue:`2460`.

    """
    def __init__(self, sopel, trigger, output_prefix=''):
        if not output_prefix:
            # Just in case someone passes in False, None, etc.
            output_prefix = ''
        # The custom __setattr__ for this class sets the attribute on the
        # original bot object. We don't want that for these, so we set them
        # with the normal __setattr__.
        object.__setattr__(self, '_bot', sopel)
        object.__setattr__(self, '_trigger', trigger)
        object.__setattr__(self, '_out_pfx', output_prefix)

    def __dir__(self):
        classattrs = [attr for attr in self.__class__.__dict__
                      if not attr.startswith('__')]
        return list(self.__dict__) + classattrs + dir(self._bot)

    def __getattr__(self, attr):
        return getattr(self._bot, attr)

    def __setattr__(self, attr, value):
        return setattr(self._bot, attr, value)

    @property
    def default_destination(self) -> Optional[str]:
        """Default say/reply destination for the associated Trigger.

        :return: the channel (with status prefix) or nick to send messages to

        This property returns the :class:`str` version of the destination that
        will be used by default by these methods:

        * :meth:`say`
        * :meth:`reply`
        * :meth:`action`
        * :meth:`notice`

        For a channel, it also ensures that the status-specific prefix is added
        to the result, so the bot replies with the same status.
        """
        if not self._trigger.sender:
            return None

        # ensure str and not Identifier
        destination = str(self._trigger.sender)

        # prepend status prefix if it exists
        if self._trigger.status_prefix:
            destination = self._trigger.status_prefix + destination

        return destination

    def say(self, message, destination=None, max_messages=1, truncation='', trailing=''):
        """Override ``Sopel.say`` to use trigger source by default.

        :param str message: message to say
        :param str destination: channel or nickname; defaults to
            :attr:`trigger.sender <sopel.trigger.Trigger.sender>`
        :param int max_messages: split ``message`` into at most this many
                                 messages if it is too long to fit into one
                                 line (optional)
        :param str truncation: string to indicate that the ``message`` was
                               truncated (optional)
        :param str trailing: string that should always appear at the end of
                             ``message`` (optional)

        The ``destination`` will default to the channel in which the
        trigger happened (or nickname, if received in a private message).

        .. seealso::

            For more details about the optional arguments to this wrapper
            method, consult the documentation for :meth:`sopel.bot.Sopel.say`.

        """
        if destination is None:
            destination = self.default_destination

        self._bot.say(
            self._out_pfx + message,
            destination,
            max_messages,
            truncation,
            trailing,
        )

    def action(self, message, destination=None):
        """Override ``Sopel.action`` to use trigger source by default.

        :param str message: action message
        :param str destination: channel or nickname; defaults to
            :attr:`trigger.sender <sopel.trigger.Trigger.sender>`

        The ``destination`` will default to the channel in which the
        trigger happened (or nickname, if received in a private message).

        .. seealso::

            :meth:`sopel.bot.Sopel.action`
        """
        if destination is None:
            destination = self.default_destination

        self._bot.action(message, destination)

    def notice(self, message, destination=None):
        """Override ``Sopel.notice`` to use trigger source by default.

        :param str message: notice message
        :param str destination: channel or nickname; defaults to
            :attr:`trigger.sender <sopel.trigger.Trigger.sender>`

        The ``destination`` will default to the channel in which the
        trigger happened (or nickname, if received in a private message).

        .. seealso::

            :meth:`sopel.bot.Sopel.notice`
        """
        if destination is None:
            destination = self.default_destination

        self._bot.notice(self._out_pfx + message, destination)

    def reply(self, message, destination=None, reply_to=None, notice=False):
        """Override ``Sopel.reply`` to ``reply_to`` sender by default.

        :param str message: reply message
        :param str destination: channel or nickname; defaults to
            :attr:`trigger.sender <sopel.trigger.Trigger.sender>`
        :param str reply_to: person to reply to; defaults to
            :attr:`trigger.nick <sopel.trigger.Trigger.nick>`
        :param bool notice: reply as an IRC notice or with a simple message

        The ``destination`` will default to the channel in which the
        trigger happened (or nickname, if received in a private message).

        ``reply_to`` will default to the nickname who sent the trigger.

        .. seealso::

            :meth:`sopel.bot.Sopel.reply`
        """
        if destination is None:
            destination = self.default_destination

        if reply_to is None:
            reply_to = self._trigger.nick

        self._bot.reply(message, destination, reply_to, notice)

    def kick(self, nick, channel=None, message=None):
        """Override ``Sopel.kick`` to kick in a channel

        :param str nick: nick to kick out of the ``channel``
        :param str channel: optional channel to kick ``nick`` from
        :param str message: optional message for the kick

        The ``channel`` will default to the channel in which the call was
        triggered. If triggered from a private message, ``channel`` is
        required.

        .. seealso::

            :meth:`sopel.bot.Sopel.kick`
        """
        if channel is None:
            if self._trigger.is_privmsg:
                raise RuntimeError('Error: KICK requires a channel.')
            else:
                channel = self._trigger.sender

        if nick is None:
            raise RuntimeError('Error: KICK requires a nick.')

        self._bot.kick(nick, channel, message)
