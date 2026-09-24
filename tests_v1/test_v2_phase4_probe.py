from build.tools.phase4_probe import run


def test_probe_is_reproducible():
    assert run() == run()
