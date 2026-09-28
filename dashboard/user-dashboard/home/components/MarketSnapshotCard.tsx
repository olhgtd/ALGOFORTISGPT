import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

type Market = HomeCommandCenterModel["markets"][number];

const formatPrice = (price: number | null) => price === null
  ? "UNAVAILABLE"
  : new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(price);

export const MarketSnapshotCard: React.FC<{ market: Market }> = ({ market }) => (
  <article className="af-home-card af-market-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Market</span><h3>{market.symbol}</h3></div>
      <span className={`af-authority af-authority-${market.state.toLowerCase()}`}>{market.state}</span>
    </header>
    <div className={`af-market-price ${market.price === null ? "af-market-price-unavailable" : ""}`}>{formatPrice(market.price)}</div>
    <div className="af-home-meta">
      <span>{market.asOf ? `As of ${market.asOf}` : "Timestamp unavailable"}</span>
      <span>{market.source ?? "Authority unavailable"}</span>
    </div>
  </article>
);
