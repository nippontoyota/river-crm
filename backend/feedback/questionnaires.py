"""Published wording is immutable. Add a new version when questions change."""
QUESTIONNAIRES = {1: {
    "TDF": {"features_explained": "Were vehicle features explained?", "met_expectations": "Did the test drive meet expectations?"},
    "PBF": {"payment_explained": "Were booking/payment details explained?", "delivery_communicated": "Was the expected delivery date communicated?"},
    "PSF": {"handover_satisfactory": "Was the handover satisfactory?", "usage_explained": "Were documents and vehicle usage explained?"},
    "SVC": {"issue_resolved": "Is the issue resolved?", "turnaround_acceptable": "Was the turnaround acceptable?", "charges_explained": "Were charges explained?"},
    "GEN": {"concern_addressed": "Was the concern in the request addressed?"},
}}
CURRENT_VERSION = 1
