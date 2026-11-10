"""Constants for the Jiuhao remote."""

DOMAIN = "cdwx8"
MODEL = "cddz.remote.cdwx8"
CONF_UUID_PREFIX = "uuid_prefix"
BUTTON_EVENTS = ("button_a", "button_b", "button_c", "button_d")


def press_signal(entry_id: str) -> str:
    """Return the signal shared by the remote and its virtual buttons."""
    return f"{DOMAIN}_{entry_id}_press"
