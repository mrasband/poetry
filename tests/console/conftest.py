import os
import pytest
import shutil

try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse

from tomlkit import document

from poetry.config import Config as BaseConfig
from poetry.console import Application as BaseApplication
from poetry.installation.noop_installer import NoopInstaller
from poetry.poetry import Poetry as BasePoetry
from poetry.packages import Locker as BaseLocker
from poetry.repositories import Pool
from poetry.repositories import Repository
from poetry.utils._compat import Path
from poetry.utils.env import Env
from poetry.utils.env import MockEnv
from poetry.utils.toml_file import TomlFile


@pytest.fixture()
def installer():
    return NoopInstaller()


def mock_clone(self, source, dest):
    # Checking source to determine which folder we need to copy
    parts = urlparse.urlparse(source)

    folder = (
        Path(__file__).parent.parent
        / "fixtures"
        / "git"
        / parts.netloc
        / parts.path.lstrip("/").rstrip(".git")
    )

    shutil.rmtree(str(dest))
    shutil.copytree(str(folder), str(dest))


@pytest.fixture
def installed():
    return Repository()


@pytest.fixture(autouse=True)
def setup(mocker, installer, installed):
    Env._env = MockEnv(path=Path("/prefix"), base=Path("/base/prefix"), is_venv=True)

    # Set Installer's installer
    p = mocker.patch("poetry.installation.installer.Installer._get_installer")
    p.return_value = installer

    p = mocker.patch("poetry.installation.installer.Installer._get_installed")
    p.return_value = installed

    p = mocker.patch(
        "poetry.repositories.installed_repository.InstalledRepository.load"
    )
    p.return_value = installed

    # Patch git module to not actually clone projects
    mocker.patch("poetry.vcs.git.Git.clone", new=mock_clone)
    mocker.patch("poetry.vcs.git.Git.checkout", new=lambda *_: None)
    p = mocker.patch("poetry.vcs.git.Git.rev_parse")
    p.return_value = "9cf87a285a2d3fbb0b9fa621997b3acc3631ed24"

    # Setting terminal width
    environ = dict(os.environ)
    os.environ["COLUMNS"] = "80"

    yield

    os.environ.clear()
    os.environ.update(environ)
    Env._env = None


class Application(BaseApplication):
    def __init__(self, poetry):
        super(Application, self).__init__()

        self._poetry = poetry

    def reset_poetry(self):
        poetry = self._poetry
        self._poetry = Poetry.create(self._poetry.file.path.parent)
        self._poetry._pool = poetry.pool


class Config(BaseConfig):
    def __init__(self, _):
        self._content = document()


class Locker(BaseLocker):
    def __init__(self, lock, local_config):
        self._lock = TomlFile(lock)
        self._local_config = local_config
        self._lock_data = None
        self._content_hash = self._get_content_hash()
        self._locked = False
        self._lock_data = None

    def is_locked(self):
        return self._locked

    def locked(self, is_locked=True):
        self._locked = is_locked

        return self

    def mock_lock_data(self, data):
        self.locked()

        self._lock_data = data

    def is_fresh(self):
        return True

    def _write_lock_data(self, data):
        self._lock_data = None


class Poetry(BasePoetry):
    def __init__(self, file, local_config, package, locker):
        self._file = TomlFile(file)
        self._package = package
        self._local_config = local_config
        self._locker = Locker(locker.lock.path, locker._local_config)
        self._config = Config.create("config.toml")

        # Configure sources
        self._pool = Pool()


@pytest.fixture
def repo():
    return Repository()


@pytest.fixture
def poetry(repo):
    p = Poetry.create(Path(__file__).parent.parent / "fixtures" / "simple_project")

    with p.file.path.open() as f:
        content = f.read()

    p.pool.remove_repository("pypi")
    p.pool.add_repository(repo)

    yield p

    with p.file.path.open("w") as f:
        f.write(content)


@pytest.fixture
def app(poetry):
    return Application(poetry)
