type OpportunityCardProps = {
  title: string;
  value: string;
  helper: string;
};

export function OpportunityCard({ title, value, helper }: OpportunityCardProps) {
  return (
    <div className="metric-card">
      <span className="metric-label">{title}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-helper">{helper}</span>
    </div>
  );
}
