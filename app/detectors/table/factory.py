"""
Factory for creating table detectors.
"""


def get_detector(method="paddle"):
    """
    Factory method to get table detector by method name.

    Args:
        method: The detector method to use

    Returns:
        Table detector instance
    """
    if method == "paddle":
        from . import paddle_detector

        return paddle_detector.PaddleTableDetector()
    else:
        raise ValueError(f"Unknown table detector method: {method}")
