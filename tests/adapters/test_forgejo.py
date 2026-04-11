from github2gitea.adapters.forgejo import ForgejoAdapter
from github2gitea.adapters.gitea import GiteaAdapter


def test_forgejo_instantiation():
    adapter = ForgejoAdapter(config={"url": "http://forgejo:3000", "token": "fake-token"})
    assert adapter is not None


def test_forgejo_platform_name():
    adapter = ForgejoAdapter(config={"url": "http://forgejo:3000", "token": "fake-token"})
    assert adapter.platform_name == "forgejo"


def test_forgejo_inherits_create_mirror():
    adapter = ForgejoAdapter(config={"url": "http://forgejo:3000", "token": "fake-token"})
    # create_mirror should be inherited from GiteaAdapter, not overridden
    assert adapter.create_mirror is not None
    assert adapter.create_mirror == GiteaAdapter.create_mirror.__get__(adapter, ForgejoAdapter)


def test_forgejo_prepare_destination_callable():
    adapter = ForgejoAdapter(config={"url": "http://forgejo:3000", "token": "fake-token"})
    assert callable(adapter.prepare_destination)
