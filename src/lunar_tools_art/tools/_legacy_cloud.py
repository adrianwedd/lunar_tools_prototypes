"""No-op stubs for the retired per-provider image generator classes.

Kept importable for backwards compatibility; construction emits a
DeprecationWarning pointing callers at the unified ``manager.image_gen``.
"""

import warnings


class _LegacyImageGenerator:
    def __init__(self, *args, **kwargs):
        warnings.warn(
            f"{type(self).__name__} is deprecated and does nothing; "
            "use manager.image_gen (unified ImageGenerator) instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    def generate(self, *args, **kwargs):
        pass


class SDXL_TURBO(_LegacyImageGenerator):
    pass


class Dalle3ImageGenerator(_LegacyImageGenerator):
    pass


class FluxImageGenerator(_LegacyImageGenerator):
    pass


class SDXL_LCM(_LegacyImageGenerator):
    pass
