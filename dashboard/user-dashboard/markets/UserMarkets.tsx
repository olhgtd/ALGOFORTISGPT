import React, { useEffect, useMemo, useState } from "react";
import { queryMarketChart } from "../../shared/services/integrationClient";
import { MarketsChart } from "./MarketsChart";
import { loadMarketsOverview, type MarketsOverview } from "./marketsData";
import {
  deriveMarketSnapshot,
  MARKET_INSTRUMENTS,
  marketStateLabel,
  optionChainAuthority,
  type MarketInstrumentId,
  type MarketSnapshotModel,
  type MarketsAuthorityState,
} from "./marketsModel";
import "./markets.css";

type MarketQuery = typeof queryMarketChart;

export interface UserMarketsProps {
  theme: "dark" | "light";
  queryMarket?: MarketQuery;
}

const initialOverview = (): MarketsOverview => ({
  NIFTY: deriveMarketSnapshot("LOADING", []),
  BANKNIFTY: deriveMarketSnapshot("LOADING", []),
});

const formatNumber = (value: number | null, digits = 2) => value === null
  ? "—"
  : value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const formatSigned = (value: number | null, digits = 2) => {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
};

const tone = (value: number | null) => value === null ? "neutral" : value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
const authorityClass = (state: MarketsAuthorityState): string =>
  state === "AVAILABLE" ? "available" : state === "STALE" ? "stale" : state === "LOADING" ? "unknown" : "unavailable";

const OverviewCard: React.FC<{
  id: MarketInstrumentId;
  snapshot: MarketSnapshotModel;
  active: boolean;
  onSelect: () => void;
}> = ({ id, snapshot, active, onSelect }) => {
  const meta = MARKET_INSTRUMENTS.find((item) => item.id === id) ?? MARKET_INSTRUMENTS[0];
  return (
    <button type="button" className={`af-market-overview-card ${active ? "active" : ""}`} onClick={onSelect}>
      <div className="af-market-overview-head">
        <div>
          <span>{meta.exchange}</span>
          <strong>{meta.label}</strong>
        </div>
        <span className={`af-authority af-authority-${authorityClass(snapshot.state)}`}>
          {marketStateLabel(snapshot.state)}
        </span>
      </div>
      <div className="af-market-overview-value">{formatNumber(snapshot.price)}</div>
      <div className={`af-market-overview-change af-market-tone-${tone(snapshot.change)}`}>
        {formatSigned(snapshot.change)} {snapshot.changePct === null ? "" : `(${formatSigned(snapshot.changePct)}%)`}
      </div>
      <div className="af-market-overview-foot">Last bar · {snapshot.asOf ?? "time unavailable"}</div>
      {snapshot.state === "STALE" && <div className="af-markets-note">STALE — context only</div>}
    </button>
  );
};

export const UserMarkets: React.FC<UserMarketsProps> = ({ theme, queryMarket = queryMarketChart }) => {
  const [selected, setSelected] = useState<MarketInstrumentId>("NIFTY");
  const [overview, setOverview] = useState<MarketsOverview>(initialOverview);

  useEffect(() => {
    let active = true;
    setOverview(initialOverview());
    loadMarketsOverview(queryMarket).then((result) => {
      if (active) setOverview(result);
    });
    return () => { active = false; };
  }, [queryMarket]);

  const selectedSnapshot = overview[selected];
  const selectedMeta = useMemo(
    () => MARKET_INSTRUMENTS.find((item) => item.id === selected) ?? MARKET_INSTRUMENTS[0],
    [selected],
  );

  return (
    <div className="af-markets" data-testid="markets-surface">
      <header className="af-markets-header">
        <div>
          <span className="af-eyebrow">Market Intelligence</span>
          <h1>Markets</h1>
          <p>Canonical index data, read-only charting, and explicit authority states. No execution authority is granted from this surface.</p>
        </div>
        <div className="af-markets-readonly-badge">
          <span>Surface</span>
          <strong>READ ONLY</strong>
        </div>
      </header>

      <section className="af-market-overview-grid" aria-label="Index market overview">
        {MARKET_INSTRUMENTS.map((item) => (
          <OverviewCard
            key={item.id}
            id={item.id}
            snapshot={overview[item.id]}
            active={selected === item.id}
            onSelect={() => setSelected(item.id)}
          />
        ))}
      </section>

      <div className="af-markets-primary-grid">
        <MarketsChart instrument={selected} theme={theme} queryMarket={queryMarket} />

        <aside className="af-markets-side-stack">
          <section className="af-markets-panel">
            <div className="af-markets-panel-head">
              <div>
                <span className="af-eyebrow">Selected Market</span>
                <h2>{selectedMeta.label}</h2>
              </div>
              <span className={`af-authority af-authority-${authorityClass(selectedSnapshot.state)}`}>
                {marketStateLabel(selectedSnapshot.state)}
              </span>
            </div>
            <dl className="af-markets-stat-grid">
              <div><dt>Open</dt><dd>{formatNumber(selectedSnapshot.open)}</dd></div>
              <div><dt>High</dt><dd>{formatNumber(selectedSnapshot.high)}</dd></div>
              <div><dt>Low</dt><dd>{formatNumber(selectedSnapshot.low)}</dd></div>
              <div><dt>Last</dt><dd>{formatNumber(selectedSnapshot.price)}</dd></div>
              <div><dt>Volume</dt><dd>{selectedSnapshot.volume === null ? "—" : selectedSnapshot.volume.toLocaleString("en-IN")}</dd></div>
              <div><dt>As of</dt><dd>{selectedSnapshot.asOf ?? "—"}</dd></div>
            </dl>
            <p className="af-markets-note">Values are derived only from canonical 5-minute candles. STALE values remain labelled STALE; missing authority never falls back to sample market values.</p>
          </section>

          <section className="af-markets-panel af-markets-authority-panel">
            <span className="af-eyebrow">Authority Map</span>
            <h2>What this page can do</h2>
            <div className="af-market-authority-row">
              <span>Index candles</span><strong>Canonical backend read</strong>
            </div>
            <div className="af-market-authority-row">
              <span>Option-chain quotes</span><strong>Unavailable</strong>
            </div>
            <div className="af-market-authority-row">
              <span>Order execution</span><strong>None</strong>
            </div>
            <div className="af-market-authority-row">
              <span>Options policy</span><strong>BUY-only constraint preserved</strong>
            </div>
          </section>
        </aside>
      </div>

      <section className="af-option-chain-panel" aria-label="Option Chain">
        <div className="af-option-chain-head">
          <div>
            <span className="af-eyebrow">Derivatives</span>
            <h2>Option Chain</h2>
          </div>
          <span className="af-authority af-authority-unavailable">{optionChainAuthority.state}</span>
        </div>
        <div className="af-option-chain-unavailable">
          <div className="af-option-chain-lock">OC</div>
          <div>
            <strong>Authoritative option-chain feed is not attached</strong>
            <p>{optionChainAuthority.detail}</p>
            <span>No generated CE/PE prices, estimated Greeks, or sample strikes are exposed on the finished user surface.</span>
          </div>
        </div>
      </section>
    </div>
  );
};
