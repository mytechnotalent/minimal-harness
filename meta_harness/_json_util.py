"""JSON scanning helpers shared by the adversarial search pipeline."""

import json


def json_text(raw: str) -> str:
    """Return the first JSON array embedded in a model response.

    Parameters
    ----------
    raw : str
        Model response containing JSON.

    Returns
    -------
    str
        Normalized JSON array text.
    """
    value = json_value(raw)
    if not isinstance(value, list):
        raise ValueError("proposer response must be a JSON array")
    return json.dumps(value)


def json_value(raw: str):
    """Decode the first JSON value embedded in a model response.

    Parameters
    ----------
    raw : str
        Model response containing JSON.

    Returns
    -------
    object
        Decoded JSON value.
    """
    text = raw.strip().replace("```json", "").replace("```", "")
    return scan_json(text)


def scan_json(text: str):
    """Scan cleaned text for the first valid JSON value.

    Parameters
    ----------
    text : str
        Cleaned model response.

    Returns
    -------
    object
        Decoded JSON value.
    """
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        value = decode_at(decoder, text, index)
        if value is not None:
            return value
    raise ValueError("model response did not contain valid JSON")


def decode_at(decoder: json.JSONDecoder, text: str, index: int):
    """Try to decode JSON beginning at one text position.

    Parameters
    ----------
    decoder : json.JSONDecoder
        Decoder used for the attempt.
    text : str
        Response text.
    index : int
        Candidate starting position.

    Returns
    -------
    object or None
        Decoded value, or ``None`` when decoding fails.
    """
    try:
        return decoder.raw_decode(text[index:])[0]
    except json.JSONDecodeError:
        return None
