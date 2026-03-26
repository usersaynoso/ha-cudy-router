"""Page containing the feature not implemented for each device"""

from typing import Dict, List

from .model_names import iter_model_name_candidates

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

    matched_model = next(
        (
            candidate
            for candidate in iter_model_name_candidates(device_model)
            if candidate in features_not_implemented
        ),
        "default",
    )

    return not any(
        f"{key_entity}|{model_entity}".startswith(feature)
        for feature in features_not_implemented[matched_model]
    )
