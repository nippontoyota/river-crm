export const APP_LOCALE = "en-IN";
export const APP_TIME_ZONE = "Asia/Kolkata";

type DateValue = Date | string | null | undefined;

const partsFor = (value: DateValue, withTime = false) => {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat(APP_LOCALE, {
    timeZone: APP_TIME_ZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" as const } : {}),
  }).formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find(part => part.type === type)?.value || "";
  return { day: get("day"), month: get("month"), year: get("year"), hour: get("hour"), minute: get("minute") };
};

export const formatDate = (value: DateValue) => {
  if (!value) return "";
  if (typeof value === "string") {
    const dateOnly = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (dateOnly) return `${dateOnly[3]}/${dateOnly[2]}/${dateOnly[1]}`;
  }
  const parts = partsFor(value);
  return parts ? `${parts.day}/${parts.month}/${parts.year}` : "";
};

export const formatDateTime = (value: DateValue) => {
  const parts = partsFor(value, true);
  return parts ? `${parts.day}/${parts.month}/${parts.year} ${parts.hour}:${parts.minute}` : "";
};

export const formatWeekday = (value: DateValue) => {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(APP_LOCALE, { weekday: "long", timeZone: APP_TIME_ZONE }).format(date);
};

export const parseDate = (value: string) => {
  const match = value.trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const [, day, month, year] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return date.getUTCFullYear() === Number(year) && date.getUTCMonth() === Number(month) - 1 && date.getUTCDate() === Number(day) ? `${year}-${month}-${day}` : null;
};

export const toApiDate = (value: string | null | undefined) => {
  if (!value) return value;
  return parseDate(value) || value;
};

export const toDateInputValue = (value: string | null | undefined) => {
  if (!value) return "";
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : parseDate(value) || "";
};

export const addDays = (value: string, days: number) => {
  const iso = toDateInputValue(value);
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
};

export const todayInIST = () => String(toApiDate(formatDate(new Date())) || "");

export const parseDateTime = (value: string) => {
  const match = value.trim().match(/^(\d{2}\/\d{2}\/\d{4})[ ,]+([01]\d|2[0-3]):([0-5]\d)$/);
  const date = match && parseDate(match[1]);
  if (!date) return null;
  const parsed = new Date(`${date}T${match[2]}:${match[3]}:00+05:30`);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
};
