"""Sopel's plugin handlers.

.. versionadded:: 7.0

Between a plugin (or "module") and Sopel's core, Plugin Handlers are used. It
is an interface (defined by the :class:`AbstractPluginHandler` abstract class),
that acts as a proxy between Sopel and the plugin, making a clear separation
between how the bot behaves and how the plugins work.

From the :class:`~sopel.bot.Sopel` class, a plugin must be:

* loaded, using :meth:`~AbstractPluginHandler.load`
* setup (if required), using :meth:`~AbstractPluginHandler.setup`
* and eventually registered using :meth:`~AbstractPluginHandler.register`

Each subclass of :class:`AbstractPluginHandler` must implement its methods in
order to be used in the application.

At the moment, three types of plugin are handled:

* :class:`PyModulePlugin`: manages plugins that can be imported as Python
  module from a Python package, i.e. where ``from package import name`` works
* :class:`PyFilePlugin`: manages plugins that are Python files on the filesystem
  or Python directory (with an ``__init__.py`` file inside), that cannot be
  directly imported and extra steps are necessary
* :class:`EntryPointPlugin`: manages plugins that are declared by an entry
  point; it otherwise behaves like a :class:`PyModulePlugin`

All expose the same interface and thereby abstract the internal implementation
away from the rest of the application.

.. important::

    This is all relatively new. Its usage and documentation is for Sopel core
    development and advanced developers. It is subject to rapid changes
    between versions without much (or any) warning.

    Do **not** build your plugin based on what is here, you do **not** need to.

"""
# Copyright 2019, Florian Strzelecki <florian.strzelecki@gmail.com>
#
# Licensed under the Eiffel Forum License 2.
from __future__ import annotations

import abc
import importlib
import importlib.util
import inspect
import itertools
import logging
import os
import sys
from typing import ClassVar, TYPE_CHECKING, TypedDict

from sopel import __version__ as release, loader, plugin as plugin_decorators
from . import exceptions


if TYPE_CHECKING:
    from types import ModuleType

    from importlib_metadata import EntryPoint

    from sopel.bot import Sopel
    from sopel.config import Config


LOGGER = logging.getLogger(__name__)


class PluginMetaDescription(TypedDict):
    """Meta description of a plugin, as a dictionary.

    This dictionary is expected to contain specific keys:

    * name: a short name for the plugin
    * label: a descriptive label for the plugin; see
      :meth:`~sopel.plugins.handlers.AbstractPluginHandler.get_label`
    * type: the plugin's type
    * source: the plugin's source
      (filesystem path, python module/import path, etc.)
    * version: the plugin's version string if available, otherwise ``None``
    """
    name: str
    label: str
    type: str
    source: str
    version: str | None


class AbstractPluginHandler(abc.ABC):
    """Base class for plugin handlers.

    This abstract class defines the interface Sopel uses to
    configure, load, shutdown, etc. a Sopel plugin (or "module").

    It is through this interface that Sopel will interact with its plugins,
    whether internal (from ``sopel.builtins``) or external (from the Python
    files in a directory, to ``sopel_modules.*`` subpackages).

    Sopel's loader will create a "Plugin Handler" for each plugin it finds, to
    which it then delegates loading the plugin, listing its functions
    (commands, jobs, etc.), configuring it, and running any required actions
    on shutdown (either upon exiting Sopel or unloading that plugin).
    """

    name: str
    """Plugin identifier.

    The name of a plugin identifies this plugin: when Sopel loads a plugin,
    it will store its information under that identifier.
    """

    @abc.abstractmethod
    def load(self) -> None:
        """Load the plugin.

        This method must be called first, in order to setup, register, shutdown,
        or configure the plugin later.
        """

    @abc.abstractmethod
    def reload(self) -> None:
        """Reload the plugin.

        This method can be called once the plugin is already loaded. It will
        take care of reloading the plugin from its source.
        """

    @abc.abstractmethod
    def get_label(self) -> str:
        """Retrieve a display label for the plugin.

        :return: a human readable label for display purpose

        This method should, at least, return ``<module_name> plugin``.
        """

    @abc.abstractmethod
    def get_meta_description(self) -> PluginMetaDescription:
        """Retrieve a meta description for the plugin.

        :return: Metadata about the plugin

        The expected keys are detailed in :class:`PluginMetaDescription`.
        """

    @abc.abstractmethod
    def get_version(self) -> str | None:
        """Retrieve the plugin's version.

        :return: the plugin's version string
        """
        raise NotImplementedError

    @abc.abstractmethod
    def is_loaded(self) -> bool:
        """Tell if the plugin is loaded or not.

        :return: ``True`` if the plugin is loaded, ``False`` otherwise

        This must return ``True`` if the :meth:`load` method has been called
        with success.
        """

    @abc.abstractmethod
    def setup(self, bot: Sopel) -> None:
        """Run the plugin's setup action.

        :param bot: instance of Sopel
        """

    @abc.abstractmethod
    def has_setup(self) -> bool:
        """Tell if the plugin has a setup action.

        :return: ``True`` if the plugin has a setup, ``False`` otherwise
        """

    @abc.abstractmethod
    def get_capability_requests(self) -> list[plugin_decorators.capability]:
        """Retrieve the plugin's list of capability requests."""

    @abc.abstractmethod
    def register(self, bot: Sopel) -> None:
        """Register the plugin with the ``bot``.

        :param bot: instance of Sopel
        """

    @abc.abstractmethod
    def unregister(self, bot: Sopel) -> None:
        """Unregister the plugin from the ``bot``.

        :param bot: instance of Sopel
        """

    @abc.abstractmethod
    def shutdown(self, bot: Sopel) -> None:
        """Run the plugin's shutdown action.

        :param bot: instance of Sopel
        """

    @abc.abstractmethod
    def has_shutdown(self) -> bool:
        """Tell if the plugin has a shutdown action.

        :return: ``True`` if the plugin has a ``shutdown`` action, ``False``
                 otherwise
        """

    @abc.abstractmethod
    def configure(self, settings: Config) -> None:
        """Configure Sopel's ``settings`` for this plugin.

        :param settings: Sopel's configuration

        This method will be called by Sopel's configuration wizard.
        """

    @abc.abstractmethod
    def has_configure(self) -> bool:
        """Tell if the plugin has a configure action.

        :return: ``True`` if the plugin has a ``configure`` action, ``False``
                 otherwise
        """


