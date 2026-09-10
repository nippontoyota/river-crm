"""Complaint intake categories, not a list of confirmed product defects."""

COMPLAINT_SUBTYPES = {
    "SERVICE_DELAY": ["Appointment unavailable", "Repair delayed", "Spare parts delayed", "Other"],
    "PRODUCT_DEFECT": ["Battery/range", "Charging", "Motor/drivetrain", "Brakes", "Display/electrical", "Suspension/tyres", "Body/accessories", "Other"],
    "DELIVERY_ISSUE": ["Delivery delayed", "Damage at handover", "Missing accessories", "Registration/documents", "Other"],
    "BILLING_FINANCE": ["Invoice discrepancy", "Payment issue", "Refund delay", "Loan/EMI issue", "Other"],
    "AFTER_SALES": ["No callback", "Unresolved repair", "Roadside assistance", "Service quality", "Other"],
    "STAFF_BEHAVIOUR": ["Rude behaviour", "Misinformation", "Poor communication", "Other"],
    "WARRANTY": ["Claim delay", "Claim rejection", "Coverage clarification", "Other"],
    "OTHER": ["Other"],
}
