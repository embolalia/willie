"""Sopel database module: management and tools around Sopel's datamodel.

This module defines a datamodel, using `SQLAlchemy ORM's mapping`__:

* :class:`NickIDs` and :class:`Nicknames` are used to track users
* :class:`NickValues` is used to store arbitrary values for users
* :class:`ChannelValues` is used to store arbitrary values for channels
* :class:`PluginValues` is used to store arbitrary values for plugins

These models are made available through the :class:`SopelDB` class and its
convenience methods, such as :meth:`~SopelDB.get_nick_value` or
:meth:`~SopelDB.get_channel_value`.

.. __: https://docs.sqlalchemy.org/en/14/orm/tutorial.html#declare-a-mapping
"""
from __future__ import annotations

import errno
import json
import logging
import os.path
import traceback
import typing

from sqlalchemy import Column, create_engine, ForeignKey, Integer, String, Text
from sqlalchemy.engine.url import make_url, URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker
from sqlalchemy.sql import delete, func, select, update

from sopel.lifecycle import deprecated
from sopel.tools.identifiers import Identifier, IdentifierFactory

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from sopel.config import Config


LOGGER = logging.getLogger(__name__)


def _deserialize(value):
    if value is None:
        return None
    # sqlite likes to return ints for strings that look like ints, even though
    # the column type is string. That's how you do dynamic typing wrong.
    value = str(value)
    # Just in case someone's mucking with the DB in a way we can't account for,
    # ignore json parsing errors
    try:
        value = json.loads(value)
    except ValueError:
        pass
    return value


BASE = declarative_base()
MYSQL_TABLE_ARGS = {'mysql_engine': 'InnoDB',
                    'mysql_charset': 'utf8mb4',
                    'mysql_collate': 'utf8mb4_unicode_ci'}


class NickIDs(BASE):
    """Nick IDs table SQLAlchemy class."""
    __tablename__ = 'nick_ids'
    nick_id = Column(Integer, primary_key=True)


class Nicknames(BASE):
    """Nicknames table SQLAlchemy class."""
    __tablename__ = 'nicknames'
    __table_args__ = MYSQL_TABLE_ARGS
    nick_id = Column(Integer, ForeignKey('nick_ids.nick_id'), primary_key=True)
    slug = Column(String(255), primary_key=True)
    canonical = Column(String(255))


