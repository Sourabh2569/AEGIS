import { Award, Clock, Lock, ShieldCheck } from "lucide-react";

export type Achievement = {
  id: string;
  category: "STRATEGY" | "PORTFOLIO" | "PROCESS";
  title: string;
  description: string;
  achieved: boolean;
  achieved_at: string | null;
  detail: string;
};

const CATEGORY_ICON = {
  STRATEGY: Award,
  PORTFOLIO: ShieldCheck,
  PROCESS: Clock,
} as const;

export function AchievementBadge({ achievement }: { achievement: Achievement }) {
  const Icon = achievement.achieved ? CATEGORY_ICON[achievement.category] : Lock;
  return (
    <div className={`achievement-card ${achievement.achieved ? "achieved" : "locked"}`}>
      <span
        className={`achievement-icon ${achievement.achieved ? achievement.category : "locked"}`}
      >
        <Icon size={18} strokeWidth={2} />
      </span>
      <div className="achievement-body">
        <div className="achievement-title">{achievement.title}</div>
        <div className="achievement-detail">{achievement.detail}</div>
      </div>
    </div>
  );
}

export function AchievementGrid({ achievements }: { achievements: Achievement[] }) {
  return (
    <div className="achievement-grid">
      {achievements.map((achievement) => (
        <AchievementBadge key={achievement.id} achievement={achievement} />
      ))}
    </div>
  );
}
