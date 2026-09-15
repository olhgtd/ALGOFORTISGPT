"""SQLite V7 Schema and PRAGMA Definitions for Phase-5/6 Paper State Store."""

from __future__ import annotations

SCHEMA_VERSION: int = 7

PRAGMA_STATEMENTS: tuple[str, ...] = (
    "PRAGMA foreign_keys = ON;",
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = FULL;",
    "PRAGMA busy_timeout = 5000;",
)

CREATE_TABLES_SQL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS paper_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS account_state (
        account_id TEXT PRIMARY KEY,
        currency TEXT NOT NULL,
        monetary_quantum TEXT NOT NULL,
        starting_capital TEXT NOT NULL,
        cash TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        aggregate_exposure TEXT NOT NULL,
        as_of_timestamp TEXT NOT NULL,
        accounting_sequence INTEGER NOT NULL,
        accounting_integrity_breached INTEGER NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS positions (
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        instrument_key TEXT NOT NULL,
        identity_json TEXT NOT NULL,
        quantity TEXT NOT NULL,
        average_entry_price TEXT NOT NULL,
        contract_multiplier TEXT NOT NULL,
        mark_price TEXT,
        mark_timestamp TEXT,
        valuation_timeframe TEXT NOT NULL,
        price_increment TEXT NOT NULL,
        monetary_quantum TEXT NOT NULL,
        PRIMARY KEY (strategy_id, strategy_version, instrument_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS premium_commitments (
        reservation_key TEXT PRIMARY KEY,
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        instrument_key TEXT NOT NULL,
        identity_json TEXT NOT NULL,
        approved_quantity TEXT NOT NULL,
        worst_permitted_fill_price TEXT NOT NULL,
        contract_multiplier TEXT NOT NULL,
        required_cash TEXT NOT NULL,
        market_time TEXT NOT NULL,
        nominal_stop_risk TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS broker_orders (
        order_id TEXT PRIMARY KEY,
        broker_order_identity TEXT NOT NULL UNIQUE,
        entry_intent_identity TEXT,
        action TEXT NOT NULL,
        order_type TEXT NOT NULL,
        quantity TEXT NOT NULL,
        limit_price TEXT,
        stop_price TEXT,
        time_in_force TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL,
        submission_market_timestamp TEXT NOT NULL,
        eligibility_timestamp TEXT NOT NULL,
        reference_price TEXT NOT NULL,
        price_increment TEXT NOT NULL,
        stop_triggered INTEGER NOT NULL DEFAULT 0,
        stop_limit_activated INTEGER NOT NULL DEFAULT 0,
        stop_limit_activation_timestamp TEXT,
        stop_limit_activation_price TEXT,
        instrument_identity_json TEXT NOT NULL,
        specification_json TEXT NOT NULL,
        original_order_json TEXT NOT NULL,
        terminal_market_timestamp TEXT,
        terminal_reason TEXT,
        execution_result_json TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS broker_watermarks (
        instrument_key TEXT PRIMARY KEY,
        last_exchange_timestamp TEXT NOT NULL,
        identity_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entry_intents (
        intent_id TEXT PRIMARY KEY,
        lifecycle_state TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS retained_protective_plans (
        order_id TEXT PRIMARY KEY,
        plan_json TEXT NOT NULL,
        quantity TEXT NOT NULL,
        run_identity TEXT,
        FOREIGN KEY (order_id) REFERENCES broker_orders (order_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS protective_exits (
        protective_id TEXT PRIMARY KEY,
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        instrument_key TEXT NOT NULL,
        identity_json TEXT NOT NULL,
        kind TEXT NOT NULL,
        state TEXT NOT NULL,
        quantity TEXT NOT NULL,
        oco_group_id TEXT,
        stop_price TEXT,
        target_price TEXT,
        trailing_current_stop TEXT,
        trailing_reference_extreme TEXT,
        trailing_activated INTEGER NOT NULL DEFAULT 0,
        trailing_effective_after TEXT,
        termination_reason TEXT,
        exit_order_json TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS protective_pending_closes (
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        instrument_key TEXT NOT NULL,
        order_id TEXT NOT NULL UNIQUE,
        broker_order_identity TEXT NOT NULL,
        protective_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        trigger_price TEXT NOT NULL,
        trigger_timestamp TEXT NOT NULL,
        PRIMARY KEY (strategy_id, strategy_version, instrument_key),
        FOREIGN KEY (order_id) REFERENCES broker_orders (order_id),
        FOREIGN KEY (protective_id) REFERENCES protective_exits (protective_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_records (
        trade_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        currency TEXT NOT NULL,
        monetary_quantum TEXT NOT NULL,
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        instrument_key TEXT NOT NULL,
        identity_json TEXT NOT NULL,
        direction TEXT NOT NULL,
        entry_timestamp TEXT NOT NULL,
        exit_timestamp TEXT NOT NULL,
        duration_seconds TEXT NOT NULL,
        entry_quantity TEXT NOT NULL,
        exit_quantity TEXT NOT NULL,
        average_entry_price TEXT NOT NULL,
        contract_multiplier TEXT NOT NULL,
        gross_realized_pnl TEXT NOT NULL,
        status TEXT NOT NULL,
        opening_event_key TEXT NOT NULL,
        closing_event_key TEXT NOT NULL,
        provenance TEXT,
        record_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_pending_lifecycles (
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        instrument_key TEXT NOT NULL,
        opening_event_key TEXT NOT NULL,
        entries_json TEXT NOT NULL,
        exits_json TEXT NOT NULL,
        PRIMARY KEY (strategy_id, strategy_version, instrument_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_legs (
        event_key TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        execution_timestamp TEXT NOT NULL,
        price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        realized_pnl_delta TEXT NOT NULL,
        leg_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_processed (
        event_key TEXT PRIMARY KEY,
        trade_id TEXT,
        result_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS cost_assessments (
        assessment_id TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL,
        total_cost TEXT NOT NULL,
        assessment_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_gate_state (
        calendar_identity TEXT NOT NULL,
        session_date TEXT NOT NULL,
        start_of_day_net_equity TEXT NOT NULL,
        current_net_equity TEXT NOT NULL,
        daily_trade_count INTEGER NOT NULL,
        filled_entry_identities_json TEXT NOT NULL,
        PRIMARY KEY (calendar_identity, session_date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS processed_fills (
        broker_order_identity TEXT PRIMARY KEY,
        order_id TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL,
        instrument_key TEXT NOT NULL,
        fill_price TEXT NOT NULL,
        filled_quantity TEXT NOT NULL,
        fee TEXT NOT NULL,
        fill_timestamp TEXT NOT NULL,
        semantic_fingerprint TEXT NOT NULL,
        event_json TEXT NOT NULL,
        result_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS safety_state (
        account_id TEXT PRIMARY KEY,
        kill_switch_active INTEGER NOT NULL CHECK(kill_switch_active IN (0, 1)),
        kill_switch_reason TEXT,
        activation_source TEXT,
        activation_market_timestamp TEXT,
        activated_at TEXT,
        FOREIGN KEY (account_id) REFERENCES account_state (account_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        audit_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        event_schema_version TEXT NOT NULL,
        event_family TEXT NOT NULL,
        event_type TEXT NOT NULL,
        aggregate_type TEXT NOT NULL,
        aggregate_identity TEXT NOT NULL,
        market_timestamp TEXT,
        recorded_at_utc TEXT NOT NULL,
        state_generation INTEGER,
        transaction_event_ordinal INTEGER NOT NULL CHECK(transaction_event_ordinal >= 0),
        correlation_id TEXT,
        causation_event_id TEXT,
        strategy_id TEXT,
        strategy_version TEXT,
        instrument_key TEXT,
        position_key_json TEXT,
        entry_intent_identity TEXT,
        broker_order_identity TEXT,
        trade_id TEXT,
        protective_id TEXT,
        payload_version TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        environment TEXT NOT NULL,
        run_id TEXT NOT NULL,
        canonical_configuration_fingerprint TEXT NOT NULL,
        source_identity TEXT NOT NULL,
        timeframe TEXT,
        status TEXT NOT NULL,
        severity TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_events_event_type ON audit_events (event_type);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_events_aggregate ON audit_events (aggregate_type, aggregate_identity);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_events_correlation ON audit_events (correlation_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_events_market_ts ON audit_events (market_timestamp);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_events_broker_order ON audit_events (broker_order_identity);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_events_trade_id ON audit_events (trade_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_events_protective_id ON audit_events (protective_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_trade_records_strat ON trade_records (strategy_id, strategy_version);
    """,
    """
    CREATE TABLE IF NOT EXISTS reconciliation_reports (
        report_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        paper_session_id TEXT NOT NULL,
        checked_state_generation INTEGER NOT NULL,
        status TEXT NOT NULL,
        critical_count INTEGER NOT NULL,
        warning_count INTEGER NOT NULL,
        info_count INTEGER NOT NULL,
        evaluated_at_market_time TEXT,
        evaluated_at_utc TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS reconciliation_findings (
        finding_id TEXT PRIMARY KEY,
        report_id TEXT NOT NULL,
        finding_key TEXT NOT NULL,
        finding_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        aggregate_type TEXT NOT NULL,
        aggregate_identity TEXT NOT NULL,
        market_timestamp TEXT,
        expected_json TEXT NOT NULL,
        observed_json TEXT NOT NULL,
        details_json TEXT NOT NULL,
        FOREIGN KEY (report_id) REFERENCES reconciliation_reports (report_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reconciliation_reports_generation ON reconciliation_reports (checked_state_generation);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reconciliation_findings_report ON reconciliation_findings (report_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reconciliation_findings_key ON reconciliation_findings (finding_key);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reconciliation_findings_aggregate ON reconciliation_findings (aggregate_type, aggregate_identity);
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_states (
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        paper_session_id TEXT NOT NULL,
        configuration_identity TEXT NOT NULL,
        codec_version TEXT NOT NULL,
        state_json TEXT NOT NULL,
        state_fingerprint TEXT NOT NULL,
        last_evaluated_decision_time TEXT,
        state_generation INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (strategy_id, strategy_version)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_strategy_states_session ON strategy_states (paper_session_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS promotion_tracking_state (
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        paper_session_id TEXT NOT NULL,
        configuration_identity TEXT NOT NULL,
        upstream_promotion_fingerprint TEXT,
        tracking_status TEXT NOT NULL,
        activated_at TEXT,
        window_start_date TEXT,
        clean_days_count INTEGER NOT NULL,
        disqualified_days_count INTEGER NOT NULL,
        last_evaluated_session_date TEXT,
        milestone_status TEXT NOT NULL,
        state_generation INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (strategy_id, strategy_version)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_promotion_tracking_session ON promotion_tracking_state (paper_session_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS promotion_session_records (
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        session_date TEXT NOT NULL,
        paper_session_id TEXT NOT NULL,
        configuration_identity TEXT NOT NULL,
        upstream_promotion_fingerprint TEXT,
        session_status TEXT NOT NULL,
        reasons_json TEXT NOT NULL,
        record_schema_version TEXT NOT NULL,
        record_fingerprint TEXT NOT NULL,
        recorded_at_utc TEXT NOT NULL,
        PRIMARY KEY (strategy_id, strategy_version, session_date)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_promotion_session_date ON promotion_session_records (session_date);
    """,
)

