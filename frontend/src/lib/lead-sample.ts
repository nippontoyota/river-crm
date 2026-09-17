import { formatDate } from "@/lib/dates";

export const downloadLeadSample = (source: string) => {
  const leadSampleRows = [
    ["name", "phone", "email", "source", "enquiry date"],
    ["Aarav Sharma", "9876543210", "aarav@example.com", source, formatDate(new Date())],
    ["Ananya Reddy", "9876543211", "ananya@example.com", source, formatDate(new Date())],
  ];
  const csv = leadSampleRows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "incheon-bulk-leads-sample.csv";
  link.click();
  URL.revokeObjectURL(url);
};