class PyModulePlugin(AbstractPluginHandler):
    """Sopel plugin loaded from a Python module or package.

    A :class:`PyModulePlugin` represents a Sopel plugin that is a Python
    module (or package) that can be imported directly.

    This::

        >>> import sys
        >>> from sopel.plugins.handlers import PyModulePlugin
        >>> plugin = PyModulePlugin('xkcd', 'sopel.builtins')
        >>> plugin.module_name
        'sopel.builtins.xkcd'
        >>> plugin.load()
        >>> plugin.module_name in sys.modules
        True

    Is the same as this::

        >>> import sys
        >>> from sopel.builtins import xkcd
        >>> 'sopel.builtins.xkcd' in sys.modules
        True

    """

    PLUGIN_TYPE: ClassVar[str] = 'python-module'
    """The plugin's type.

    Metadata for the plugin; this should be considered to be a constant and
    should not be modified at runtime.
    """

    package: str | None
    """Dotted path of the plugin's python module's package."""

    module_name: str
    """Name of the python module for this plugin."""

    def __init__(self, name: str, package: str | None = None) -> None:
        self.name = name
        self.package = package
        if package:
            self.module_name = package + '.' + self.name
        else:
            self.module_name = name

        self._module: ModuleType | None = None

    @property
    def module(self) -> ModuleType:
        """Python module represented by this plugin."""
        if self._module is None:
            raise RuntimeError('No module for plugin %s' % self.name)
        return self._module

    def get_label(self) -> str:
        """Retrieve a display label for the plugin.

        :return: a human readable label for display purpose

        By default, this is ``<name> plugin``. If the plugin's module has a
        docstring, its first line is used as the plugin's label.
        """
        default_label = '%s plugin' % self.name

        if not self.is_loaded() or not hasattr(self.module, '__doc__'):
            return default_label

        module_doc = self.module.__doc__ or ""
        lines = inspect.cleandoc(module_doc).splitlines()
        return default_label if not lines else lines[0]

    def get_meta_description(self) -> PluginMetaDescription:
        """Retrieve a meta description for the plugin.

        :return: Metadata about the plugin
        :rtype: :class:`dict`

        The expected keys are detailed in :class:`PluginMetaDescription`.

        This implementation uses its module's dotted import path as the
        ``source`` value::

            {
                'name': 'example',
                'type': 'python-module',
                'label': 'example plugin',
                'source': 'sopel_modules.example',
                'version': '3.1.2',
            }

        """
        return {
            'label': self.get_label(),
            'type': self.PLUGIN_TYPE,
            'name': self.name,
            'source': self.module_name,
            'version': self.get_version(),
        }

    def get_version(self) -> str | None:
        """Retrieve the plugin's version.

        :return: the plugin's version string
        """
        version: str | None = None
        if self.is_loaded() and hasattr(self.module, "__version__"):
            version = str(self.module.__version__)
        elif self.module_name.startswith("sopel."):
            version = release

        return version

    def load(self) -> None:
        """Load the plugin's module using :func:`importlib.import_module`.

        This method assumes the module is available through ``sys.path``.
        """
        self._module = importlib.import_module(self.module_name)

    def reload(self) -> None:
        """Reload the plugin's module using :func:`importlib.reload`.

        This method assumes the plugin is already loaded.
        """
        self._module = importlib.reload(self.module)

    def is_loaded(self) -> bool:
        return self._module is not None

    def setup(self, bot: Sopel) -> None:
        if self.has_setup():
            self.module.setup(bot)

    def has_setup(self) -> bool:
        """Tell if the plugin has a setup action.

        :return: ``True`` if the plugin has a setup, ``False`` otherwise
        :rtype: bool

        The plugin has a setup action if its module has a ``setup`` attribute.
        This attribute is expected to be a callable.
        """
        return hasattr(self.module, 'setup')

    def get_capability_requests(self) -> list[plugin_decorators.capability]:
        return [
            module_attribute
            for module_attribute in vars(self.module).values()
            if isinstance(module_attribute, plugin_decorators.capability)
        ]

    def register(self, bot: Sopel) -> None:
        # capabilities are directly registered
        for cap_request in self.get_capability_requests():
            bot.cap_requests.register(self.name, cap_request)

        # plugin callables go through ``bot.add_plugin``
        callables, jobs, _, urls = loader.clean_module(
            self.module,
            bot.config,
        )

        for part in itertools.chain(callables, jobs, urls):
            # annotate all callables in relevant_parts with `plugin_name`
            # attribute to make per-channel config work; see #1839
            setattr(part, 'plugin_name', self.name)

        bot.register_callables(callables)
        bot.register_jobs(jobs)
        if self.has_shutdown():
            bot.register_shutdowns([self.module.shutdown])
        bot.register_urls(urls)
        bot.store_plugin_handler(self)

    def unregister(self, bot: Sopel) -> None:
        name = self.name
        bot.rules.unregister_plugin(name)
        bot.scheduler.unregister_plugin(name)
        if self.has_shutdown():
            bot.unregister_shutdowns([self.module.shutdown])
        bot.remove_plugin_handler(name)

    def shutdown(self, bot: Sopel) -> None:
        if self.has_shutdown():
            self.module.shutdown(bot)

    def has_shutdown(self) -> bool:
        """Tell if the plugin has a shutdown action.

        :return: ``True`` if the plugin has a ``shutdown`` action, ``False``
                 otherwise
        :rtype: bool

        The plugin has a shutdown action if its module has a ``shutdown``
        attribute. This attribute is expected to be a callable.
        """
        return hasattr(self.module, 'shutdown')

    def configure(self, settings: Config) -> None:
        if self.has_configure():
            self.module.configure(settings)

    def has_configure(self) -> bool:
        """Tell if the plugin has a configure action.

        :return: ``True`` if the plugin has a ``configure`` action, ``False``
                 otherwise
        :rtype: bool

        The plugin has a configure action if its module has a ``configure``
        attribute. This attribute is expected to be a callable.
        """
        return hasattr(self.module, 'configure')


