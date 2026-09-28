import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

const eventText = (event: Record<string, unknown>): string => {
  for (const key of ["detail", "text", "event_type", "status", "source"]) {
    const value = event[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "Recorded event";
};

export const RecentActivitySummary: React.FC<{ activity: HomeCommandCenterModel["recentActivity"] }> = ({ activity }) => (
  <section className="af-home-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Recent</span><h3>Activity</h3></div>
      <span className={`af-authority af-authority-${activity.state.toLowerCase()}`}>{activity.state}</span>
    </header>
    {activity.items === null ? (
      <div className="af-empty-state"><strong>UNAVAILABLE</strong><span>Recent activity authority is unavailable.</span></div>
    ) : activity.items.length === 0 ? (
      <div className="af-empty-state"><strong>No recent activity</strong><span>The authoritative source returned an empty collection.</span></div>
    ) : (
      <div className="af-activity-list">
        {activity.items.slice(0, 6).map((event, index) => (
          <div className="af-activity-row" key={String(event.event_id ?? event.id ?? index)}>
            <span>{eventText(event)}</span>
            <time>{String(event.event_time ?? event.time ?? "Time unavailable")}</time>
          </div>
        ))}
      </div>
    )}
  </section>
);
