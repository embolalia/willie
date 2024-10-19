"""
version.py - Sopel Version Plugin
Copyright 2009, Silas Baronda
Copyright 2014, Dimitri Molenaars <tyrope@tyrope.nl>
Licensed under the Eiffel Forum License 2.

https://sopel.chat
"""
from __future__ import annotations

import datetime
import os
import platform

from sopel import __version__ as release, plugin


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
GIT_DIR = os.path.join(PROJECT_DIR, '.git')


def _read_commit(gitdir: str, head: str) -> str | None:
    """
    Given paths to ``.git/`` and ``HEAD``, determine the associated commit hash
    """
    result = None

    if os.path.isfile(head):
        with open(head) as h:
            head_loc = h.readline()[5:-1]  # strip ref: and \n
        head_file = os.path.join(gitdir, head_loc)
        if os.path.isfile(head_file):
            with open(head_file) as h:
                sha = h.readline()
                if sha:
                    result = sha

    return result


def _resolve_git_dirs(path: str) -> tuple[str, str]:
    """Resolve a ``.git`` path to its 'true' ``.git/`` and `HEAD`

    This helper is useful for dealing with the ``.git`` file stored in a
    git worktree.
    """
    # default to the old behavior: assume `path` is a valid .git/ to begin with
    gitdir = path
    head = os.path.join(path, "HEAD")

    if os.path.isfile(path):
        # this may be a worktree, let's override the result properly if so
        with open(path, 'r') as f:
            first, rest = next(f).strip().split(maxsplit=1)
            if first == "gitdir:":
                # line is "gitdir: /path/to/parentrepo/.git/worktrees/thispath"
                gitdir = os.path.dirname(os.path.dirname(rest))
                head = os.path.join(rest, "HEAD")
            # else: we can't make sense of this file, stick to the default

    return gitdir, head


def git_info() -> str | None:
    """
    Determine the git commit hash of this Sopel, if applicable
    """
    gitdir, head = _resolve_git_dirs(GIT_DIR)
    return _read_commit(gitdir, head)


@plugin.command('version')
@plugin.example('.version [plugin_name]')
@plugin.output_prefix('[version] ')
def version(bot, trigger):
    """Display the installed version of Sopel or a plugin.

    Includes the version of Python Sopel is installed on.
    Includes the commit hash if Sopel is installed from source.
    """
    plugin = trigger.group(3)
    if plugin and plugin.lower() != "sopel":
        # Plugin version
        if not bot.has_plugin(plugin):
            bot.say("I don't have a plugin named %r loaded." % plugin)
            return

        meta = bot.get_plugin_meta(plugin)
        if meta["version"] is None:
            version = "(unknown)"
        else:
            version = "v" + str(meta["version"])

        if meta["source"].startswith("sopel."):
            version += " (built in)"

        bot.say(plugin + " " + version)
        return

    # Sopel version
    parts = [
        'Sopel v%s' % release,
        'Python: %s' % platform.python_version()
    ]
    sha = git_info()
    if sha:
        parts.append('Commit: %s' % sha)

    bot.say(' | '.join(parts))


@plugin.ctcp('VERSION')
@plugin.rate(20)
def ctcp_version(bot, trigger):
    bot.write(('NOTICE', trigger.nick),
              '\x01VERSION Sopel IRC Bot version %s\x01' % release)


@plugin.ctcp('SOURCE')
@plugin.rate(20)
def ctcp_source(bot, trigger):
    bot.write(('NOTICE', trigger.nick),
              '\x01SOURCE https://github.com/sopel-irc/sopel\x01')


@plugin.ctcp('PING')
@plugin.rate(10)
def ctcp_ping(bot, trigger):
    text = trigger.group()
    text = text.replace("PING ", "")
    text = text.replace("\x01", "")
    bot.write(('NOTICE', trigger.nick),
              '\x01PING {0}\x01'.format(text))


@plugin.ctcp('TIME')
@plugin.rate(20)
def ctcp_time(bot, trigger):
    dt = datetime.datetime.now()
    current_time = dt.strftime("%A, %d. %B %Y %I:%M%p")
    bot.write(('NOTICE', trigger.nick),
              '\x01TIME {0}\x01'.format(current_time))