class NickValues(BASE):
    """Nick values table SQLAlchemy class."""
    __tablename__ = 'nick_values'
    __table_args__ = MYSQL_TABLE_ARGS
    nick_id = Column(Integer, ForeignKey('nick_ids.nick_id'), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(Text)


class ChannelValues(BASE):
    """Channel values table SQLAlchemy class."""
    __tablename__ = 'channel_values'
    __table_args__ = MYSQL_TABLE_ARGS
    channel = Column(String(255), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(Text)


class PluginValues(BASE):
    """Plugin values table SQLAlchemy class."""
    __tablename__ = 'plugin_values'
    __table_args__ = MYSQL_TABLE_ARGS
    plugin = Column(String(255), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(Text)


class SopelDB:
    """Database object class.

    :param config: Sopel's configuration settings
    :type config: :class:`sopel.config.Config`
    :param identifier_factory: factory for
                               :class:`~sopel.tools.identifiers.Identifier`
    :type: Callable[[:class:`str`], :class:`str`]

    This defines a simplified interface for basic, common operations on the
    bot's database. Direct access to the database is also available through
    its :attr:`engine` attribute, to serve more complex plugins' needs.

    When configured to use SQLite with a relative filename, the file is assumed
    to be in the directory named by the core setting ``homedir``.

    .. versionadded:: 5.0

    .. versionchanged:: 7.0

        Switched from direct SQLite access to :ref:`SQLAlchemy
        <sqlalchemy:overview>`, allowing users more flexibility around what type
        of database they use (especially on high-load Sopel instances, which may
        run up against SQLite's concurrent-access limitations).

    .. versionchanged:: 8.0

        An Identifier factory can be provided that will be used to instantiate
        :class:`~sopel.tools.identifiers.Identifier` when dealing with Nick or
        Channel names.

    .. seealso::

        For any advanced usage of the ORM, refer to the
        `SQLAlchemy documentation`__.

    .. __: https://docs.sqlalchemy.org/en/14/
    """

    def __init__(
        self,
        config: Config,
        identifier_factory: IdentifierFactory = Identifier,
    ) -> None:
        self.make_identifier: IdentifierFactory = identifier_factory

        if config.core.db_url is not None:
            self.url = make_url(config.core.db_url)

            # TODO: there's no way to get `config.core.db_type.choices`, but
            # it would be nice to validate this type name somehow. Shouldn't
            # affect anything, since the only thing it's ever used for is
            # checking whether the configured database is 'sqlite'.
            self.type = self.url.drivername.split('+', 1)[0]
        elif config.core.db_type == 'sqlite':
            self.type = 'sqlite'
            path = config.core.db_filename
            if path is None:
                path = os.path.join(config.core.homedir, config.basename + '.db')
            path = os.path.expanduser(path)
            if not os.path.isabs(path):
                path = os.path.normpath(os.path.join(config.core.homedir, path))
            if not os.path.isdir(os.path.dirname(path)):
                raise OSError(
                    errno.ENOENT,
                    'Cannot create database file. '
                    'No such directory: "{}". Check that configuration setting '
                    'core.db_filename is valid'.format(os.path.dirname(path)),
                    path
                )
            self.url = make_url('sqlite:///' + path)
        else:
            self.type = config.core.db_type

            query = {}
            if self.type == 'mysql':
                drivername = config.core.db_driver or 'mysql'
                query = {'charset': 'utf8mb4'}
            elif self.type == 'postgres':
                drivername = config.core.db_driver or 'postgresql'
            elif self.type == 'oracle':
                drivername = config.core.db_driver or 'oracle'
            elif self.type == 'mssql':
                drivername = config.core.db_driver or 'mssql+pymssql'
            elif self.type == 'firebird':
                drivername = config.core.db_driver or 'firebird+fdb'
            elif self.type == 'sybase':
                drivername = config.core.db_driver or 'sybase+pysybase'
            else:
                raise Exception('Unknown db_type')

            db_user = config.core.db_user  # Sometimes empty
            db_pass = config.core.db_pass  # Sometimes empty
            db_host = config.core.db_host  # Sometimes empty
            db_port = config.core.db_port  # Optional
            db_name = config.core.db_name  # Sometimes optional

            # Ensure we have all our variables defined
            if db_user is None or db_pass is None or db_host is None:
                raise Exception('Please make sure the following core '
                                'configuration values are defined: '
                                'db_user, db_pass, db_host')
            self.url = URL(drivername=drivername, username=db_user,
                           password=db_pass, host=db_host, port=db_port,
                           database=db_name, query=query)

        self.engine = create_engine(self.url, pool_recycle=3600)
        """SQLAlchemy Engine used to connect to Sopel's database.

        .. seealso::

            Read `SQLAlchemy engine`__'s documentation to know how to use it.

        .. __: https://docs.sqlalchemy.org/en/14/core/connections.html

        .. important::

            Introduced in Sopel 7, Sopel uses SQLAlchemy 1.4+. This version of
            SQLAlchemy deprecates various behaviors and methods, to prepare the
            migration to its future 2.0 version, and the new 2.x style.

            Sopel doesn't enforce the new 2.x style yet. This will be modified
            in Sopel 9 by using the ``future=True`` flag on the engine.

            You can read more about the `migration guide from 1.x to 2.x`__, as
            Sopel will ensure in a future version that it is compatible with
            the new style.

        .. __: https://docs.sqlalchemy.org/en/14/changelog/migration_20.html
        """

        # Catch any errors connecting to database
        try:
            self.engine.connect()
        except OperationalError:
            print("OperationalError: Unable to connect to database.")
            raise

        # Create our tables
        BASE.metadata.create_all(self.engine)

        self.ssession = scoped_session(
            sessionmaker(bind=self.engine, future=True))

    def connect(self):
        """Get a direct database connection.

        :return: a proxied DBAPI connection object; see
                 :meth:`sqlalchemy.engine.Engine.raw_connection()`

        .. important::

           The :attr:`~sopel.config.core_section.CoreSection.db_type` in use
           can change how the raw connection object behaves. You probably want
           to use :meth:`session` and the SQLAlchemy ORM in new plugins, and
           officially support only Sopel 7.0+.

           Note that :meth:`session` is not available in Sopel versions prior
           to 7.0. If your plugin needs to be compatible with older Sopel
           releases, your code *should* use SQLAlchemy via :meth:`session` if
           it is available (Sopel 7.0+) and fall back to direct SQLite access
           via :meth:`connect` if it is not (Sopel 6.x).

           We discourage *publishing* plugins that don't work with all
           supported databases, but you're obviously welcome to take shortcuts
           and support only the engine(s) you need in *private* plugins.

        """
        if self.type != 'sqlite':
            # log non-sqlite uses of raw connections for troubleshooting, since
            # unless the developer had a good reason to use this instead of
            # `session()`, it indicates the plugin was written before Sopel 7.0
            # and might not work right when connected to non-sqlite DBs
            LOGGER.info(
                "Raw connection requested when 'db_type' is not 'sqlite':\n"
                "Consider using 'db.session()' to get a SQLAlchemy session "
                "instead here:\n%s",
                traceback.format_list(traceback.extract_stack()[:-1])[-1][:-1])
        return self.engine.raw_connection()

    def session(self):
        """Get a SQLAlchemy Session object.

        :rtype: :class:`sqlalchemy.orm.session.Session`

        .. versionadded:: 7.0

        .. note::

           If your plugin needs to remain compatible with Sopel versions prior
           to 7.0, you can use :meth:`connect` to get a raw connection. See
           its documentation for relevant warnings and compatibility caveats.

        """
        return self.ssession()

    @deprecated('Use SopelDB.engine directly', version='8.0', removed_in='9.0')
    def execute(self, *args, **kwargs):
        """Execute an arbitrary SQL query against the database.

        :return: the query results
        :rtype: :class:`sqlalchemy.engine.Result`

        The ``Result`` object returned is a wrapper around a ``Cursor`` object
        as specified by :pep:`249`.

        .. deprecated:: 8.0

            This method will be removed in Sopel 9, following the deprecation
            of SQLAlchemy's :meth:`sqlalchemy.engine.Engine.execute`.

            To perform a raw SQL query, use the :class:`~SopelDB.engine`
            attribute as per the migration guide from SQLAlchemy::

                from sqlalchemy.sql import text

                def my_command(bot, trigger):
                    raw_sql = ' ... '  # your raw SQL
                    # get a connection as a context manager
                    with bot.db.engine.connect() as conn:
                        res = conn.execute(text(raw_sql))
                        data = res.fetchall()

                    # do something with your data here

        .. seealso::

            Read the `migration guide from 1.x style to 2.x style`__ by
            SQLAlchemy to learn more about using SQLALchemy's engine and
            connection.

        .. __: https://docs.sqlalchemy.org/en/14/changelog/migration_20.html
        """
        return self.engine.execute(*args, **kwargs)

    def get_uri(self) -> URL:
        """Return a direct URL for the database.

        :return: the database connection URI
        :rtype: str

        This can be used to connect from a plugin using another SQLAlchemy
        instance, for example, without sharing the bot's connection.
        """
        return self.url

    # NICK FUNCTIONS

    def get_nick_id(self, nick: str, create: bool = False) -> int:
        """Return the internal identifier for a given nick.

        :param nick: the nickname for which to fetch an ID
        :param create: whether to create an ID if one does not exist
                       (set to ``False`` by default)
        :raise ValueError: if no ID exists for the given ``nick`` and ``create``
                           is set to ``False``
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        The nick ID is shared across all of a user's aliases, assuming their
        nicks have been grouped together.

        .. versionchanged:: 8.0

            The ``create`` parameter is now ``False`` by default.

        .. seealso::

            Alias/group management functions: :meth:`alias_nick`,
            :meth:`unalias_nick`, :meth:`merge_nick_groups`, and
            :meth:`forget_nick_group`.

        """
        slug = self.make_identifier(nick).lower()
        with self.session() as session:
            nickname = session.execute(
                select(Nicknames).where(Nicknames.slug == slug)
            ).scalar_one_or_none()

            if nickname is None:
                # see if it needs case-mapping migration
                nickname = session.execute(
                    select(Nicknames)
                    .where(Nicknames.slug == Identifier._lower_swapped(nick))
                ).scalar_one_or_none()

                if nickname is not None:
                    # it does!
                    nickname.slug = slug
                    session.commit()

            if nickname is None:  # "is /* still */ None", if Python had inline comments
                if not create:
                    raise ValueError('No ID exists for the given nick')
                # Generate a new ID
                nick_id = NickIDs()
                session.add(nick_id)
                session.commit()

                # Create a new Nickname
                nickname = Nicknames(
                    nick_id=nick_id.nick_id,
                    slug=slug,
                    canonical=nick,
                )
                session.add(nickname)
                session.commit()
            return nickname.nick_id

    def alias_nick(self, nick: str, alias: str) -> None:
        """Create an alias for a nick.

        :param nick: an existing nickname
        :param alias: an alias by which ``nick`` should also be known
        :raise ValueError: if the ``alias`` already exists
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. seealso::

            To merge two *existing* nick groups, use :meth:`merge_nick_groups`.

            To remove an alias created with this function, use
            :meth:`unalias_nick`.

        """
        slug = self.make_identifier(alias).lower()
        nick_id = self.get_nick_id(nick, create=True)
        with self.session() as session:
            result = session.execute(
                select(Nicknames)
                .where(Nicknames.slug == slug)
                .where(Nicknames.canonical == alias)
            ).scalar_one_or_none()
            if result:
                raise ValueError('Alias already exists.')
            nickname = Nicknames(
                nick_id=nick_id,
                slug=slug,
                canonical=alias,
            )
            session.add(nickname)
            session.commit()

    def set_nick_value(self, nick: str, key: str, value: typing.Any) -> None:
        """Set or update a value in the key-value store for ``nick``.

        :param nick: the nickname with which to associate the ``value``
        :param key: the name by which this ``value`` may be accessed later
        :param value: the value to set for this ``key`` under ``nick``
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        The ``value`` can be any of a range of types; it need not be a string.
        It will be serialized to JSON before being stored and decoded
        transparently upon retrieval.

        .. seealso::

            To retrieve a value set with this method, use
            :meth:`get_nick_value`.

            To delete a value set with this method, use
            :meth:`delete_nick_value`.

        """
        value = json.dumps(value, ensure_ascii=False)
        nick_id = self.get_nick_id(nick, create=True)
        with self.session() as session:
            result = session.execute(
                select(NickValues)
                .where(NickValues.nick_id == nick_id)
                .where(NickValues.key == key)
            ).scalar_one_or_none()

            # NickValue exists, update
            if result:
                result.value = value
                session.commit()
            # DNE - Insert
            else:
                new_nickvalue = NickValues(
                    nick_id=nick_id,
                    key=key,
                    value=value,
                )
                session.add(new_nickvalue)
                session.commit()

    def delete_nick_value(self, nick: str, key: str) -> None:
        """Delete a value from the key-value store for ``nick``.

        :param nick: the nickname whose values to modify
        :param key: the name of the value to delete
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. seealso::

            To set a value in the first place, use :meth:`set_nick_value`.

            To retrieve a value instead of deleting it, use
            :meth:`get_nick_value`.

        """
        try:
            nick_id = self.get_nick_id(nick)
        except ValueError:
            # there's nothing to do if the nick doesn't exist
            return

        with self.session() as session:
            result = session.execute(
                select(NickValues)
                .where(NickValues.nick_id == nick_id)
                .where(NickValues.key == key)
            ).scalar_one_or_none()
            # NickValue exists, delete
            if result:
                session.delete(result)
                session.commit()

    def get_nick_value(
        self,
        nick: str,
        key: str,
        default: typing.Optional[typing.Any] = None
    ) -> typing.Optional[typing.Any]:
        """Get a value from the key-value store for ``nick``.

        :param nick: the nickname whose values to access
        :param key: the name by which the desired value was saved
        :param default: value to return if ``key`` does not have a value set
                        (optional)
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. versionadded:: 7.0

            The ``default`` parameter.

        .. seealso::

            To set a value for later retrieval with this method, use
            :meth:`set_nick_value`.

            To delete a value instead of retrieving it, use
            :meth:`delete_nick_value`.

        """
        slug = self.make_identifier(nick).lower()
        with self.session() as session:
            result = session.execute(
                select(NickValues)
                .where(Nicknames.nick_id == NickValues.nick_id)
                .where(Nicknames.slug == slug)
                .where(NickValues.key == key)
            ).scalar_one_or_none()

            if result is not None:
                result = result.value
            elif default is not None:
                result = default

            return _deserialize(result)

    def unalias_nick(self, alias: str) -> None:
        """Remove an alias.

        :param alias: an alias with at least one other nick in its group
        :raise ValueError: if there is not at least one other nick in the
                           group, or the ``alias`` is not known
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. seealso::

            To delete an entire group, use :meth:`forget_nick_group`.

            To *add* an alias for a nick, use :meth:`alias_nick`.

        """
        slug = self.make_identifier(alias).lower()
        nick_id = self.get_nick_id(alias)
        with self.session() as session:
            count = session.scalar(
                select(func.count()).select_from(Nicknames)
                .where(Nicknames.nick_id == nick_id)
            )
            if count <= 1:
                raise ValueError('Given alias is the only entry in its group.')
            session.execute(
                delete(Nicknames)
                .where(Nicknames.slug == slug)
                .execution_options(synchronize_session="fetch")
            )
            session.commit()

    def forget_nick_group(self, nick: str) -> None:
        """Remove a nickname, all of its aliases, and all of its stored values.

        :param nick: one of the nicknames in the group to be deleted
        :raise ValueError: if the ``nick`` does not exist in the database
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. important::

            This is otherwise known as The Nuclear Option. Be *very* sure that
            you want to do this.

        """
        nick_id = self.get_nick_id(nick)
        with self.session() as session:
            session.execute(
                delete(Nicknames)
                .where(Nicknames.nick_id == nick_id)
                .execution_options(synchronize_session="fetch")
            )
            session.execute(
                delete(NickValues)
                .where(NickValues.nick_id == nick_id)
                .execution_options(synchronize_session="fetch")
            )
            session.commit()

    @deprecated(
        version='8.0',
        removed_in='9.0',
        reason="Renamed to `forget_nick_group`",
    )
    def delete_nick_group(self, nick: str) -> None:  # pragma: nocover
        self.forget_nick_group(nick)

    def merge_nick_groups(self, first_nick: str, second_nick: str) -> None:
        """Merge two nick groups.

        :param first_nick: one nick in the first group to merge
        :param second_nick: one nick in the second group to merge
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        Takes two nicks, which may or may not be registered. Unregistered nicks
        will be registered. Keys which are set for only one of the given nicks
        will be preserved. Where both nicks have values for a given key, the
        value set for the ``first_nick`` will be used.

        A nick group can contain one or many nicknames. Groups containing more
        than one nickname can be created with this function, or by using
        :meth:`alias_nick` to add aliases.

        Note that merging of data only applies to the native key-value store.
        Plugins which define their own tables relying on the nick table will
        need to handle their own merging separately.
        """
        first_id = self.get_nick_id(first_nick, create=True)
        second_id = self.get_nick_id(second_nick, create=True)
        with self.session() as session:
            # Get second_id's values
            results = session.execute(
                select(NickValues).where(NickValues.nick_id == second_id)
            ).scalars()

            # Update first_id with second_id values if first_id doesn't have that key
            for row in results:
                first_res = session.execute(
                    select(NickValues)
                    .where(NickValues.nick_id == first_id)
                    .where(NickValues.key == row.key)
                ).scalar_one_or_none()

                if not first_res:
                    self.set_nick_value(
                        first_nick, row.key, _deserialize(row.value))

            session.execute(
                delete(NickValues)
                .where(NickValues.nick_id == second_id)
                .execution_options(synchronize_session="fetch")
            )
            session.execute(
                update(Nicknames)
                .where(Nicknames.nick_id == second_id)
                .values(nick_id=first_id)
                .execution_options(synchronize_session="fetch")
            )
            session.commit()

    # CHANNEL FUNCTIONS

    def get_channel_slug(self, chan: str) -> str:
        """Return the case-normalized representation of ``channel``.

        :param channel: the channel name to normalize, with prefix (required)
        :return: the case-normalized channel name (or "slug" representation)

        This is useful to make sure that a channel name is stored consistently
        in both the bot's own database and third-party plugins'
        databases/files, without regard for variation in case between
        different clients and/or servers on the network.
        """
        slug = self.make_identifier(chan).lower()

        with self.session() as session:
            # Always migrate from old casemapping
            session.execute(
                update(ChannelValues)
                .where(ChannelValues.channel == Identifier._lower_swapped(chan))
                .values(channel=slug)
                .execution_options(synchronize_session="fetch")
            )
            session.commit()

        return slug

    def set_channel_value(
        self,
        channel: str,
        key: str,
        value: typing.Any,
    ) -> None:
        """Set or update a value in the key-value store for ``channel``.

        :param channel: the channel with which to associate the ``value``
        :param key: the name by which this ``value`` may be accessed later
        :param value: the value to set for this ``key`` under ``channel``
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        The ``value`` can be any of a range of types; it need not be a string.
        It will be serialized to JSON before being stored and decoded
        transparently upon retrieval.

        .. seealso::

            To retrieve a value set with this method, use
            :meth:`get_channel_value`.

            To delete a value set with this method, use
            :meth:`delete_channel_value`.

        """
        channel = self.get_channel_slug(channel)
        value = json.dumps(value, ensure_ascii=False)
        with self.session() as session:
            result = session.execute(
                select(ChannelValues)
                .where(ChannelValues.channel == channel)
                .where(ChannelValues.key == key)
            ).scalar_one_or_none()

            # ChannelValue exists, update
            if result:
                result.value = value
                session.commit()
            # DNE - Insert
            else:
                new_channelvalue = ChannelValues(
                    channel=channel,
                    key=key,
                    value=value,
                )
                session.add(new_channelvalue)
                session.commit()

    def delete_channel_value(self, channel: str, key: str) -> None:
        """Delete a value from the key-value store for ``channel``.

        :param channel: the channel whose values to modify
        :param key: the name of the value to delete
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. seealso::

            To set a value in the first place, use :meth:`set_channel_value`.

            To retrieve a value instead of deleting it, use
            :meth:`get_channel_value`.

        """
        channel = self.get_channel_slug(channel)
        with self.session() as session:
            session.execute(
                delete(ChannelValues)
                .where(
                    ChannelValues.channel == channel,
                    ChannelValues.key == key
                ).execution_options(synchronize_session="fetch")
            )
            session.commit()

    def get_channel_value(
        self,
        channel: str,
        key: str,
        default: typing.Optional[typing.Any] = None,
    ) -> typing.Any:
        """Get a value from the key-value store for ``channel``.

        :param channel: the channel whose values to access
        :param key: the name by which the desired value was saved
        :param default: value to return if ``key`` does not have a value set
                        (optional)
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. versionadded:: 7.0

            The ``default`` parameter.

        .. seealso::

            To set a value for later retrieval with this method, use
            :meth:`set_channel_value`.

            To delete a value instead of retrieving it, use
            :meth:`delete_channel_value`.

        """
        channel = self.get_channel_slug(channel)
        with self.session() as session:
            result = session.execute(
                select(ChannelValues)
                .where(ChannelValues.channel == channel)
                .where(ChannelValues.key == key)
            ).scalar_one_or_none()
            if result is not None:
                result = result.value
            elif default is not None:
                result = default
            return _deserialize(result)

    def forget_channel(self, channel: str) -> None:
        """Remove all of a channel's stored values.

        :param channel: the name of the channel for which to delete values
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. important::

            This is a Nuclear Option. Be *very* sure that you want to do it.

        """
        channel = self.get_channel_slug(channel)
        with self.session() as session:
            session.execute(
                delete(ChannelValues)
                .where(ChannelValues.channel == channel)
            )
            session.commit()

    # PLUGIN FUNCTIONS

    def set_plugin_value(
        self,
        plugin: str,
        key: str,
        value: typing.Any,
    ) -> None:
        """Set or update a value in the key-value store for ``plugin``.

        :param plugin: the plugin name with which to associate the ``value``
        :param key: the name by which this ``value`` may be accessed later
        :param value: the value to set for this ``key`` under ``plugin``
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        The ``value`` can be any of a range of types; it need not be a string.
        It will be serialized to JSON before being stored and decoded
        transparently upon retrieval.

        .. seealso::

            To retrieve a value set with this method, use
            :meth:`get_plugin_value`.

            To delete a value set with this method, use
            :meth:`delete_plugin_value`.

        """
        plugin = plugin.lower()
        value = json.dumps(value, ensure_ascii=False)
        with self.session() as session:
            result = session.execute(
                select(PluginValues)
                .where(PluginValues.plugin == plugin)
                .where(PluginValues.key == key)
            ).scalar_one_or_none()
            # PluginValue exists, update
            if result:
                result.value = value
                session.commit()
            # DNE - Insert
            else:
                new_pluginvalue = PluginValues(plugin=plugin, key=key, value=value)
                session.add(new_pluginvalue)
                session.commit()

    def delete_plugin_value(self, plugin: str, key: str) -> None:
        """Delete a value from the key-value store for ``plugin``.

        :param plugin: the plugin name whose values to modify
        :param key: the name of the value to delete
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. seealso::

            To set a value in the first place, use :meth:`set_plugin_value`.

            To retrieve a value instead of deleting it, use
            :meth:`get_plugin_value`.

        """
        plugin = plugin.lower()
        with self.session() as session:
            result = session.execute(
                select(PluginValues)
                .where(PluginValues.plugin == plugin)
                .where(PluginValues.key == key)
            ).scalar_one_or_none()
            # PluginValue exists, update
            if result:
                session.delete(result)
                session.commit()

    def get_plugin_value(
        self,
        plugin: str,
        key: str,
        default: typing.Optional[typing.Any] = None,
    ) -> typing.Optional[typing.Any]:
        """Get a value from the key-value store for ``plugin``.

        :param plugin: the plugin name whose values to access
        :param key: the name by which the desired value was saved
        :param default: value to return if ``key`` does not have a value set
                        (optional)
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. versionadded:: 7.0

            The ``default`` parameter.

        .. seealso::

            To set a value for later retrieval with this method, use
            :meth:`set_plugin_value`.

            To delete a value instead of retrieving it, use
            :meth:`delete_plugin_value`.

        """
        plugin = plugin.lower()
        with self.session() as session:
            result = session.execute(
                select(PluginValues)
                .where(PluginValues.plugin == plugin)
                .where(PluginValues.key == key)
            ).scalar_one_or_none()

            if result is not None:
                result = result.value
            elif default is not None:
                result = default
            return _deserialize(result)

    def forget_plugin(self, plugin: str) -> None:
        """Remove all of a plugin's stored values.

        :param plugin: the name of the plugin for which to delete values
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. important::

            This is a Nuclear Option. Be *very* sure that you want to do it.

        """
        plugin = plugin.lower()
        with self.session() as session:
            session.execute(
                delete(PluginValues).where(PluginValues.plugin == plugin)
            )
            session.commit()

    # NICK AND CHANNEL FUNCTIONS

    def get_nick_or_channel_value(
        self,
        name: str,
        key: str,
        default: typing.Any | None = None
    ) -> typing.Any | None:
        """Get a value from the key-value store for ``name``.

        :param name: nick or channel whose values to access
        :param key: the name by which the desired value was saved
        :param default: value to return if ``key`` does not have a value set
                        (optional)
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        .. versionadded:: 7.0

            The ``default`` parameter.

        This is useful for common logic that is shared between both users and
        channels, as it will fetch the appropriate value based on what type of
        ``name`` it is given.

        .. seealso::

            To get a value for a nick specifically, use :meth:`get_nick_value`.

            To get a value for a channel specifically, use
            :meth:`get_channel_value`.

        """
        if not isinstance(name, Identifier):
            identifier = self.make_identifier(name)
        else:
            identifier = typing.cast('Identifier', name)

        if identifier.is_nick():
            return self.get_nick_value(identifier, key, default)
        else:
            return self.get_channel_value(identifier, key, default)

    def get_preferred_value(
        self,
        names: Iterable[str],
        key: str,
    ) -> typing.Optional[typing.Any]:
        """Get a value for the first name which has it set.

        :param names: a list of channel names and/or nicknames
        :param key: the name by which the desired value was saved
        :return: the value for ``key`` from the first ``name`` which has it set,
                 or ``None`` if none of the ``names`` has it set
        :raise ~sqlalchemy.exc.SQLAlchemyError: if there is a database error

        This is useful for logic that needs to customize its output based on
        settings stored in the database. For example, it can be used to fall
        back from the triggering user's setting to the current channel's setting
        in case the user has not configured their setting.

        .. note::

            This is the only ``get_*_value()`` method that does not support
            passing a ``default``. Try to avoid using it on ``key``\\s which
            might have ``None`` as a valid value, to avoid ambiguous logic.

        """
        for name in names:
            value = self.get_nick_or_channel_value(name, key)
            if value is not None:
                return value

        # Explicit return for type check
        return None
