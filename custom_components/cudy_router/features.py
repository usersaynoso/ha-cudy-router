"""Page containing the feature not implemented for each device"""

from typing import Dict, List

features_not_implemented: Dict[str, List[str]] = {
    # Unknown models default to enabled modules; module-specific endpoint probing
    # in router.py decides if data can actually be fetched.
    "default": [],
    "WR3000S V1.0": [
        "modem|",
        "data_usage|",
        "sms|",
    ],
}


def existing_feature(device_model: str, key_entity: str, model_entity: str = "") -> bool:
    """Check if a feature is implemented or not for a specific device."""

    if device_model not in features_not_implemented:
        device_model = "default"

    return not any(
        f"{key_entity}|{model_entity}".startswith(feature) for feature in features_not_implemented[device_model]
    )
