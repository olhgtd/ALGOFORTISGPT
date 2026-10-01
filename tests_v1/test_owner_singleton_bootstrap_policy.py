from dashboard.backend.account_v2.owner_bootstrap import (
    OwnerEntryFlow,
    OwnerPresence,
    resolve_owner_bootstrap,
)


def test_existing_local_owner_routes_to_login_and_never_setup() -> None:
    decision = resolve_owner_bootstrap(
        local_owner_initialized=True,
        roaming_identity_configured=False,
        production=False,
    )
    assert decision.presence is OwnerPresence.LOCAL_EXISTS
    assert decision.flow is OwnerEntryFlow.LOCAL_LOGIN
    assert decision.setup_allowed is False


def test_fresh_pc_with_no_central_authority_fails_closed_not_owner_setup() -> None:
    decision = resolve_owner_bootstrap(
        local_owner_initialized=False,
        roaming_identity_configured=False,
        production=False,
    )
    assert decision.presence is OwnerPresence.UNKNOWN
    assert decision.flow is OwnerEntryFlow.UNAVAILABLE
    assert decision.setup_allowed is False


def test_fresh_pc_with_roaming_authority_routes_to_returning_login() -> None:
    decision = resolve_owner_bootstrap(
        local_owner_initialized=False,
        roaming_identity_configured=True,
        production=True,
    )
    assert decision.flow is OwnerEntryFlow.RETURNING_USER
    assert decision.setup_allowed is False


def test_explicit_nonproduction_bootstrap_is_the_only_local_setup_escape_hatch() -> None:
    decision = resolve_owner_bootstrap(
        local_owner_initialized=False,
        roaming_identity_configured=False,
        explicit_trusted_local_bootstrap=True,
        production=False,
    )
    assert decision.presence is OwnerPresence.ABSENT_CONFIRMED
    assert decision.flow is OwnerEntryFlow.LOCAL_OWNER_SETUP
    assert decision.setup_allowed is True


def test_production_never_accepts_local_bootstrap_override() -> None:
    decision = resolve_owner_bootstrap(
        local_owner_initialized=False,
        roaming_identity_configured=False,
        explicit_trusted_local_bootstrap=True,
        production=True,
    )
    assert decision.flow is OwnerEntryFlow.UNAVAILABLE
    assert decision.setup_allowed is False
