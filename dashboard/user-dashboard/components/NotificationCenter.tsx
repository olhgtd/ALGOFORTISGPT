import React from "react";

export type NotificationPriority = "Critical" | "Action Required" | "Important" | "Info";

export interface UserNotification {
  id: string;
  priority: NotificationPriority;
  title: string;
  detail?: string;
  asOf?: string;
}

export interface NotificationCenterProps {
  open: boolean;
  notifications: readonly UserNotification[];
  onClose: () => void;
}

export const NotificationCenter: React.FC<NotificationCenterProps> = ({ open, notifications, onClose }) => {
  if (!open) return null;

  return (
    <div className="af-notification-layer" data-testid="notification-center" role="presentation">
      <button className="af-notification-backdrop" aria-label="Close notifications" onClick={onClose} />
      <aside className="af-notification-panel" role="dialog" aria-modal="true" aria-label="Notifications">
        <header className="af-notification-head">
          <div>
            <span className="af-eyebrow">Attention Center</span>
            <h2>Notifications</h2>
          </div>
          <button className="af-icon-button" type="button" onClick={onClose} aria-label="Close notifications">×</button>
        </header>
        <div className="af-notification-list">
          {notifications.length === 0 ? (
            <div className="af-empty-state" role="status">
              <strong>No authoritative notifications available</strong>
              <span>The app will not invent alerts when the notification authority is unavailable or empty.</span>
            </div>
          ) : notifications.map((item) => (
            <article className={`af-notification af-priority-${item.priority.toLowerCase().replaceAll(" ", "-")}`} key={item.id}>
              <div className="af-notification-priority">{item.priority}</div>
              <strong>{item.title}</strong>
              {item.detail && <p>{item.detail}</p>}
              {item.asOf && <time>{item.asOf}</time>}
            </article>
          ))}
        </div>
      </aside>
    </div>
  );
};