class PyFilePlugin(PyModulePlugin):
    """Sopel plugin loaded from the filesystem outside of the Python path.

    This plugin handler can be used to load a Sopel plugin from the
    filesystem, either a Python ``.py`` file or a directory containing an
    ``__init__.py`` file, and behaves like a :class:`PyModulePlugin`::

        >>> from sopel.plugins.handlers import PyFilePlugin
        >>> plugin = PyFilePlugin('/home/sopel/.sopel/plugins/custom.py')
        >>> plugin.load()
        >>> plugin.name
        'custom'

    In this example, the plugin ``custom`` is loaded from its filename despite
    not being in the Python path.
    """

    PLUGIN_TYPE: ClassVar[str] = 'python-file'
    """The plugin's type.

    Metadata for the plugin; this should be considered to be a constant and
    should not be modified at runtime.
    """

    def __init__(self, filename: str):
        good_file = (
            os.path.isfile(filename) and
            filename.endswith('.py') and not filename.startswith('_')
        )
        good_dir = (
            os.path.isdir(filename) and
            os.path.isfile(os.path.join(filename, '__init__.py'))
        )

        if good_file:
            name = os.path.basename(filename)[:-3]
            spec = importlib.util.spec_from_file_location(
                name,
                filename,
            )
        elif good_dir:
            name = os.path.basename(filename)
            spec = importlib.util.spec_from_file_location(
                name,
                os.path.join(filename, '__init__.py'),
                submodule_search_locations=[filename],
            )
        else:
            raise exceptions.PluginError('Invalid Sopel plugin: %s' % filename)

        if spec is None:
            raise exceptions.PluginError('Could not determine spec for plugin: %s' % filename)

        self.filename = filename
        self.path = filename
        self.module_spec = spec

        super().__init__(name)

    def _load(self) -> ModuleType:
        module = importlib.util.module_from_spec(self.module_spec)
        if not self.module_spec.loader:
            raise exceptions.PluginError('Could not determine loader for plugin: %s' % self.filename)
        sys.modules[self.name] = module
        self.module_spec.loader.exec_module(module)
        return module

    def get_meta_description(self) -> PluginMetaDescription:
        """Retrieve a meta description for the plugin.

        :return: Metadata about the plugin
        :rtype: :class:`dict`

        The expected keys are detailed in :class:`PluginMetaDescription`.

        This implementation uses its source file's path as the ``source``
        value::

            {
                'name': 'example',
                'type': 'python-file',
                'label': 'example plugin',
                'source': '/home/username/.sopel/plugins/example.py',
                'version': '3.1.2',
            }

        """
        data = super().get_meta_description()
        data.update({
            'source': self.path,
        })
        return data

    def load(self) -> None:
        self._module = self._load()

    def reload(self) -> None:
        """Reload the plugin.

        Unlike :class:`PyModulePlugin`, it is not possible to use the
        ``reload`` function (either from `imp` or `importlib`), because the
        module might not be available through ``sys.path``.
        """
        self._module = self._load()


