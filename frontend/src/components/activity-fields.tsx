"use client";

import { useEffect, useState } from "react";
import { getSystemConfig, type SystemConfig } from "@/lib/crm";

export function ActivityFields({ activity = "", subActivity = "", lists: configuredLists, onChange }: {
  activity?: string; subActivity?: string;
  lists?: SystemConfig["lists"];
  onChange: (fields: { activity: string; sub_activity: string }) => void;
}) {
  const [lists, setLists] = useState<SystemConfig["lists"]>({});
  const [error, setError] = useState("");
  useEffect(() => {
    if (configuredLists) return;
    void getSystemConfig().then(config => setLists(config.lists)).catch(() => setError("Unable to load activities. Reopen this form to retry."));
  }, [configuredLists]);
  const activities = (configuredLists || lists).activities || [];
  const children = (configuredLists || lists).subActivities?.[activity] || [];
  return <>
    <label>Activity (optional)<select name="activity" value={activity} onChange={event => onChange({ activity: event.target.value, sub_activity: "" })} disabled={!activities.length && !activity}>
      <option value="">Select activity</option>
      {activity && !activities.includes(activity) && <option value={activity}>{activity} (retired)</option>}
      {activities.map(item => <option key={item}>{item}</option>)}
    </select></label>
    <label>Sub-activity (optional)<select name="sub_activity" value={subActivity} onChange={event => onChange({ activity, sub_activity: event.target.value })} disabled={!activity || (!children.length && !subActivity)}>
      <option value="">{activity ? "Select sub-activity" : "Select activity first"}</option>
      {subActivity && !children.includes(subActivity) && <option value={subActivity}>{subActivity} (retired)</option>}
      {children.map(item => <option key={item}>{item}</option>)}
    </select></label>
    {error && <p className="form-error" role="alert">{error}</p>}
  </>;
}
