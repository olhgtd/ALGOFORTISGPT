import React from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { USER_NAV_ITEMS, type UserScreenId } from "../navigation";

export interface UserNavRailProps {
  activeScreen: UserScreenId;
  onNavigate: (screen: UserScreenId) => void;
}

export const UserNavRail: React.FC<UserNavRailProps> = ({ activeScreen, onNavigate }) => (
  <nav className="af-user-nav" aria-label="Primary navigation">
    <div className="af-user-nav-label">Workspace</div>
    <div className="af-user-nav-items">
      {USER_NAV_ITEMS.map((item) => {
        const active = activeScreen === item.id;
        return (
          <button
            key={item.id}
            type="button"
            className={`af-user-nav-item ${active ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
            aria-current={active ? "page" : undefined}
            data-user-nav={item.id}
          >
            <Icon name={item.icon} size={16} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </div>
  </nav>
);