class EntryPointPlugin(PyModulePlugin):
    """Sopel plugin loaded from an entry point.

    :param entry_point: an entry point object

    This handler loads a Sopel plugin exposed by a package's entry point. It
    expects to be able to load a module object from the entry point, and to
    work as a :class:`~.PyModulePlugin` from that module.

    By default, Sopel searches within the entry point group ``sopel.plugins``.
    To use that for their own plugins, developers must define an entry point
    either in their ``setup.py`` file or their ``setup.cfg`` file::

        # in setup.py file
        setup(
            name='my_plugin',
            version='1.0',
            entry_points={
                'sopel.plugins': [
                    'custom = my_plugin.path.to.plugin',
                ],
            }
        )

    And this plugin can be loaded with::

        >>> from importlib_metadata import entry_points
        >>> from sopel.plugins.handlers import EntryPointPlugin
        >>> plugin = [
        ...     EntryPointPlugin(ep)
        ...     for ep in entry_points(group='sopel.plugins', name='custom')
        ... ][0]
        >>> plugin.load()
        >>> plugin.name
        'custom'

    In this example, the plugin ``custom`` is loaded from an entry point.
    Unlike the :class:`~.PyModulePlugin`, the name is not derived from the
    actual Python module, but from its entry point's name.

    .. seealso::

        Sopel uses the :func:`~sopel.plugins.find_entry_point_plugins` function
        internally to search entry points.

        Entry points are a `standard packaging mechanism`__ for Python, used by
        other applications (such as ``pytest``) for their plugins.

        The ``importlib_metadata`` backport package is used for consistency
        across all of Sopel's supported Python versions. Its API matches that
        of :mod:`importlib.metadata` from Python 3.10 and up; Sopel will drop
        this external requirement when practical.

        .. __: https://packaging.python.org/en/latest/specifications/entry-points/

    """

    PLUGIN_TYPE: ClassVar[str] = 'setup-entrypoint'
    """The plugin's type.

    Metadata for the plugin; this should be considered to be a constant and
    should not be modified at runtime.
    """

    def __init__(self, entry_point: EntryPoint):
        self.entry_point: EntryPoint = entry_point
        super().__init__(entry_point.name)

    def load(self) -> None:
        self._module = self.entry_point.load()

    def get_version(self) -> str | None:
        """Retrieve the plugin's version.

        :return: the plugin's version string
        """
        version: str | None = super().get_version()

        if (
            version is None
            and hasattr(self.entry_point, "dist")
            and hasattr(self.entry_point.dist, "name")
        ):
            dist_name = self.entry_point.dist.name
            try:
                version = importlib.metadata.version(dist_name)
            except (ValueError, importlib.metadata.PackageNotFoundError):
                LOGGER.warning("Cannot determine version of %r", dist_name)
            except Exception:
                LOGGER.warning(
                    "Unexpected error occurred while checking the version of %r",
                    dist_name,
                    exc_info=True,
                )

        return version

    def get_meta_description(self) -> PluginMetaDescription:
        """Retrieve a meta description for the plugin.

        :return: Metadata about the plugin
        :rtype: :class:`dict`

        The expected keys are detailed in :class:`PluginMetaDescription`.

        This implementation uses its entry point definition as the ``source``
        value::

            {
                'name': 'example',
                'type': 'setup-entrypoint',
                'label': 'example plugin',
                'source': 'example = my_plugin.example',
                'version': '3.1.2',
            }

        """
        data = super().get_meta_description()
        data.update({
            'source': self.entry_point.name + ' = ' + self.entry_point.value,
        })
        return data
