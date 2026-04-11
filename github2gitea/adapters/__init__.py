from .github    import GitHubAdapter
from .gitea     import GiteaAdapter
from .gitlab    import GitLabAdapter
from .bitbucket import BitbucketAdapter
from .forgejo   import ForgejoAdapter
from .base      import BaseAdapter

_REGISTRY = {
    "github":    GitHubAdapter,
    "gitea":     GiteaAdapter,
    "gitlab":    GitLabAdapter,
    "bitbucket": BitbucketAdapter,
    "forgejo":   ForgejoAdapter,
}

VALID_PLATFORMS = list(_REGISTRY.keys())


def get_adapter(platform: str, config: dict) -> BaseAdapter:
    if platform not in _REGISTRY:
        raise ValueError(
            f"Unknown platform: {platform!r}. Choices: {list(_REGISTRY)}"
        )
    return _REGISTRY[platform](config=config)
