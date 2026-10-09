import pytest

from runbook_copilot.ingest.fetch import _validate
from runbook_copilot.ingest.sources import Source


def _src(**kw):
    base = {"id": "x", "license": "MIT", "url_base": "u", "repo": "https://github.com/a/b.git", "commit": "a" * 40, "paths": ["docs/"]}
    base.update(kw)
    return Source(**base)


def test_valid_source_passes():
    _validate(_src())


@pytest.mark.parametrize("kw", [
    {"commit": "main"}, {"commit": "--upload-pack=evil"}, {"commit": "A" * 40}, {"commit": None},
    {"repo": "git@github.com:a/b.git"}, {"repo": "--help"}, {"paths": ["-rf"]},
])
def test_unsafe_source_rejected(kw):
    with pytest.raises(ValueError):
        _validate(_src(**kw))
